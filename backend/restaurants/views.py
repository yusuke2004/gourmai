from typing import List, Dict, Any, Optional
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.request import Request
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
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
    SearchHistory,
)
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

logger = logging.getLogger(__name__)

HP_GENRE_NAMES = {
    "G001": "居酒屋", "G002": "ダイニングバー・バル", "G003": "創作料理",
    "G004": "和食", "G005": "洋食", "G006": "イタリアン・フレンチ",
    "G007": "中華", "G008": "焼肉・ホルモン", "G009": "アジア・エスニック料理",
    "G010": "各国料理", "G011": "カラオケ・パーティ", "G012": "バー・カクテル",
    "G013": "ラーメン", "G014": "カフェ・スイーツ", "G017": "韓国料理", "G015": "その他"
}


@api_view(["GET"])
def ping(request: Request) -> Response:
    return Response({"ok": True, "message": "API is working"})


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

    shops = []
    
    # 1. HotPepper Search
    try:
        if lat and lng:
            all_hp_shops = search_restaurants(
                lat=lat, lng=lng, range=range_val, budget=None, 
                genre=genre, keyword=keyword, people=people, 
                free_drink=hp_free_drink, free_food=hp_free_food
            )
        else:
            all_hp_shops = search_by_keyword(
                keyword=keyword or "", range=range_val, budget=None, 
                genre=genre, people=people, 
                free_drink=hp_free_drink, free_food=hp_free_food
            )
        
        # Local filtering for HP budget codes
        if budget_codes_list:
            hp_shops = [s for s in all_hp_shops if s.get("raw_budget_code") in budget_codes_list]
        else:
            hp_shops = all_hp_shops
        
        shops.extend(hp_shops)
    except Exception as e:
        logger.error(f"HotPepper Search Error: {e}")

    # 2. Google Maps Search
    try:
        if lat and lng:
            google_shops = search_nearby_places(lat, lng, radius=radius, keyword=keyword, genre=genre)
            shops.extend(google_shops)
        elif keyword:
            google_shops = search_places_by_text(keyword, lat, lng, radius=radius, genre=genre)
            shops.extend(google_shops)
    except Exception as e:
        logger.error(f"Google Maps Search Error: {e}")

    # 3. マージと重複排除 (名前と距離で判定)
    def normalize_name(n):
        if not n: return ""
        # 小文字化、空白、記号除去
        import re
        n = n.lower()
        n = re.sub(r'[ 　\(\)（）-\.\[\]]', '', n)
        # よくある末尾の店舗表現をカット
        for suffix in ["店", "駅前", "成城店", "新宿店", "池袋店", "本店", "分店"]:
            if n.endswith(suffix) and len(n) > len(suffix) + 1:
                n = n[:-len(suffix)]
        return n

    merged_shops = []
    
    for s in shops:
        s["is_hotpepper"] = (s.get("source") == "hotpepper")
        s["is_google"] = (s.get("source") == "google")
        
        found = False
        s_name = s.get("name", "")
        norm = normalize_name(s_name)
        s_lat = s.get("lat")
        s_lng = s.get("lng")
        
        for existing in merged_shops:
            e_norm = normalize_name(existing.get("name", ""))
            e_lat = existing.get("lat")
            e_lng = existing.get("lng")
            
            # (1) 名前が似ている (どちらかがどちらかを含む & 3文字以上)
            name_match = (norm in e_norm or e_norm in norm) and len(norm) >= 3 and len(e_norm) >= 3
            
            # (2) 位置に基づく判定
            dist = calculate_distance(s_lat, s_lng, e_lat, e_lng)
            
            # 50m以内で、名前に共通のキーワード(2文字以上)があるか、非常に近い(20m)なら同一とみなす
            shared_keywords = any((k in e_norm and len(k) >= 2) for k in [norm[i:i+2] for i in range(len(norm)-1)])
            pos_match = dist is not None and (
                (dist < 0.05 and shared_keywords) or
                (dist < 0.02 and (norm[:2] == e_norm[:2] or norm[-2:] == e_norm[-2:]))
            )

            if name_match or pos_match: 
                # マージ処理
                if s.get("google_rating"):
                    existing["google_rating"] = s["google_rating"]
                    existing["google_user_rating_count"] = s.get("google_user_rating_count", 0)
                    existing["is_google"] = True
                if s.get("url") and "hotpepper.jp" in s.get("url"):
                    existing["url"] = s["url"]
                    existing["is_hotpepper"] = True
                    if s.get("photo"): existing["photo"] = s["photo"]
                found = True
                break
        
        if not found:
            merged_shops.append(s)

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
    
    #@api_view(["POST"])
def natural_search(request: Request) -> Response:
    """
    Geminiを使用した自然言語検索
    POST /api/restaurants/natural-search
    """
    query = request.data.get("query")
    if not query:
        return Response({"error": "Query is required"}, status=400)

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
def search(request: Request) -> Response:
    """
    店舗検索 (HotPepper + Google Maps)
    GET /api/restaurants/search
    """
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

    shops = _perform_combined_search(
        lat=float(lat_param) if lat_param else None,
        lng=float(lng_param) if lng_param else None,
        range_val=int(range_param) if range_param.isdigit() else 5,
        budget_min=budget_min,
        budget_max=budget_max,
        genre=genre,
        keyword=keyword,
        people=people,
        free_drink=free_drink,
        free_food=free_food,
        user=request.user,
        original_query_params=dict(request.GET)
    )
    
    # 検索ワードやジャンル指定がある場合、AI評価を追加
    if shops and (keyword or genre):
        ai_query = f"{keyword or ''} {genre or ''}".strip()
        shops = generate_ai_recommendation(ai_query, shops)
        
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
@permission_classes([IsAuthenticated])
def admin_stats_view(request: Request) -> Response:
    """
    管理者用統計データ取得
    GET /api/restaurants/admin/stats
    """
    if request.user.email != "test@gmail.com":
        return Response({"error": "Forbidden"}, status=403)
    
    # ユーザー統計
    users = User.objects.all()
    total_users = users.count()
    user_emails = [u.email for u in users if u.email]
    
    # 検索統計
    histories = SearchHistory.objects.order_by('-created_at')[:500]
    
    budget_stats = {}
    people_stats = {}
    
    for h in histories:
        params = h.query_params
        if not isinstance(params, dict):
            continue
            
        # budget_max
        b_max = params.get('budget_max')
        if isinstance(b_max, list) and len(b_max) > 0: b_max = b_max[0]
        if b_max:
            # マッピングがあれば変換
            budget_stats[b_max] = budget_stats.get(b_max, 0) + 1
        
        # people
        p = params.get('people')
        if isinstance(p, list) and len(p) > 0: p = p[0]
        if p:
            # 人数ごとの集計
            people_stats[p] = people_stats.get(p, 0) + 1
            
    return Response({
        "total_users": total_users,
        "user_emails": user_emails,
        "budget_stats": budget_stats,
        "people_stats": people_stats
    })


# ============================================================
# Auth Endpoints
# ============================================================
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """ユーザー登録"""
    ser = RegisterSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    email = ser.validated_data["email"]
    password = ser.validated_data["password"]
    display_name = ser.validated_data.get("display_name", "")

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
def login_view(request):
    """ログイン"""
    ser = LoginSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    email = ser.validated_data["email"]
    password = ser.validated_data["password"]

    # Check if user exists
    if not User.objects.filter(username=email).exists() and not User.objects.filter(email=email).exists():
        return Response(
            {"error": "user_not_found", "message": "このメールアドレスは登録されていません。新規登録してください。"},
            status=404
        )

    user = authenticate(request, username=email, password=password)
    if not user:
        return Response(
            {"error": "invalid_password", "message": "パスワードが正しくありません"}, status=401
        )

    login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
def logout_view(request: Request) -> Response:
    """ログアウト"""
    logout(request)
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request: Request) -> Response:
    """現在のユーザー情報"""
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
    shop, _ = Shop.objects.update_or_create(
        hotpepper_id=shop_id,
        defaults={
            "name": shop_data.get("name", ""),
            "photo_url": shop_data.get("photo", ""),
            "genre": shop_data.get("genre", ""),
            "budget": shop_data.get("budget", ""),
            "address": shop_data.get("address", ""),
            "lat": shop_data.get("lat"),
            "lng": shop_data.get("lng"),
            "url": shop_data.get("url", ""),
            "open_hours": shop_data.get("open", ""),
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
def comments_view(request: Request, shop_id: str) -> Response:
    """GET: 特定店舗の全コメント, POST: コメント投稿"""
    try:
        shop = Shop.objects.get(hotpepper_id=shop_id)
    except Shop.DoesNotExist:
        if request.method == "GET":
            return Response([])
        return Response({"error": "Shop not found"}, status=404)

    if request.method == "GET":
        comments = Comment.objects.filter(shop=shop)
        return Response(CommentReadSerializer(comments, many=True).data)

    elif request.method == "POST":
        text = request.data.get("text", "").strip()
        if not text:
            return Response({"error": "Comment text is required"}, status=400)

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
        )
        return Response(CommentReadSerializer(comment).data, status=201)
    return Response({"error": "Method not allowed"}, status=405)


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
        text = request.data.get("text", "").strip()
        if not text:
            return Response({"error": "Comment text is required"}, status=400)
        comment.text = text
        comment.save()
        return Response(CommentReadSerializer(comment).data)

    elif request.method == "DELETE":
        comment.delete()
        return Response({"ok": True})
    return Response({"error": "Method not allowed"}, status=405)


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
