from django.urls import path
from . import views

urlpatterns = [
    path("ping/", views.ping, name="ping"),
    path("search/", views.search, name="search"),
    path("natural-search/", views.natural_search, name="natural_search"),
    path("budgets/", views.budgets, name="budgets"),
    path("genres/", views.genres, name="genres"),
    # Auth
    path("auth/register/", views.register, name="register"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/me/", views.me, name="me"),
    path("auth/profile/", views.update_profile, name="update_profile"),
    # User Data
    path("favorites/", views.favorites_view, name="favorites"),
    path("visits/", views.visits_view, name="visits"),
    path("ratings/", views.ratings_view, name="ratings"),
    path("comments/<str:shop_id>/", views.comments_view, name="comments"),
    path(
        "comments/detail/<int:comment_id>/",
        views.comment_detail_view,
        name="comment_detail",
    ),
    # Search History
    path("search-history/", views.search_history_view, name="search_history"),
    # Share
    path("share/<str:shop_id>/", views.share_view, name="share"),
    # Stats
    path("admin/stats/", views.admin_stats_view, name="admin_stats"),
]
