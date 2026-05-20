"""django-ratelimit が無い環境では no-op になるラッパ。

本番では requirements.txt 経由で django-ratelimit が入っていれば実際に動作する。
ローカル / CI で未インストールでもアプリが起動できるようにするための逃げ道。
"""
from __future__ import annotations

try:
    from django_ratelimit.decorators import ratelimit as _ratelimit  # type: ignore
    HAS_RATELIMIT = True
except Exception:  # ImportError or other  # pragma: no cover - defensive
    HAS_RATELIMIT = False


def ratelimit(*args, **kwargs):
    """django_ratelimit と同じシグネチャ。未インストール時は no-op。"""
    if HAS_RATELIMIT:
        return _ratelimit(*args, **kwargs)

    def decorator(view_func):
        return view_func

    return decorator
