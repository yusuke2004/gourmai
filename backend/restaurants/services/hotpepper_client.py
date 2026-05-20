import os
import logging
import requests
from typing import Dict, Any, List, Optional
from utils.location import calculate_distance, estimate_walk_time
from utils.cache import cached

logger = logging.getLogger(__name__)

# キャッシュ TTL
_MASTER_TTL = 60 * 60 * 24  # 予算 / ジャンルマスタは1日
_SEARCH_TTL = 60 * 5         # 検索結果は 5 分

class HotPepperAPIError(Exception):
    """HotPepper APIからエラーが返された場合のカスタム例外"""
    pass

def get_api_key() -> str:
    """環境変数からAPIキーを取得する"""
    api_key = os.environ.get("HOTPEPPER_API_KEY")
    if not api_key:
        logger.warning("HOTPEPPER_API_KEY is not set in environment variables.")
    return api_key or ""

def get_budget_master() -> List[Dict[str, Any]]:
    """予算マスタを取得する (1日キャッシュ)"""
    def _call() -> List[Dict[str, Any]]:
        url = "http://webservice.recruit.co.jp/hotpepper/budget/v1/"
        params = {"key": get_api_key(), "format": "json"}
        try:
            response = requests.get(url, params=params, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            if "results" in data and "error" in data["results"]:
                errors = data["results"]["error"]
                error_msgs = ", ".join([e.get("message", "") for e in errors])
                raise HotPepperAPIError(f"API Error: {error_msgs}")
            return data.get("results", {}).get("budget", [])
        except Exception as e:
            logger.error(f"Failed to fetch budget master: {e}")
            return []

    return cached("hp:budget_master", "v1", _MASTER_TTL, _call) or []

def get_genre_master() -> List[Dict[str, Any]]:
    """ジャンルマスタを取得する (1日キャッシュ)"""
    def _call() -> List[Dict[str, Any]]:
        url = "http://webservice.recruit.co.jp/hotpepper/genre/v1/"
        params = {"key": get_api_key(), "format": "json"}
        try:
            response = requests.get(url, params=params, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            if "results" in data and "error" in data["results"]:
                errors = data["results"]["error"]
                error_msgs = ", ".join([e.get("message", "") for e in errors])
                raise HotPepperAPIError(f"API Error: {error_msgs}")
            return data.get("results", {}).get("genre", [])
        except Exception as e:
            logger.error(f"Failed to fetch genre master: {e}")
            return []

    return cached("hp:genre_master", "v1", _MASTER_TTL, _call) or []

def search_restaurants(
    lat: float,
    lng: float,
    range: int = 3,
    budget: Optional[str] = None,
    genre: Optional[str] = None,
    keyword: Optional[str] = None,
    people: Optional[int] = None,
    free_drink: Optional[str] = None,
    free_food: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    現在地と条件から店舗を検索し、パースして返す
    
    Args:
        lat (float): 緯度
        lng (float): 経度
        range (int): 検索範囲 (1:300m, 2:500m, 3:1000m, 4:2000m, 5:3000m)
        budget (str, optional): 予算コード
        genre (str, optional): ジャンルコード
        keyword (str, optional): 検索キーワード
        people (int, optional): 人数
        free_drink (str, optional): 飲み放題フラグ ('1')
        free_food (str, optional): 食べ放題フラグ ('1')
        
    Returns:
        List[Dict[str, Any]]: 店舗情報のリスト
    """
    url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
    api_key = get_api_key()
    
    if not api_key:
        logger.warning("Returning empty array because HOTPEPPER_API_KEY is missing.")
        return []

    params: Dict[str, Any] = {
        "key": api_key,
        "lat": lat,
        "lng": lng,
        "range": range, # Changed from range_val to range as per original code
        "format": "json",
        "count": 100,  # 取得件数（最大100）
        "order": 4    # 4: おすめ順
    }

    if genre:
        params["genre"] = genre
    if budget:
        params["budget"] = budget
    if keyword:
        params["keyword"] = keyword
    if people:
        params["party_capacity"] = people
    if free_drink:
        params["free_drink"] = free_drink
    if free_food:
        params["free_food"] = free_food

    try:
        response = requests.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        if "results" in data and "error" in data["results"]:
            errors = data["results"]["error"]
            error_msgs = ", ".join([e.get("message", "") for e in errors])
            logger.error(f"HotPepper API Result Error: {error_msgs}")
            raise HotPepperAPIError(f"API Error: {error_msgs}")
            
        shops = data.get("results", {}).get("shop", [])
        
        # フィルタリング
        filtered_shops = []
        for shop in shops:
            shop_name = shop.get("name", "")
            shop_catch = shop.get("catch", "")
            shop_address = shop.get("address", "")
            
            # 1. 閉店店店舗等の除外
            if "閉店" in shop_name or "閉店" in shop_catch:
                continue

            # 2. キーワードフィルタ (複数単語対応)
            if keyword:
                text_to_search = f"{shop_name} {shop_address} {shop_catch} {shop.get('access', '')}".lower()
                query_words = keyword.lower().split()
                if not all(word in text_to_search for word in query_words):
                    continue

            # 3. ジャンル厳密一致チェック
            if genre:
                shop_genre_code = shop.get("genre", {}).get("code", "")
                if shop_genre_code != genre:
                    continue
            
            filtered_shops.append(shop)

        # 整形して返す
        formatted_shops = []
        for idx, shop in enumerate(filtered_shops):
            shop_lat = float(shop.get("lat", 0))
            shop_lng = float(shop.get("lng", 0))
            
            # 追加要件: 距離計算と徒歩時間推定
            distance_km = calculate_distance(lat, lng, shop_lat, shop_lng)
            walk_time_min = estimate_walk_time(distance_km)
            
            formatted_shops.append({
                "source": "hotpepper",
                "originalIndex": idx, # フロントエンドで「おすすめ順」に戻す用
                "id": shop.get("id", ""),
                "name": shop.get("name", ""),
                "address": shop.get("address", ""),
                "genre": shop.get("genre", {}).get("name", "") if isinstance(shop.get("genre"), dict) else "",
                "budget": shop.get("budget", {}).get("name", "") if isinstance(shop.get("budget"), dict) else "",
                "raw_budget_code": shop.get("budget", {}).get("code", "") if isinstance(shop.get("budget"), dict) else "",
                "lat": shop_lat,
                "lng": shop_lng,
                "photo": (
                    shop.get("photo", {}).get("pc", {}).get("l", "")
                    or shop.get("photo", {}).get("mobile", {}).get("l", "")
                ) if isinstance(shop.get("photo"), dict) else "",
                "url": shop.get("urls", {}).get("pc", "") if isinstance(shop.get("urls"), dict) else "",
                "access": shop.get("access", ""),
                "distance_km": round(distance_km, 2),
                "walk_time_min": walk_time_min
            })
            
        return formatted_shops

    except requests.exceptions.Timeout:
        logger.error("HotPepper API request timed out")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"HotPepper API request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in search_restaurants: {e}")
        return []


def search_by_keyword(
    keyword: str,
    range: int = 3,
    budget: Optional[str] = None,
    genre: Optional[str] = None,
    people: Optional[int] = None,
    free_drink: Optional[str] = None,
    free_food: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    キーワード（駅名など）で店舗を検索し、パースして返す
    lat/lngなしで検索する場合に使用
    """
    url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
    api_key = get_api_key()
    
    if not api_key:
        logger.warning("Returning empty array because HOTPEPPER_API_KEY is missing.")
        return []

    params: Dict[str, Any] = {
        "key": api_key,
        "keyword": keyword,
        "format": "json",
        "count": 100,
        "order": 4
    }

    if genre:
        params["genre"] = genre
    if budget:
        params["budget"] = budget
    if people:
        params["party_capacity"] = people
    if free_drink:
        params["free_drink"] = free_drink
    if free_food:
        params["free_food"] = free_food

    try:
        response = requests.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        if "results" in data and "error" in data["results"]:
            errors = data["results"]["error"]
            error_msgs = ", ".join([e.get("message", "") for e in errors])
            raise HotPepperAPIError(f"API Error: {error_msgs}")
            
        shops = data.get("results", {}).get("shop", [])
        
        filtered_shops = []
        for shop in shops:
            shop_name = shop.get("name", "")
            shop_catch = shop.get("catch", "")
            
            if "閉店" in shop_name or "閉店" in shop_catch:
                continue

            # キーワードフィルタ (複数単語対応)
            if keyword:
                search_targets = [shop_name, shop_catch, shop.get("address", ""), shop.get("access", ""), shop.get("genre", {}).get("name", "")]
                text_to_search = " ".join([t for t in search_targets if t]).lower()
                query_words = keyword.lower().split()
                if not all(word in text_to_search for word in query_words):
                    continue

            # ジャンル厳密一致
            if genre:
                shop_genre_code = shop.get("genre", {}).get("code", "")
                if shop_genre_code != genre:
                    continue
            
            filtered_shops.append(shop)

        formatted_shops = []
        for idx, shop in enumerate(filtered_shops):
            shop_lat = float(shop.get("lat", 0))
            shop_lng = float(shop.get("lng", 0))
            
            formatted_shops.append({
                "source": "hotpepper",
                "originalIndex": idx,
                "id": shop.get("id", ""),
                "name": shop.get("name", ""),
                "address": shop.get("address", ""),
                "genre": shop.get("genre", {}).get("name", "") if isinstance(shop.get("genre"), dict) else "",
                "budget": shop.get("budget", {}).get("name", "") if isinstance(shop.get("budget"), dict) else "",
                "raw_budget_code": shop.get("budget", {}).get("code", "") if isinstance(shop.get("budget"), dict) else "",
                "lat": shop_lat,
                "lng": shop_lng,
                "photo": (
                    shop.get("photo", {}).get("pc", {}).get("l", "")
                    or shop.get("photo", {}).get("mobile", {}).get("l", "")
                ) if isinstance(shop.get("photo"), dict) else "",
                "url": shop.get("urls", {}).get("pc", "") if isinstance(shop.get("urls"), dict) else "",
                "access": shop.get("access", ""),
                "distance_km": None,
                "walk_time_min": None
            })
            
        return formatted_shops

    except requests.exceptions.Timeout:
        logger.error("HotPepper API request timed out (keyword mode)")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"HotPepper API request failed (keyword mode): {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in search_by_keyword: {e}")
        return []
