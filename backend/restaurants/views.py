from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.request import Request
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from utils.ratelimit_compat import ratelimit
from .services.hotpepper_client import (
    search_restaurants,
    search_by_keyword,
    get_budget_master,
    get_genre_master,
)
from .services.google_maps_client import search_nearby_places, search_places_by_text
from .services.gemini_service import parse_search_intent, generate_ai_recommendation
from .models import (
    UserProfile,
    Shop,
    Favorite,
    VisitRecord,
    Rating,
    Comment,
    CommentReport,
    SearchHistory,
    ShopImpression,
)
from .services.recommendation import (
    compute_genre_affinity,
    get_revisit_records,
    get_discovery_shops,
    get_popular_shops,
)
from django.db.models import F
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    LoginSerializer,
    FavoriteSerializer,
    VisitRecordSerializer,
    RatingSerializer,
    CommentSerializer,
    CommentReadSerializer,
    SearchHistorySerializer,
    ShopSerializer,
)
import logging
from utils.location import calculate_distance
from utils.cache import cached, make_key
from utils.moderation import (
    contains_ng_word,
    get_client_ip,
    get_user_agent,
    looks_like_spam,
    sanitize_text,
)
from django.core.cache import cache as django_cache

logger = logging.getLogger(__name__)

HP_GENRE_NAMES = {
    "G001": "居酒屋", "G002": "ダイニングバー・バル", "G003": "創作料理",
    "G004": "和食", "G005": "洋食", "G006": "イタリアン・フレンチ",
    "G007": "中華", "G008": "焼肉・ホルモン", "G009": "アジア・エスニック料理",
    "G010": "各国料理", "G011": "カラオケ・パーティ", "G012": "バー・カクテル",
    "G013": "ラーメン", "G014": "カフェ・スイーツ", "G017": "韓国料理", "G015": "その他"
}

# レコメンドのハイブリッド検索用: ジャンル名 → HotPepper ジャンルコード
HP_GENRE_NAME_TO_CODE = {name: code for code, name in HP_GENRE_NAMES.items()}


@api_view(["GET"])
def ping(request: Request) -> Response:
    return Response({"ok": True, "message": "API is working"})


@api_view(["GET"])
@permission_classes([AllowAny])
def healthz(request: Request) -> Response:
    """liveness — 外部依存に触らない軽量チェック"""
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([AllowAny])
def readyz(request: Request) -> Response:
    """readiness — DB と cache に触れる"""
    from django.db import connection
    db_ok = True
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception:
        db_ok = False

    cache_ok = True
    try:
        django_cache.set("ready:probe", "1", 5)
        cache_ok = django_cache.get("ready:probe") == "1"
    except Exception:
        cache_ok = False

    status = 200 if (db_ok and cache_ok) else 503
    return Response({"ok": status == 200, "db": db_ok, "cache": cache_ok}, status=status)


def ratelimited_view(request, exception):  # noqa: ARG001
    """settings.RATELIMIT_VIEW から呼ばれる。429 を返す。"""
    from django.http import JsonResponse
    return JsonResponse(
        {"error": "rate_limited", "message": "リクエストが多すぎます。しばらく待ってからお試しください。"},
        status=429,
    )


def _perform_combined_search(
    lat: Optional[float], 
    lng: Optional[float], 
    range_val: int = 5, 
    budget_min: Optional[str] = None, 
    budget_max: Optional[str] = None, 
    genre: Optional[str] = None, 
    keyword: Optional[str] = None, 
    people: Optional[str] = None, 
    free_drink: Optional[str] = None, 
    free_food: Optional[str] = None,
    user = None,
    original_query_params: Optional[dict] = None
) -> List[Dict[str, Any]]:
    # radius in meters for Google
    radius_map = {1: 300, 2: 500, 3: 1000, 4: 2000, 5: 3000}
    radius = radius_map.get(range_val, 1000)

    # Budget range expansion for HotPepper
    budget_codes_list = None
    if budget_min or budget_max:
        all_codes = ['B009', 'B010', 'B011', 'B001', 'B002', 'B003', 'B008', 'B004', 'B005', 'B006', 'B012', 'B013', 'B014']
        idx_min = 0
        idx_max = len(all_codes) - 1
        if budget_min:
            try: idx_min = all_codes.index(budget_min)
            except ValueError: pass
        if budget_max:
            try: idx_max = all_codes.index(budget_max)
            except ValueError: pass
        
        if idx_min <= idx_max:
            budget_codes_list = all_codes[idx_min:idx_max+1]

    # Convert frontend free_drink/free_food (true/false) to HP (1/0)
    hp_free_drink = "1" if free_drink in ["true", "1", True] else None
    hp_free_food = "1" if free_food in ["true", "1", True] else None

    # 1+2. HotPepper / Google Maps を並列で叩く
    def _hp() -> List[Dict[str, Any]]:
        try:
            if lat and lng:
                return search_restaurants(
                    lat=lat, lng=lng, range=range_val, budget=None,
                    genre=genre, keyword=keyword, people=people,
                    free_drink=hp_free_drink, free_food=hp_free_food,
                )
            return search_by_keyword(
                keyword=keyword or "", range=range_val, budget=None,
                genre=genre, people=people,
                free_drink=hp_free_drink, free_food=hp_free_food,
            )
        except Exception as e:
            logger.error(f"HotPepper Search Error: {e}")
            return []

    def _google() -> List[Dict[str, Any]]:
        try:
            if lat and lng:
                return search_nearby_places(lat, lng, radius=radius, keyword=keyword, genre=genre)
            if keyword:
                return search_places_by_text(keyword, lat, lng, radius=radius, genre=genre)
            return []
        except Exception as e:
            logger.error(f"Google Maps Search Error: {e}")
            return []

    shops: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        hp_fut = ex.submit(_hp)
        gg_fut = ex.submit(_google)
        all_hp_shops = hp_fut.result()
        google_shops = gg_fut.result()

    # Local filtering for HP budget codes
    if budget_codes_list:
        hp_shops = [s for s in all_hp_shops if s.get("raw_budget_code") in budget_codes_list]
    else:
        hp_shops = all_hp_shops
    shops.extend(hp_shops)
    shops.extend(google_shops)

    # 3. マージと重複排除 (名前と距離で判定)
    import re as _re

    def normalize_name(n):
        if not n: return ""
        n = n.lower()
        n = _re.sub(r'[ 　\(\)（）\-\.\[\]]', '', n)
        for suffix in ["店", "駅前", "成城店", "新宿店", "池袋店", "本店", "分店"]:
            if n.endswith(suffix) and len(n) > len(suffix) + 1:
                n = n[:-len(suffix)]
        return n

    def _bucket_key(lat_v, lng_v):
        # 約0.001度 ≒ 100m 単位でバケット化。隣接 9 セルを見れば 50m判定は十分。
        if lat_v is None or lng_v is None:
            return None
        return (round(float(lat_v) * 1000), round(float(lng_v) * 1000))

    # geohash 風バケット → 既存店舗 index リスト
    bucket_map: Dict[Any, List[int]] = {}
    merged_shops: List[Dict[str, Any]] = []

    for s in shops:
        s["is_hotpepper"] = (s.get("source") == "hotpepper")
        s["is_google"] = (s.get("source") == "google")

        s_name = s.get("name", "")
        norm = normalize_name(s_name)
        s_lat = s.get("lat")
        s_lng = s.get("lng")
        bk = _bucket_key(s_lat, s_lng)

        # 候補 index を集める (近接バケット + 同名簡易ヒット)
        candidate_idx: set[int] = set()
        if bk is not None:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    candidate_idx.update(bucket_map.get((bk[0] + dy, bk[1] + dx), []))
        # 位置が無い場合は名前のみで線形探索 (フォールバック)
        if bk is None:
            candidate_idx = set(range(len(merged_shops)))

        found = False
        for idx in candidate_idx:
            existing = merged_shops[idx]
            e_norm = normalize_name(existing.get("name", ""))
            e_lat = existing.get("lat")
            e_lng = existing.get("lng")

            name_match = (norm in e_norm or e_norm in norm) and len(norm) >= 3 and len(e_norm) >= 3
            dist = calculate_distance(s_lat, s_lng, e_lat, e_lng)

            shared_keywords = any((k in e_norm and len(k) >= 2) for k in [norm[i:i+2] for i in range(len(norm)-1)])
            pos_match = dist is not None and (
                (dist < 0.05 and shared_keywords) or
                (dist < 0.02 and (norm[:2] == e_norm[:2] or norm[-2:] == e_norm[-2:]))
            )

            if name_match or pos_match:
                if s.get("google_rating"):
                    existing["google_rating"] = s["google_rating"]
                    existing["google_user_rating_count"] = s.get("google_user_rating_count", 0)
                    existing["is_google"] = True
                if s.get("url") and "hotpepper.jp" in (s.get("url") or ""):
                    existing["url"] = s["url"]
                    existing["is_hotpepper"] = True
                    if s.get("photo"):
                        existing["photo"] = s["photo"]
                found = True
                break

        if not found:
            merged_shops.append(s)
            if bk is not None:
                bucket_map.setdefault(bk, []).append(len(merged_shops) - 1)

    # 4. ジャンル厳密フィルタ (居酒屋選択時にカフェとかが出ないように)
    if genre:
        target_genre_name = HP_GENRE_NAMES.get(genre, "")
        final_shops = []
        for s in merged_shops:
            shop_genre = s.get("genre", "") or ""
            if not shop_genre:
                final_shops.append(s)
                continue
            
            is_match = False
            if s.get("is_hotpepper") and "genre_code" in s and genre in s["genre_code"]:
                is_match = True
            elif target_genre_name and target_genre_name in shop_genre:
                is_match = True
            elif "居酒屋" in target_genre_name and ("居酒屋" in shop_genre or "ダイニング" in shop_genre or "バル" in shop_genre):
                is_match = True
            elif target_genre_name == "和食" and ("和食" in shop_genre or "日本料理" in shop_genre):
                is_match = True
            
            if is_match:
                final_shops.append(s)
            else:
                logger.info(f"Filtered out: {s.get('name')} ({shop_genre}) for target {target_genre_name}")
        
        merged_shops = final_shops

    shops = merged_shops

    # 4. 検索履歴保存
    if user and user.is_authenticated and original_query_params:
        SearchHistory.objects.create(
            user=user,
            query_params=original_query_params,
            result_count=len(shops),
        )

    return shops


@api_view(["POST"])
@ratelimit(key="user_or_ip", rate="20/m", method="POST", block=False)
@ratelimit(key="user_or_ip", rate="200/h", method="POST", block=False)
def natural_search(request: Request) -> Response:
    """
    Geminiを使用した自然言語検索
    POST /api/restaurants/natural-search
    """
    if getattr(request, "limited", False):
        return Response(
            {"error": "rate_limited", "message": "リクエストが多すぎます。しばらくお待ちください。"},
            status=429,
        )

    query = request.data.get("query")
    if not query:
        return Response({"error": "Query is required"}, status=400)
    if len(query) > 300:
        return Response({"error": "Query is too long"}, status=400)

    try:
        lat_param = request.data.get("lat")
        lng_param = request.data.get("lng")
        current_genre = request.data.get("current_genre")
        current_people = request.data.get("current_people")
        current_budget_max = request.data.get("current_budget_max")

        # Geminiでパース
        parsed = parse_search_intent(query) or {}
        logger.info(f"Parsed intent: {parsed}")
        
        # パース結果からパラメータを調整
        keyword = parsed.get("keyword")
        genre_name = parsed.get("genre") or current_genre
        location_name = parsed.get("location")
        people_val = parsed.get("people") or current_people
        
        hp_genre_code = None
        if genre_name:
            all_genres = get_genre_master()
            for g in all_genres:
                if genre_name in g["name"]:
                    hp_genre_code = g["code"]
                    break
        
        budget_min_code = None
        budget_max_code = None
        budget_max_yen = parsed.get("budget_max_yen")
        
        if not budget_max_yen and current_budget_max:
            try:
                import re
                m = re.search(r'(\d+)', current_budget_max)
                if m: budget_max_yen = int(m.group(1))
            except: pass

        if parsed.get("budget_min_yen") or budget_max_yen:
            def yen_to_code(yen):
                if not yen: return None
                try:
                    yen_int = int(yen)
                    if yen_int <= 500: return "B009"
                    if yen_int <= 1000: return "B010"
                    if yen_int <= 1500: return "B011"
                    if yen_int <= 2000: return "B001"
                    if yen_int <= 3000: return "B002"
                    if yen_int <= 4000: return "B003"
                    return "B008"
                except: return None
            
            budget_min_code = yen_to_code(parsed.get("budget_min_yen"))
            budget_max_code = yen_to_code(budget_max_yen)

        # キーワードの構築
        effective_keyword = f"{location_name or ''} {keyword or ''}".strip()
        
        # 緯度経度の安全な変換
        def to_float(v):
            if v is None: return None
            try: return float(v)
            except: return None

        lat = to_float(lat_param)
        lng = to_float(lng_param)
        
        shops = _perform_combined_search(
            lat=lat, lng=lng,
            budget_min=budget_min_code,
            budget_max=budget_max_code,
            genre=hp_genre_code,
            keyword=effective_keyword or query,
            people=str(people_val) if people_val else None,
            user=request.user,
            original_query_params={"natural_query": query}
        )
        
        if not shops and effective_keyword:
            shops = _perform_combined_search(
                lat=lat, lng=lng,
                budget_max=budget_max_code,
                genre=hp_genre_code,
                user=request.user
            )

        # AIでリコメンド (エラー時は元のリストを維持)
        if shops:
            try:
                shops = generate_ai_recommendation(query, shops)
            except Exception as e:
                logger.error(f"Post-search AI recommendation failed: {e}")
        
        return Response({
            "params": parsed,
            "shops": shops
        })

    except Exception as e:
        logger.error(f"Critical error in natural_search: {e}")
        return Response({
            "error": "Internal search error",
            "shops": []
        }, status=200)

@api_view(["GET"])
@ratelimit(key="user_or_ip", rate="60/m", method="GET", block=False)
def search(request: Request) -> Response:
    """
    店舗検索 (HotPepper + Google Maps)
    GET /api/restaurants/search
    """
    if getattr(request, "limited", False):
        return Response(
            {"error": "rate_limited", "message": "検索が多すぎます。少し待って再試行してください。"},
            status=429,
        )

    lat_param = request.GET.get("lat")
    lng_param = request.GET.get("lng")
    range_param = request.GET.get("range", "5")
    budget_min = request.GET.get("budget_min")
    budget_max = request.GET.get("budget_max")
    genre = request.GET.get("genre")
    keyword = request.GET.get("keyword")
    people = request.GET.get("people")
    free_drink = request.GET.get("free_drink")
    free_food = request.GET.get("free_food")

    # 検索結果キャッシュ (同一条件 5 分)。ユーザー固有副作用 (履歴保存) は判定後に行う。
    cache_payload = {
        "lat": lat_param, "lng": lng_param, "range": range_param,
        "budget_min": budget_min, "budget_max": budget_max,
        "genre": genre, "keyword": keyword, "people": people,
        "free_drink": free_drink, "free_food": free_food,
    }
    cache_key = make_key("search:combined", cache_payload)
    shops = django_cache.get(cache_key)
    if shops is None:
        shops = _perform_combined_search(
            lat=float(lat_param) if lat_param else None,
            lng=float(lng_param) if lng_param else None,
            range_val=int(range_param) if range_param and range_param.isdigit() else 5,
            budget_min=budget_min,
            budget_max=budget_max,
            genre=genre,
            keyword=keyword,
            people=people,
            free_drink=free_drink,
            free_food=free_food,
            user=None,  # キャッシュ対象には履歴を書かない
            original_query_params=None,
        )
        django_cache.set(cache_key, shops, 60 * 5)

    # 履歴は (キャッシュヒットでも) 別途記録する
    if request.user.is_authenticated:
        try:
            SearchHistory.objects.create(
                user=request.user,
                query_params=dict(request.GET),
                result_count=len(shops or []),
            )
        except Exception as e:
            logger.warning(f"SearchHistory save failed: {e}")

    # 検索ワードやジャンル指定がある場合、AI評価を追加 (これはキャッシュしない)
    if shops and (keyword or genre):
        ai_query = f"{keyword or ''} {genre or ''}".strip()
        try:
            shops = generate_ai_recommendation(ai_query, shops)
        except Exception as e:
            logger.error(f"AI recommendation failed: {e}")

    return Response({"shops": shops})


@api_view(["GET"])
def budgets(request: Request) -> Response:
    """
    予算マスタ取得
    GET /api/restaurants/budgets
    """
    try:
        data = get_budget_master()
        return Response({"results": data})
    except Exception as e:
        logger.error(f"Budget API Error: {e}")
        return Response({"error": "Could not fetch budgets"}, status=500)


@api_view(["GET"])
def genres(request: Request) -> Response:
    """
    ジャンルマスタ取得
    GET /api/restaurants/genres
    """
    try:
        data = get_genre_master()
        return Response({"results": data})
    except Exception as e:
        logger.error(f"Genre API Error: {e}")
        return Response({"error": "Could not fetch genres"}, status=500)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_stats_view(request: Request) -> Response:
    """
    管理者用統計データ取得 (is_staff のユーザーのみ)
    GET /api/restaurants/admin/stats

    プライバシー上、個別のメールアドレス一覧は返さない (集計値のみ)。
    """
    total_users = User.objects.count()

    histories = SearchHistory.objects.order_by('-created_at')[:500]
    budget_stats: Dict[str, int] = {}
    people_stats: Dict[str, int] = {}
    for h in histories:
        params = h.query_params
        if not isinstance(params, dict):
            continue
        b_max = params.get('budget_max')
        if isinstance(b_max, list) and len(b_max) > 0:
            b_max = b_max[0]
        if b_max:
            budget_stats[b_max] = budget_stats.get(b_max, 0) + 1
        p = params.get('people')
        if isinstance(p, list) and len(p) > 0:
            p = p[0]
        if p:
            people_stats[p] = people_stats.get(p, 0) + 1

    # コメント関連の運用指標
    total_comments = Comment.objects.count()
    hidden_comments = Comment.objects.filter(is_hidden=True).count()
    pending_reports = CommentReport.objects.filter(comment__is_hidden=False).count()

    return Response({
        "total_users": total_users,
        "budget_stats": budget_stats,
        "people_stats": people_stats,
        "total_comments": total_comments,
        "hidden_comments": hidden_comments,
        "pending_reports": pending_reports,
    })


# ============================================================
# Auth Endpoints
# ============================================================
@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="5/m", method="POST", block=False)
@ratelimit(key="ip", rate="50/h", method="POST", block=False)
def register(request):
    """ユーザー登録"""
    if getattr(request, "limited", False):
        return Response(
            {"error": "rate_limited", "message": "登録の試行が多すぎます。しばらく待って再試行してください。"},
            status=429,
        )
    ser = RegisterSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    email = ser.validated_data["email"]
    password = ser.validated_data["password"]
    display_name = ser.validated_data.get("display_name", "")

    # 利用規約への同意フラグ (フロントエンドで明示的に true を送る)
    if not request.data.get("agree_terms"):
        return Response(
            {"error": "terms_required", "message": "利用規約とプライバシーポリシーへの同意が必要です。"},
            status=400,
        )

    if User.objects.filter(email=email).exists():
        return Response(
            {"error": "このメールアドレスは既に登録されています"}, status=400
        )

    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
    )
    UserProfile.objects.create(
        user=user, display_name=display_name or email.split("@")[0]
    )
    login(request, user)
    return Response(UserSerializer(user).data, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="10/m", method="POST", block=False)
@ratelimit(key="post:email", rate="10/h", method="POST", block=False)
def login_view(request):
    """ログイン。ユーザー列挙を避けるため成功 / 失敗のメッセージは統一する。"""
    if getattr(request, "limited", False):
        return Response(
            {"error": "rate_limited", "message": "ログイン試行が多すぎます。しばらくしてからお試しください。"},
            status=429,
        )
    ser = LoginSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    email = ser.validated_data["email"]
    password = ser.validated_data["password"]

    user = authenticate(request, username=email, password=password)
    if not user:
        # メール有無に関わらず統一メッセージ
        return Response(
            {"error": "invalid_credentials", "message": "メールアドレスまたはパスワードが正しくありません。"},
            status=401,
        )

    login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
def logout_view(request: Request) -> Response:
    """ログアウト"""
    logout(request)
    return Response({"ok": True})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account_view(request: Request) -> Response:
    """退会 (アカウント削除)。

    関連レコードはモデルの on_delete=CASCADE に従って削除される。
    """
    assert request.user.is_authenticated
    user = request.user
    confirm = request.data.get("confirm") if hasattr(request, "data") else None
    if confirm != "DELETE":
        return Response(
            {"error": "confirm_required", "message": "確認のため 'DELETE' を送信してください。"},
            status=400,
        )
    logout(request)
    user.delete()
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def me(request: Request) -> Response:
    """現在のユーザー情報。未ログインでも csrftoken クッキーを必ず発行する。

    IsAuthenticated にすると未ログイン時に 403 が先に返り @ensure_csrf_cookie が
    走らないため、AllowAny にして view 内で認証状態を判定する。
    """
    if not request.user.is_authenticated:
        return Response({"detail": "Not authenticated"}, status=401)
    return Response(UserSerializer(request.user).data)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_profile(request: Request) -> Response:
    """プロフィール更新"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    display_name = request.data.get("display_name")
    favorite_genre = request.data.get("favorite_genre")
    theme = request.data.get("theme")

    if display_name is not None:
        profile.display_name = display_name
    if favorite_genre is not None:
        profile.favorite_genre = favorite_genre
    if theme is not None:
        profile.theme = theme
    profile.save()
    return Response(UserSerializer(request.user).data)


# ============================================================
# Shop Upsert (create or get from HP API data)
# ============================================================
def get_or_create_shop(shop_data):
    """HotPepper APIのデータから Shop を作成/取得"""
    shop_id = shop_data.get("id", "")
    if not shop_id:
        return None
    # Google 由来の店舗は budget / genre などが None になりうるため "" に正規化する
    shop, _ = Shop.objects.update_or_create(
        hotpepper_id=shop_id,
        defaults={
            "name": shop_data.get("name") or "",
            "photo_url": shop_data.get("photo") or "",
            "genre": shop_data.get("genre") or "",
            "budget": shop_data.get("budget") or "",
            "address": shop_data.get("address") or "",
            "lat": shop_data.get("lat"),
            "lng": shop_data.get("lng"),
            "url": shop_data.get("url") or "",
            "open_hours": shop_data.get("open") or "",
        },
    )
    return shop


# ============================================================
# Favorites API
# ============================================================
@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def favorites_view(request: Request) -> Response:
    assert request.user.is_authenticated
    if request.method == "GET":
        favs = Favorite.objects.filter(user=request.user).select_related("shop")
        return Response(FavoriteSerializer(favs, many=True).data)

    elif request.method == "POST":
        shop_data = request.data.get("shop", {})
        shop = get_or_create_shop(shop_data)
        if not shop:
            return Response({"error": "Invalid shop data"}, status=400)
        fav, created = Favorite.objects.get_or_create(user=request.user, shop=shop)
        if not created:
            return Response({"message": "Already favorited"}, status=200)
        return Response(FavoriteSerializer(fav).data, status=201)

    elif request.method == "DELETE":
        shop_id = request.data.get("shop_id", "")
        try:
            shop = Shop.objects.get(hotpepper_id=shop_id)
            Favorite.objects.filter(user=request.user, shop=shop).delete()
        except Shop.DoesNotExist:
            pass
        return Response({"ok": True})
    return Response({"error": "Method not allowed"}, status=405)


# ============================================================
# Visit Count API
# ============================================================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def visits_view(request: Request) -> Response:
    assert request.user.is_authenticated
    if request.method == "GET":
        records = VisitRecord.objects.filter(
            user=request.user, visit_count__gt=0
        ).select_related("shop")
        return Response(VisitRecordSerializer(records, many=True).data)

    elif request.method == "POST":
        shop_data = request.data.get("shop", {})
        visit_count = request.data.get("visit_count", 0)
        shop = get_or_create_shop(shop_data)
        if not shop:
            return Response({"error": "Invalid shop data"}, status=400)
        record, _ = VisitRecord.objects.update_or_create(
            user=request.user, shop=shop, defaults={"visit_count": visit_count}
        )
        return Response(VisitRecordSerializer(record).data)
    return Response({"error": "Method not allowed"}, status=405)


# ============================================================
# Rating API
# ============================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ratings_view(request: Request) -> Response:
    assert request.user.is_authenticated
    shop_data = request.data.get("shop", {})
    score = request.data.get("score", 0)
    shop = get_or_create_shop(shop_data)
    if not shop:
        return Response({"error": "Invalid shop data"}, status=400)
    rating, _ = Rating.objects.update_or_create(
        user=request.user, shop=shop, defaults={"score": float(score)}
    )
    return Response(RatingSerializer(rating).data)


# ============================================================
# Comments API (shared across all users)
# ============================================================
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False)
@ratelimit(key="user_or_ip", rate="100/h", method="POST", block=False)
def comments_view(request: Request, shop_id: str) -> Response:
    """GET: 特定店舗の (非表示でない) コメント一覧, POST: コメント投稿"""
    if request.method == "GET":
        try:
            shop = Shop.objects.get(hotpepper_id=shop_id)
        except Shop.DoesNotExist:
            return Response([])
        comments = Comment.objects.filter(shop=shop, is_hidden=False)
        return Response(CommentReadSerializer(comments, many=True).data)

    # POST
    if getattr(request, "limited", False):
        return Response(
            {"error": "rate_limited", "message": "投稿が短時間に多すぎます。少しお待ちください。"},
            status=429,
        )

    max_len = getattr(settings, "COMMENT_MAX_LENGTH", 1000)
    text = sanitize_text(request.data.get("text", ""), max_length=max_len)
    if not text:
        return Response({"error": "Comment text is required"}, status=400)

    ng = contains_ng_word(text)
    if ng:
        return Response(
            {"error": "ng_word", "message": f"NG ワードが含まれています ({ng})。表現を見直してください。"},
            status=400,
        )
    if looks_like_spam(text):
        return Response(
            {"error": "spam", "message": "スパムの可能性のある内容のため受け付けられませんでした。"},
            status=400,
        )

    # 店舗が未登録なら、投稿データ(shop)から作成する
    try:
        shop = Shop.objects.get(hotpepper_id=shop_id)
    except Shop.DoesNotExist:
        shop = get_or_create_shop(request.data.get("shop", {}))
        if not shop:
            return Response({"error": "Shop not found"}, status=404)

    user = request.user if request.user.is_authenticated else None
    author_name = "匿名"
    if user:
        profile = getattr(user, "profile", None)
        author_name = profile.display_name if profile else getattr(user, "username", "ユーザー")

    comment = Comment.objects.create(
        shop=shop,
        user=user,
        author_name=author_name,
        text=text,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return Response(CommentReadSerializer(comment).data, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="user_or_ip", rate="10/h", method="POST", block=False)
def report_comment_view(request: Request, comment_id: int) -> Response:
    """コメントの通報。3件以上で自動的に非表示にする。"""
    if getattr(request, "limited", False):
        return Response(
            {"error": "rate_limited", "message": "通報が多すぎます。"},
            status=429,
        )
    try:
        comment = Comment.objects.get(id=comment_id)
    except Comment.DoesNotExist:
        return Response({"error": "Comment not found"}, status=404)

    reason = (request.data.get("reason") or "other").strip()
    detail = sanitize_text(request.data.get("detail", ""), max_length=500)

    valid_reasons = {k for k, _ in CommentReport.REASONS}
    if reason not in valid_reasons:
        reason = "other"

    CommentReport.objects.create(
        comment=comment,
        reporter=request.user if request.user.is_authenticated else None,
        reason=reason,
        detail=detail,
        reporter_ip=get_client_ip(request),
    )
    # 通報数をインクリメントし、しきい値超えで非表示
    Comment.objects.filter(pk=comment.pk).update(report_count=F("report_count") + 1)
    comment.refresh_from_db(fields=["report_count"])
    if comment.report_count >= 3 and not comment.is_hidden:
        Comment.objects.filter(pk=comment.pk).update(is_hidden=True)
        logger.info(f"Comment {comment.pk} auto-hidden after {comment.report_count} reports")

    return Response({"ok": True})


@api_view(["PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def comment_detail_view(request: Request, comment_id: int) -> Response:
    """PUT: 自分のコメント編集, DELETE: 自分のコメント削除"""
    assert request.user.is_authenticated
    try:
        comment = Comment.objects.get(id=comment_id, user=request.user)
    except Comment.DoesNotExist:
        return Response({"error": "Comment not found or not yours"}, status=404)

    if request.method == "PUT":
        max_len = getattr(settings, "COMMENT_MAX_LENGTH", 1000)
        text = sanitize_text(request.data.get("text", ""), max_length=max_len)
        if not text:
            return Response({"error": "Comment text is required"}, status=400)
        ng = contains_ng_word(text)
        if ng:
            return Response(
                {"error": "ng_word", "message": f"NG ワードが含まれています ({ng})。"},
                status=400,
            )
        if looks_like_spam(text):
            return Response(
                {"error": "spam", "message": "スパムの可能性のある内容です。"},
                status=400,
            )
        comment.text = text
        comment.save()
        return Response(CommentReadSerializer(comment).data)

    elif request.method == "DELETE":
        comment.delete()
        return Response({"ok": True})
    return Response({"error": "Method not allowed"}, status=405)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_comments_view(request: Request) -> Response:
    """ログインユーザー自身の全コメント (店舗情報つき)"""
    comments = (
        Comment.objects.filter(user=request.user)
        .select_related("shop")
        .order_by("-created_at")
    )
    data = [
        {
            "id": c.id,
            "text": c.text,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "shop": ShopSerializer(c.shop).data if c.shop else None,
        }
        for c in comments
    ]
    return Response(data)


# ============================================================
# Search History API
# ============================================================
@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def search_history_view(request: Request) -> Response:
    assert request.user.is_authenticated
    if request.method == "GET":
        histories = SearchHistory.objects.filter(user=request.user)[:50]  # 最新50件
        return Response(SearchHistorySerializer(histories, many=True).data)

    elif request.method == "POST":
        query_params = request.data.get("query_params", {})
        result_count = request.data.get("result_count", 0)
        SearchHistory.objects.create(
            user=request.user, query_params=query_params, result_count=result_count
        )
        return Response({"ok": True}, status=201)

    elif request.method == "DELETE":
        SearchHistory.objects.filter(user=request.user).delete()
        return Response({"ok": True})
    return Response({"error": "Method not allowed"}, status=405)


# ============================================================
# Share API
# ============================================================
@api_view(["GET"])
def share_view(request: Request, shop_id: str) -> Response:
    """店舗のシェア用URL生成"""
    shop = None
    try:
        shop = Shop.objects.get(hotpepper_id=shop_id)
    except Shop.DoesNotExist:
        # DBにない場合も共有可能にする
        logger.info(f"Share requested for unknown shop {shop_id}")

    # アプリ内の店舗詳細ページURL
    base_uri = request.build_absolute_uri("/").rstrip("/")
    share_url = f"{base_uri}/#/detail?shop_id={shop_id}"

    # シェア用テキスト
    shop_name = shop.name if shop else ""
    share_text = f"おすすめの飲食店{('「' + shop_name + '」') if shop_name else ''}を見つけました！\n{share_url}"

    response_data = {
        "shop": ShopSerializer(shop).data if shop else None,
        "share_url": share_url,
        "share_text": share_text,
        "encoded_text": share_text.replace("\n", "%0A"),  # URLエンコード用
    }
    return Response(response_data)


# ============================================================
# Recommendations API
# ============================================================
def _shop_to_card(shop: Shop, reason: str = "") -> Dict[str, Any]:
    """Shop モデルをフロント表示用の dict (検索結果と同じ形) に変換する。"""
    url = shop.url or ""
    return {
        "id": shop.hotpepper_id,
        "name": shop.name,
        "photo": shop.photo_url,
        "genre": shop.genre,
        "budget": shop.budget,
        "address": shop.address,
        "lat": shop.lat,
        "lng": shop.lng,
        "url": url,
        "open": shop.open_hours,
        "source": "hotpepper" if "hotpepper" in url else "cache",
        "is_hotpepper": "hotpepper" in url,
        "is_google": "google.com/maps" in url,
        "distance_km": None,
        "walk_time_min": None,
        "reason": reason,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def impressions_view(request: Request) -> Response:
    """検索結果などで表示された店舗を記録する (レコメンドのシグナル)。"""
    assert request.user.is_authenticated
    shops = request.data.get("shops", [])
    if not isinstance(shops, list):
        return Response({"error": "shops must be a list"}, status=400)

    recorded = 0
    for shop_data in shops[:50]:  # 1リクエストあたり最大50件
        if not isinstance(shop_data, dict):
            continue
        shop = get_or_create_shop(shop_data)
        if not shop:
            continue
        imp, _ = ShopImpression.objects.get_or_create(user=request.user, shop=shop)
        ShopImpression.objects.filter(pk=imp.pk).update(count=F("count") + 1)
        recorded += 1

    return Response({"recorded": recorded})


@api_view(["GET"])
@permission_classes([AllowAny])
def recommendations_view(request: Request) -> Response:
    """
    パーソナライズされたレコメンドを返す。
    GET /api/restaurants/recommendations/?lat=..&lng=..

    - ログイン中: revisit (また行きたい) + discovery (おすすめ)。
      キャッシュが薄ければ現在地で HotPepper を叩いて補完する (ハイブリッド)。
    - 未ログイン / 履歴の薄いユーザー: popular (人気店ランキング) で補完する。
    """
    def to_float(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    lat = to_float(request.GET.get("lat"))
    lng = to_float(request.GET.get("lng"))

    # --- ゲスト: 人気店のみ ---
    if not request.user.is_authenticated:
        popular = [
            _shop_to_card(s, "みんなが注目しているお店")
            for s in get_popular_shops()
        ]
        return Response(
            {"mode": "guest", "revisit": [], "discovery": [], "popular": popular}
        )

    user = request.user
    affinity = compute_genre_affinity(user)

    # --- また行きたいお店 ---
    revisit_records = get_revisit_records(user)
    revisit = [
        _shop_to_card(
            r.shop, f"{r.visit_count}回来店したお店。また行きませんか？"
        )
        for r in revisit_records
    ]

    # --- あなたへのおすすめ (キャッシュ) ---
    known_ids = {r.shop.hotpepper_id for r in revisit_records}
    known_ids |= set(
        Favorite.objects.filter(user=user).values_list(
            "shop__hotpepper_id", flat=True
        )
    )
    discovery_shops = get_discovery_shops(user, affinity, known_ids)
    discovery = [
        _shop_to_card(
            s,
            f"好きな「{s.genre}」系のお店です" if s.genre else "あなたの好みに近いお店",
        )
        for s in discovery_shops
    ]

    # --- ハイブリッド: キャッシュが薄ければ現在地で新規検索して補完 ---
    top_genre = max(affinity, key=affinity.get) if affinity else None
    if len(discovery) < 4 and lat and lng and top_genre:
        code = HP_GENRE_NAME_TO_CODE.get(top_genre)
        if code:
            try:
                fresh = search_restaurants(lat=lat, lng=lng, range=4, genre=code)
                seen = {d["id"] for d in discovery} | known_ids
                for s in fresh:
                    if s.get("id") in seen:
                        continue
                    s["reason"] = f"近くにある「{top_genre}」のお店"
                    discovery.append(s)
                    seen.add(s["id"])
                    if len(discovery) >= 10:
                        break
            except Exception as e:
                logger.error(f"Recommendation fresh search failed: {e}")

    # --- 個人レコメンドが薄ければ人気店で補完 ---
    popular = []
    if len(revisit) + len(discovery) < 4:
        popular = [
            _shop_to_card(s, "いま人気のお店") for s in get_popular_shops()
        ]

    return Response(
        {
            "mode": "personal",
            "revisit": revisit,
            "discovery": discovery,
            "popular": popular,
        }
    )
