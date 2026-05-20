"""
レコメンドのスコアリングロジック。

ユーザーの行動シグナル（来店回数・お気に入り・高評価・表示回数）から
ジャンル嗜好を算出し、2種類のレコメンドを生成する:
  - revisit  : 「また行きたいお店」(来店済みの再訪提案)
  - discovery: 「あなたへのおすすめ」(嗜好ジャンルに合う未訪問の店)
ゲスト・履歴の薄いユーザー向けに popular(人気店ランキング) も提供する。
"""
import logging
from collections import defaultdict

from django.db.models import Count, Sum

from ..models import Favorite, Rating, Shop, ShopImpression, VisitRecord

logger = logging.getLogger(__name__)

# 行動シグナルの重み
W_VISIT = 3.0       # 来店1回あたり
W_FAVORITE = 2.0    # お気に入り登録
W_HIGH_RATING = 2.0  # 高評価 (score >= 4)
W_IMPRESSION = 0.2  # 表示1回あたり (弱いシグナル)

REVISIT_LIMIT = 10
DISCOVERY_LIMIT = 10
POPULAR_LIMIT = 12


def compute_genre_affinity(user):
    """ユーザーの行動履歴からジャンルごとの嗜好スコアを算出する。"""
    affinity = defaultdict(float)

    for vr in (
        VisitRecord.objects.filter(user=user, visit_count__gt=0)
        .select_related("shop")
    ):
        genre = (vr.shop.genre or "").strip()
        if genre:
            affinity[genre] += vr.visit_count * W_VISIT

    for fav in Favorite.objects.filter(user=user).select_related("shop"):
        genre = (fav.shop.genre or "").strip()
        if genre:
            affinity[genre] += W_FAVORITE

    for rt in (
        Rating.objects.filter(user=user, score__gte=4).select_related("shop")
    ):
        genre = (rt.shop.genre or "").strip()
        if genre:
            affinity[genre] += W_HIGH_RATING

    for imp in ShopImpression.objects.filter(user=user).select_related("shop"):
        genre = (imp.shop.genre or "").strip()
        if genre:
            affinity[genre] += imp.count * W_IMPRESSION

    return dict(affinity)


def get_revisit_records(user, limit=REVISIT_LIMIT):
    """「また行きたいお店」— 来店済みの店を来店回数×最近性で並べる。"""
    return list(
        VisitRecord.objects.filter(user=user, visit_count__gt=0)
        .select_related("shop")
        .order_by("-visit_count", "-updated_at")[:limit]
    )


def get_discovery_shops(user, affinity, exclude_shop_ids, limit=DISCOVERY_LIMIT):
    """「あなたへのおすすめ」— 嗜好ジャンルに合う未訪問の店をキャッシュから探す。"""
    if not affinity:
        return []

    preferred_genres = sorted(affinity, key=affinity.get, reverse=True)

    # このユーザーの店舗別表示回数 (「気になっている店」の加点用)
    impression_map = {
        imp.shop_id: imp.count
        for imp in ShopImpression.objects.filter(user=user)
    }

    candidates = Shop.objects.filter(genre__in=preferred_genres).exclude(
        hotpepper_id__in=exclude_shop_ids
    )

    scored = []
    for shop in candidates:
        genre = (shop.genre or "").strip()
        score = affinity.get(genre, 0.0)
        score += impression_map.get(shop.id, 0) * W_IMPRESSION
        scored.append((score, shop))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [shop for _, shop in scored[:limit]]


def get_popular_shops(limit=POPULAR_LIMIT):
    """全ユーザーの行動を集計した人気店ランキング (ゲスト・履歴の薄いユーザー向け)。"""
    shops = Shop.objects.annotate(
        visit_total=Sum("visit_records__visit_count"),
        fav_total=Count("favorited_by", distinct=True),
        impression_total=Sum("impressions__count"),
    )

    scored = []
    for shop in shops:
        score = (
            (shop.visit_total or 0) * W_VISIT
            + (shop.fav_total or 0) * W_FAVORITE
            + (shop.impression_total or 0) * W_IMPRESSION
        )
        if score > 0:
            scored.append((score, shop))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [shop for _, shop in scored[:limit]]
