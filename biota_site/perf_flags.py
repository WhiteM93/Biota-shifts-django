"""Флаги оптимизаций (пакет A и др.) — включаются через .env, по умолчанию выключены."""

from __future__ import annotations

import os


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def _env_or_package(env_name: str, package_a: bool) -> bool:
    raw = (os.getenv(env_name) or "").strip()
    if raw:
        return _truthy(raw)
    return package_a


def _users_store_cache_seconds(package_a: bool) -> int:
    raw = (os.getenv("BIOTA_PERF_USERS_STORE_CACHE_SEC") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            return 0
    return 60 if package_a else 0


def load_perf_settings() -> dict:
    package_a = _truthy(os.getenv("BIOTA_PERF_PACKAGE_A"))
    return {
        "BIOTA_PERF_PACKAGE_A": package_a,
        "BIOTA_PERF_MOBILE_GRAPH": _env_or_package("BIOTA_PERF_MOBILE_GRAPH", package_a),
        "BIOTA_PERF_DEFER_SCRIPTS": _env_or_package("BIOTA_PERF_DEFER_SCRIPTS", package_a),
        "BIOTA_PERF_USERS_STORE_CACHE_SEC": _users_store_cache_seconds(package_a),
    }
