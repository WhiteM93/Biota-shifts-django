"""Простой rate limit по IP для публичных auth-страниц (без внешних зависимостей)."""

from __future__ import annotations

import time
from typing import NamedTuple

from django.core.cache import caches


class RateLimitResult(NamedTuple):
    exceeded: bool
    retry_after: int
    limit_key: str


def get_client_ip(request) -> str:
    """IP клиента за nginx (X-Forwarded-For / X-Real-IP) или напрямую."""
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    x_real = (request.META.get("HTTP_X_REAL_IP") or "").strip()
    if x_real:
        return x_real
    return (request.META.get("REMOTE_ADDR") or "").strip() or "unknown"


def _increment_counter(cache_key: str, window_seconds: int) -> tuple[int, int]:
    """Возвращает (текущий счётчик, секунд до сброса окна)."""
    cache = caches["ratelimit"]
    now = time.time()
    data = cache.get(cache_key)
    if not data or now - float(data.get("start", 0)) >= window_seconds:
        cache.set(cache_key, {"count": 1, "start": now}, window_seconds)
        return 1, window_seconds

    count = int(data.get("count", 0)) + 1
    elapsed = now - float(data["start"])
    ttl = max(int(window_seconds - elapsed), 1)
    cache.set(cache_key, {"count": count, "start": data["start"]}, ttl)
    return count, ttl


def check_rate_limit(
    *,
    scope: str,
    client_id: str,
    max_requests: int,
    window_seconds: int,
) -> RateLimitResult:
    """True в exceeded, если лимит превышен."""
    if max_requests <= 0 or window_seconds <= 0:
        return RateLimitResult(False, 0, "")

    cache_key = f"rl:{scope}:{client_id}"
    count, retry_after = _increment_counter(cache_key, window_seconds)
    if count > max_requests:
        return RateLimitResult(True, retry_after, scope)
    return RateLimitResult(False, 0, "")


def registration_rate_limits(
    *,
    client_id: str,
    method: str,
    burst_max: int,
    burst_window: int,
    post_max: int,
    post_window: int,
) -> RateLimitResult:
    """Общий лимит на /accounts/register/* и отдельный — на POST."""
    burst = check_rate_limit(
        scope="register_burst",
        client_id=client_id,
        max_requests=burst_max,
        window_seconds=burst_window,
    )
    if burst.exceeded:
        return burst

    if (method or "").upper() == "POST" and post_max > 0:
        post = check_rate_limit(
            scope="register_post",
            client_id=client_id,
            max_requests=post_max,
            window_seconds=post_window,
        )
        if post.exceeded:
            return post

    return RateLimitResult(False, 0, "")
