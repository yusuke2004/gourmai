from django.contrib import admin

from .models import (
    Comment,
    CommentReport,
    Favorite,
    Rating,
    SearchHistory,
    Shop,
    ShopImpression,
    UserProfile,
    VisitRecord,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "favorite_genre", "theme", "created_at")
    search_fields = ("user__email", "user__username", "display_name")


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "hotpepper_id", "genre", "budget", "updated_at")
    search_fields = ("name", "hotpepper_id", "address")
    list_filter = ("genre",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "shop", "created_at")
    search_fields = ("user__email", "shop__name")


@admin.register(VisitRecord)
class VisitRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "shop", "visit_count", "updated_at")
    search_fields = ("user__email", "shop__name")


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("user", "shop", "score", "updated_at")
    search_fields = ("user__email", "shop__name")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "author_name", "shop", "is_hidden", "report_count", "created_at")
    list_filter = ("is_hidden",)
    search_fields = ("author_name", "text", "shop__name", "ip_address")
    actions = ("hide_comments", "unhide_comments")

    @admin.action(description="選択したコメントを非表示にする")
    def hide_comments(self, request, queryset):
        queryset.update(is_hidden=True)

    @admin.action(description="選択したコメントを再表示する")
    def unhide_comments(self, request, queryset):
        queryset.update(is_hidden=False)


@admin.register(CommentReport)
class CommentReportAdmin(admin.ModelAdmin):
    list_display = ("id", "comment", "reason", "reporter", "created_at")
    list_filter = ("reason",)
    search_fields = ("comment__text", "reporter__email", "reporter_ip")


@admin.register(ShopImpression)
class ShopImpressionAdmin(admin.ModelAdmin):
    list_display = ("user", "shop", "count", "last_seen_at")


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "result_count", "created_at")
    search_fields = ("user__email",)
