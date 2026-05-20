"""主要 API のスモークテストと、モデレーション系のユニットテスト。

外部 API (HotPepper / Google / Gemini) はモックする。
"""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Comment, CommentReport, Shop, UserProfile
from utils.moderation import (
    contains_ng_word,
    looks_like_spam,
    sanitize_text,
)


@override_settings(RATELIMIT_ENABLE=False)
class HealthCheckTests(TestCase):
    def test_ping(self):
        res = self.client.get("/api/restaurants/ping/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

    def test_healthz(self):
        res = self.client.get("/api/restaurants/healthz/")
        self.assertEqual(res.status_code, 200)

    def test_readyz(self):
        res = self.client.get("/api/restaurants/readyz/")
        self.assertIn(res.status_code, (200, 503))


@override_settings(RATELIMIT_ENABLE=False)
class AuthFlowTests(TestCase):
    def test_register_requires_terms(self):
        res = self.client.post(
            "/api/restaurants/auth/register/",
            data={"email": "a@example.com", "password": "passw0rd"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "terms_required")

    def test_register_success(self):
        res = self.client.post(
            "/api/restaurants/auth/register/",
            data={"email": "a@example.com", "password": "passw0rd", "agree_terms": True},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(User.objects.filter(email="a@example.com").exists())

    def test_login_uniform_message_on_bad_password(self):
        User.objects.create_user(username="b@example.com", email="b@example.com", password="correct")
        # 存在するが間違ったパスワード
        r1 = self.client.post(
            "/api/restaurants/auth/login/",
            data={"email": "b@example.com", "password": "wrong"},
            content_type="application/json",
        )
        # 存在しないユーザー
        r2 = self.client.post(
            "/api/restaurants/auth/login/",
            data={"email": "unknown@example.com", "password": "whatever"},
            content_type="application/json",
        )
        # 両方とも 401 / 同じエラー値 (ユーザー列挙対策)
        self.assertEqual(r1.status_code, 401)
        self.assertEqual(r2.status_code, 401)
        self.assertEqual(r1.json()["error"], r2.json()["error"])

    def test_account_deletion(self):
        u = User.objects.create_user(username="c@example.com", email="c@example.com", password="pw12345")
        self.client.force_login(u)
        res = self.client.delete(
            "/api/restaurants/auth/delete/",
            data={"confirm": "DELETE"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(pk=u.pk).exists())


@override_settings(RATELIMIT_ENABLE=False)
class CommentModerationTests(TestCase):
    def setUp(self):
        self.shop = Shop.objects.create(hotpepper_id="hp_test_1", name="テスト居酒屋")

    def _post_comment(self, text):
        return self.client.post(
            f"/api/restaurants/comments/{self.shop.hotpepper_id}/",
            data={"text": text},
            content_type="application/json",
        )

    def test_comment_post_basic(self):
        res = self._post_comment("ちょうど良かったです")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Comment.objects.count(), 1)
        c = Comment.objects.first()
        # IP / UA が記録されていること
        self.assertIsNotNone(c.ip_address)

    @override_settings(NG_WORDS=["バカ"])
    def test_comment_rejects_ng_word(self):
        res = self._post_comment("店員はバカだった")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "ng_word")

    def test_comment_rejects_spam(self):
        res = self._post_comment("https://a.example.com https://b.example.com 良いお店")
        self.assertEqual(res.status_code, 400)

    def test_report_threshold_hides_comment(self):
        c = Comment.objects.create(shop=self.shop, text="テスト投稿", author_name="x")
        url = f"/api/restaurants/comments/{c.id}/report/"
        for _ in range(3):
            res = self.client.post(url, data={"reason": "spam"}, content_type="application/json")
            self.assertEqual(res.status_code, 200)
        c.refresh_from_db()
        self.assertTrue(c.is_hidden)
        self.assertEqual(CommentReport.objects.count(), 3)

    def test_hidden_comments_not_listed(self):
        Comment.objects.create(shop=self.shop, text="ふつう", author_name="x")
        Comment.objects.create(shop=self.shop, text="非表示", author_name="y", is_hidden=True)
        res = self.client.get(f"/api/restaurants/comments/{self.shop.hotpepper_id}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body), 1)


class ModerationUnitTests(TestCase):
    def test_contains_ng_word(self):
        with self.settings(NG_WORDS=["xxx", "yyy"]):
            self.assertEqual(contains_ng_word("これは xxx ですよ"), "xxx")
            self.assertIsNone(contains_ng_word("普通のテキスト"))

    def test_looks_like_spam(self):
        self.assertTrue(looks_like_spam("https://a.example.com http://b.example.com"))
        self.assertTrue(looks_like_spam("aaaaaaaaaaaaaaaaaa"))
        self.assertFalse(looks_like_spam("良いお店でした!"))

    def test_sanitize_text(self):
        self.assertEqual(sanitize_text("  hello  "), "hello")
        self.assertEqual(sanitize_text("a\n\n\n\nb"), "a\n\nb")
        self.assertEqual(sanitize_text("0123456789", max_length=5), "01234")


@override_settings(RATELIMIT_ENABLE=False)
class AdminStatsTests(TestCase):
    def test_admin_stats_excludes_emails(self):
        admin = User.objects.create_user(
            username="admin@example.com", email="admin@example.com",
            password="pw", is_staff=True,
        )
        User.objects.create_user(username="u1@example.com", email="u1@example.com", password="pw")
        self.client.force_login(admin)
        res = self.client.get("/api/restaurants/admin/stats/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("total_users", body)
        self.assertNotIn("user_emails", body)
