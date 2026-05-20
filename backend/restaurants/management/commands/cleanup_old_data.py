"""
古い行動シグナル・履歴データを削除する管理コマンド。

例:
    python manage.py cleanup_old_data
    python manage.py cleanup_old_data --search-days 180 --impression-days 90 --dry-run

cron で 1日1回回せばテーブル肥大化を防げる。
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from restaurants.models import (
    CommentReport,
    SearchHistory,
    ShopImpression,
)


class Command(BaseCommand):
    help = "古い検索履歴 / 表示履歴 / 処理済み通報などを削除する"

    def add_arguments(self, parser):
        parser.add_argument("--search-days", type=int, default=180,
                            help="この日数より古い SearchHistory を削除 (default: 180)")
        parser.add_argument("--impression-days", type=int, default=90,
                            help="この日数より古い ShopImpression を削除 (default: 90)")
        parser.add_argument("--report-days", type=int, default=365,
                            help="この日数より古い CommentReport を削除 (default: 365)")
        parser.add_argument("--dry-run", action="store_true",
                            help="削除せずに件数だけ表示する")

    def handle(self, *args, **opts):
        now = timezone.now()
        plan = [
            ("SearchHistory", SearchHistory.objects.filter(
                created_at__lt=now - timedelta(days=opts["search_days"]))),
            ("ShopImpression (last_seen_at)", ShopImpression.objects.filter(
                last_seen_at__lt=now - timedelta(days=opts["impression_days"]))),
            ("CommentReport", CommentReport.objects.filter(
                created_at__lt=now - timedelta(days=opts["report_days"]))),
        ]

        for label, qs in plan:
            count = qs.count()
            if opts["dry_run"]:
                self.stdout.write(f"[DRY-RUN] {label}: {count} 件削除予定")
            else:
                deleted, _ = qs.delete()
                self.stdout.write(self.style.SUCCESS(f"{label}: {deleted} 件削除しました"))
