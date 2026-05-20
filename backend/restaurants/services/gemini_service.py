import os
import json
import logging
from typing import Dict, Any, List, Optional
import google.genai as genai
from google.genai import types

from utils.cache import cached

logger = logging.getLogger(__name__)

# 同一クエリは Gemini を叩かずキャッシュ (LLM コスト削減)
_INTENT_CACHE_TTL = 60 * 60 * 6  # 6 時間

def get_gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")

def get_client():
    api_key = get_gemini_api_key()
    if not api_key:
        return None
    # google.genai Client
    return genai.Client(api_key=api_key)

def parse_search_intent(query: str) -> Dict[str, Any]:
    """
    ユーザーの自然言語入力から検索パラメータを抽出する。
    同一クエリは Gemini を叩かずキャッシュから返す。
    """
    if not query:
        return {}

    client = get_client()
    if not client:
        logger.warning("GEMINI_API_KEY is not set.")
        return {}

    def _call() -> Dict[str, Any]:
        prompt = f"""
        ユーザーの飲食店検索クエリから以下の要素を抽出し、JSON形式で返してください。

        クエリ: "{query}"

        抽出項目:
        - location: 地名、最寄り駅、ビル名など (例: "池袋")
        - keyword: 具体的な料理名、特徴、こだわり条件 (例: "個室 焼き鳥")
        - genre: 飲食店ジャンル (和食, 居酒屋, イタリアン, 焼肉, ... から選択)
        - budget_min_yen: 予算の下限 (数値のみ, 例: 2000)
        - budget_max_yen: 予算の上限 (数値のみ, 例: 4000)
        - people: 人数 (数値のみ, 例: 4)

        不明な項目は null にしてください。
        """

        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini intent parse error: {e}")
            return {}

    return cached("gemini:intent", query.strip().lower(), _INTENT_CACHE_TTL, _call) or {}

def generate_ai_recommendation(query: str, shops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    ユーザーのクエリに基づいて各店舗のおすすめ理由を生成し、おすすめ順にソートする
    """
    client = get_client()
    if not client or not query or not shops:
        return shops

    # おすすめ対象の情報を抽出 (30件まで)
    target_shops = shops[:30]
    shop_info = [{ "id": s["id"], "name": s["name"], "genre": s["genre"], "budget": s["budget"] } for s in target_shops]
    
    prompt = f"""
    ユーザーの今の気分や条件に基づいて、店舗リストを並べ替え、15〜40文字程度の「おすすめ理由」を生成してください。
    和食やイタリアンなどのジャンルが指定されている場合は、そのジャンルを優先してください。
    
    検索ワード・気分: "{query}"
    
    店舗リスト:
    {json.dumps(shop_info, ensure_ascii=False)}
    
    出力形式:
    [
        {{
            "id": "（ここには必ずリストにある実際の店舗IDを入れてください）",
            "ai_reason": "ユーザーの条件にどう合っているかの簡潔な理由。例：『個室完備で、落ち着いてお酒を楽しめる雰囲気が条件にぴったりです』"
        }},
        ...
    ]
    
    必ず店舗リストにある実際のIDを使用し、JSON形式のリストのみを返してください。
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        text = response.text.strip()
        recs = json.loads(text)
        
        # ソート (recsの順序に従う)
        sorted_shops = []
        found_ids = set()
        for r in recs:
            s_id = r.get("id")
            if s_id in found_ids: continue
            shop = next((s for s in target_shops if s["id"] == s_id), None)
            if shop:
                shop["ai_reason"] = r.get("ai_reason", "")
                sorted_shops.append(shop)
                found_ids.add(s_id)
        
        # 残りの店舗を統合
        # AIが返さなかった店舗もリストに残す
        remaining = [s for s in shops if s["id"] not in found_ids]
        sorted_shops.extend(remaining)
        
        # originalIndexを再割り当て
        for i, s in enumerate(sorted_shops):
            s["originalIndex"] = i

        return sorted_shops
    except Exception as e:
        logger.error(f"Gemini Recommend error: {e}")
        return shops
