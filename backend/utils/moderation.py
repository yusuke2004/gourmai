"""コメントなどユーザー投稿テキストの簡易モデレーション。"""
from __future__ import annotations

import re

from django.conf import settings


_URL_RE = re.compile(r"https?://", re.IGNORECASE)


def get_client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_user_agent(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:300]


def contains_ng_word(text: str) -> str | None:
    """NG ワードが含まれていれば、検出した語を返す。なければ None。"""
    words = getattr(settings, "NG_WORDS", []) or []
    lower = text.lower()
    for w in words:
        if w and w.lower() in lower:
            return w
    return None


def looks_like_spam(text: str) -> bool:
    """超軽量のヒューリスティック。誤検知を避けるため緩めに。"""
    if not text:
        return False
    # URL が 2個以上 ＝ ほぼ広告
    if len(_URL_RE.findall(text)) >= 2:
        return True
    # 同じ文字の連続が 12 文字以上
    if re.search(r"(.)\1{11,}", text):
        return True
    return False


def sanitize_text(text: str, max_length: int | None = None) -> str:
    """前後空白除去・連続改行を 2 行までに丸める。最大長で切る。"""
    text = (text or "").strip()
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if max_length is not None and len(text) > max_length:
        text = text[:max_length]
    return text
