"""キャッシュキー生成と簡易ラッパ。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from django.core.cache import cache


def make_key(prefix: str, payload: Any) -> str:
    """payload を安定した文字列化 → SHA1 してキーを作る。"""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def cached(prefix: str, payload: Any, ttl: int, builder: Callable[[], Any]) -> Any:
    """payload に応じたキャッシュ。miss なら builder() を呼んで保存。"""
    key = make_key(prefix, payload)
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = builder()
    if value is not None:
        cache.set(key, value, ttl)
    return value
