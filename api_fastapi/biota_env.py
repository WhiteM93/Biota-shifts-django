"""Переменные BIOTA_DB_* с тем же профилем, что и в biota_shifts.config (MAIN/ALT)."""
from __future__ import annotations

import os


def _profile_env(prefix: str, key: str, default: str = "") -> str:
    profile = (os.getenv(f"{prefix}_PROFILE") or "").strip().upper()
    if profile:
        profile_key = f"{prefix}_{profile}_{key}"
        val = (os.getenv(profile_key) or "").strip()
        if val:
            return val
    return (os.getenv(f"{prefix}_{key}", default) or "").strip()


def biota_db_connection_kwargs() -> dict:
    connect_timeout_s = (_profile_env("BIOTA_DB", "CONNECT_TIMEOUT", "15") or "15").strip()
    try:
        connect_timeout = int(connect_timeout_s)
    except ValueError:
        connect_timeout = 15

    return {
        "host": _profile_env("BIOTA_DB", "HOST", "localhost"),
        "port": int(_profile_env("BIOTA_DB", "PORT", "5432") or "5432"),
        "dbname": _profile_env("BIOTA_DB", "NAME", "biota_db"),
        "user": _profile_env("BIOTA_DB", "USER", "biota_user"),
        "password": _profile_env("BIOTA_DB", "PASSWORD", ""),
        "connect_timeout": connect_timeout,
    }
