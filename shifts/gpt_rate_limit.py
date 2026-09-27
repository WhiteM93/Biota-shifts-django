"""Общий rate-limit для вызовов YandexGPT (не для админа)."""
from __future__ import annotations

from django.core.cache import cache

from biota_shifts.auth import _is_admin


def gpt_rate_limit_allow(username: str, *, scope: str, cooldown_sec: int = 60) -> tuple[bool, int]:
    """
    Разрешить запрос. Админ — всегда да.
    Остальные: не чаще 1 раза за cooldown_sec в рамках scope.
    Возвращает (ok, retry_after_sec).
    """
    u = (username or "").strip()
    if _is_admin(u):
        return True, 0
    wait = max(1, int(cooldown_sec or 60))
    key = f"gpt_rl:{scope}:{u or 'anon'}"
    if cache.get(key):
        return False, wait
    cache.set(key, 1, timeout=wait)
    return True, 0
