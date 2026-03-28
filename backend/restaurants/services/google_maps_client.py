import requests
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Valid Places API (New) types for Searchable (Table A)
# Mapping HotPepper genres to Google Maps "includedTypes" valid for searchNearby
HP_GENRE_TO_GOOGLE_TYPES = {
    "G001": ["restaurant", "bar"], # 居酒屋 (izakaya_restaurant is not searchable)
    "G002": ["french_restaurant", "italian_restaurant"], # フランス・イタリア
    "G003": ["japanese_restaurant"], # 創作料理
    "G004": ["japanese_restaurant", "sushi_restaurant"], # 和食
    "G005": ["restaurant"], # 洋食
    "G006": ["italian_restaurant", "pizza_restaurant"], # イタリアン・フレンチ
    "G007": ["chinese_restaurant"], # 中華
    "G008": ["japanese_restaurant", "restaurant"], # 焼肉・ホルモン (yakiniku_restaurant is not searchable)
    "G009": ["restaurant"], # アジア・エスニック
    "G010": ["restaurant"], # 各国料理
    "G011": ["restaurant", "bar"], # カラオケ・パーティ
    "G012": ["bar"], # バー・カクテル
    "G013": ["japanese_restaurant", "restaurant"], # ラーメン (ramen_restaurant is not searchable)
    "G014": ["cafe", "bakery", "coffee_shop"], # カフェ・スイーツ
    "G015": ["restaurant"], # その他
}

def get_google_maps_api_key() -> str:
    return os.environ.get("GOOGLE_MAPS_API_KEY", "")

def genre_to_text(genre_code):
    """HotPepperジャンルコードを日本語に変換"""
    mapping = {
        "G001": "居酒屋", "G002": "ダイニングバー・バル", "G003": "創作料理",
        "G004": "和食", "G005": "洋食", "G006": "イタリアン・フレンチ",
        "G007": "中華", "G008": "焼肉・ホルモン", "G009": "アジア・エスニック料理",
        "G010": "各国料理", "G011": "カラオケ・パーティ", "G012": "バー・カクテル",
        "G013": "ラーメン", "G014": "カフェ・スイーツ", "G017": "韓国料理", "G015": "その他"
    }
    return mapping.get(genre_code, "")

def search_nearby_places(
    lat: float,
    lng: float,
    radius: int = 1000,
    keyword: Optional[str] = None,
    genre: Optional[str] = None,
    type: str = "restaurant"
) -> List[Dict[str, Any]]:
    """
    Google Places API (New) を使用して近隣の店舗を検索する
    """
    api_key = get_google_maps_api_key()
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY is not set.")
        return []

    # ジャンル指定がある場合は、より正確な searchText を優先する
    if keyword or genre:
        query = f"{keyword or ''} {genre_to_text(genre)}".strip()
        if query:
            return search_places_by_text(query, lat, lng, radius, genre)

    url = "https://places.googleapis.com/v1/places:searchNearby"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.photos,places.types,places.priceLevel"
    }
    
    # HPジャンルコードからGoogleのタイプを取得
    included_types = [type]
    if genre and genre in HP_GENRE_TO_GOOGLE_TYPES:
        included_types = HP_GENRE_TO_GOOGLE_TYPES[genre]

    body = {
        "includedTypes": included_types,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(lat),
                    "longitude": float(lng)
                },
                "radius": float(radius)
            }
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        places = data.get("places", [])
        return format_google_places(places, lat, lng)
            
    except Exception as e:
        logger.error(f"Google Places API error: {e}")
        # bodyの詳細をログに出力してみる
        logger.error(f"Post Body: {body}")
        return []

def search_places_by_text(
    query: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: int = 1000,
    genre: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Google Places API (New) Text Search
    """
    api_key = get_google_maps_api_key()
    url = "https://places.googleapis.com/v1/places:searchText"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.photos,places.types,places.priceLevel"
    }
    
    # HPジャンルコードからGoogleのタイプを取得
    included_type = "restaurant"
    if genre and genre in HP_GENRE_TO_GOOGLE_TYPES:
        included_type = HP_GENRE_TO_GOOGLE_TYPES[genre][0]

    body = {
        "textQuery": query,
        "languageCode": "ja",
        "maxResultCount": 20,
        "includedType": included_type
    }
    
    if lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": float(lat),
                    "longitude": float(lng)
                },
                "radius": float(radius)
            }
        }
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        places = data.get("places", [])
        return format_google_places(places, lat, lng)
    except Exception as e:
        logger.error(f"Google Places TextSearch API error: {e}")
        return []

def format_google_places(places: List[Dict[str, Any]], lat: float, lng: float) -> List[Dict[str, Any]]:
    from utils.location import calculate_distance, estimate_walk_time
    
    formatted = []
    for p in places:
        loc = p.get("location", {})
        plat = loc.get("latitude")
        plng = loc.get("longitude")
        
        dist = calculate_distance(lat, lng, plat, plng) if plat and plng else None
        walk_time = estimate_walk_time(dist) if dist else None
        
        # photo reference
        photo_url = None
        if p.get("photos"):
            ref = p["photos"][0].get("name")
            api_key = get_google_maps_api_key()
            photo_url = f"https://places.googleapis.com/v1/{ref}/media?maxHeightPx=400&maxWidthPx=400&key={api_key}"

        shop = {
            "id": f"google_{p.get('id')}",
            "name": p.get("displayName", {}).get("text", "Unknown"),
            "address": p.get("formattedAddress", ""),
            "lat": plat,
            "lng": plng,
            "google_rating": p.get("rating"),
            "google_user_rating_count": p.get("userRatingCount"),
            "url": f"https://www.google.com/maps/place/?q=place_id:{p.get('id')}",
            "photo": photo_url,
            "distance_km": round(dist, 2) if dist else None,
            "walk_time_min": walk_time,
            "source": "google",
            "is_google": True,
            "is_hotpepper": False,
            "budget": None,
            "genre": None # 後でマージ時に補完される可能性がある
        }
        
        # ジャンル名の推測 (typesから)
        types = p.get("types", [])
        if "japanese_restaurant" in types: shop["genre"] = "和食"
        elif "sushi_restaurant" in types: shop["genre"] = "寿司"
        elif "italian_restaurant" in types: shop["genre"] = "イタリアン"
        elif "french_restaurant" in types: shop["genre"] = "フレンチ"
        elif "chinese_restaurant" in types: shop["genre"] = "中華"
        elif "ramen_restaurant" in types: shop["genre"] = "ラーメン"
        elif "cafe" in types: shop["genre"] = "カフェ"
        elif "bar" in types: shop["genre"] = "バー"
        elif "izakaya_restaurant" in types or "izakaya" in types: shop["genre"] = "居酒屋"
        else: shop["genre"] = "飲食店"

        formatted.append(shop)
        
    return formatted
