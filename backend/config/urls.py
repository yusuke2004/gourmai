from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, HttpResponse, HttpResponseNotFound
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_control
from django.views.generic import TemplateView


def _serve_dist_file(name, content_type=None, max_age=3600):
    """frontend/dist 直下の静的ファイルをルートで配信する小さなビュー。"""
    @cache_control(max_age=max_age, public=True)
    def view(request):  # noqa: ARG001
        path_obj = Path(settings.FRONTEND_DIST_DIR) / name
        if not path_obj.exists():
            return HttpResponseNotFound(b"")
        resp = FileResponse(open(path_obj, "rb"))
        if content_type:
            resp["Content-Type"] = content_type
        return resp

    return view


def _robots_txt(request):  # noqa: ARG001
    body = "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin/\n\nSitemap: /sitemap.xml\n"
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def _sitemap_xml(request):
    # 静的ページのみの最小限の sitemap (動的店舗ページは含めない)
    base = request.build_absolute_uri("/").rstrip("/")
    paths = ["/", "/login", "/register", "/terms", "/privacy", "/tokushoho"]
    urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in paths)
    body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HttpResponse(body, content_type="application/xml; charset=utf-8")


urlpatterns = [
    # 管理画面
    path("admin/", admin.site.urls),

    # API
    path("api/restaurants/", include("restaurants.urls")),

    # PWA / SEO
    path("manifest.webmanifest",
         _serve_dist_file("manifest.webmanifest", content_type="application/manifest+json", max_age=3600)),
    path("service-worker.js",
         _serve_dist_file("service-worker.js", content_type="application/javascript", max_age=0)),
    path("robots.txt", _robots_txt),
    path("sitemap.xml", _sitemap_xml),

    # ルート
    path("", TemplateView.as_view(template_name="index.html"), name="root"),

    # SPA フォールバック
    re_path(
        r"^(?!api/|admin/|static/|media/).*$",
        TemplateView.as_view(template_name="index.html"),
    ),
]
