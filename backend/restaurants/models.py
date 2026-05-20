from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """拡張ユーザープロフィール"""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=100, blank=True)
    favorite_genre = models.CharField(max_length=100, blank=True)
    theme = models.CharField(max_length=20, default="dark")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"

    def __str__(self):
        return f"{self.user.username} - {self.display_name}"


class Shop(models.Model):
    """店舗キャッシュ (HotPepper APIのデータを保存)"""

    hotpepper_id = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    photo_url = models.URLField(max_length=500, blank=True)
    genre = models.CharField(max_length=100, blank=True)
    budget = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    url = models.URLField(max_length=500, blank=True)
    open_hours = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shops"

    def __str__(self):
        return self.name


class Favorite(models.Model):
    """お気に入り (ユーザーごと)"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    shop = models.ForeignKey(
        Shop, on_delete=models.CASCADE, related_name="favorited_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorites"
        unique_together = ("user", "shop")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} -> {self.shop.name}"


class VisitRecord(models.Model):
    """来店回数 (ユーザーごと)"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="visit_records"
    )
    shop = models.ForeignKey(
        Shop, on_delete=models.CASCADE, related_name="visit_records"
    )
    visit_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "visit_records"
        unique_together = ("user", "shop")

    def __str__(self):
        return f"{self.user.username} -> {self.shop.name}: {self.visit_count}回"


class Rating(models.Model):
    """評価 (ユーザーごと)"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ratings")
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="ratings")
    score = models.FloatField(default=0)  # 0.0 ~ 5.0
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ratings"
        unique_together = ("user", "shop")

    def __str__(self):
        return f"{self.user.username} -> {self.shop.name}: {self.score}"


class Comment(models.Model):
    """コメント (全ユーザー共有)"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="comments", null=True, blank=True
    )
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="comments")
    author_name = models.CharField(max_length=100, default="匿名")
    text = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True, default="")
    is_hidden = models.BooleanField(default=False, db_index=True)
    report_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "comments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.author_name}: {self.text[:50]}"


class CommentReport(models.Model):
    """コメントの通報"""

    REASONS = [
        ("spam", "スパム / 広告"),
        ("abuse", "誹謗中傷"),
        ("false", "虚偽情報"),
        ("privacy", "プライバシー侵害"),
        ("other", "その他"),
    ]

    comment = models.ForeignKey(
        Comment, on_delete=models.CASCADE, related_name="reports"
    )
    reporter = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )
    reason = models.CharField(max_length=20, choices=REASONS, default="other")
    detail = models.TextField(blank=True, default="")
    reporter_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comment_reports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report#{self.id} on comment#{self.comment_id}"


class ShopImpression(models.Model):
    """店舗の表示回数 (ユーザーごと) — レコメンドのシグナル"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="impressions"
    )
    shop = models.ForeignKey(
        Shop, on_delete=models.CASCADE, related_name="impressions"
    )
    count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shop_impressions"
        unique_together = ("user", "shop")

    def __str__(self):
        return f"{self.user.username} -> {self.shop.name}: {self.count}回表示"


class SearchHistory(models.Model):
    """検索履歴 (ユーザーごと)"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="search_histories"
    )
    query_params = models.JSONField()  # 検索パラメータをJSONで保存
    result_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_histories"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.created_at}"
