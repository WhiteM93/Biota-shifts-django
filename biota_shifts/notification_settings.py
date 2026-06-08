"""Настройки уведомлений администратора (JSON в корне проекта)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from biota_shifts.config import APP_DIR
from biota_shifts.emp_codes import normalize_emp_code, normalize_emp_codes_list

NOTIFICATION_SETTINGS_PATH = Path(APP_DIR) / ".biota_notification_settings.json"

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

DEFAULT_SETTINGS: dict = {
    "enabled": False,
    "morning_enabled": True,
    "morning_time": "08:20",
    "evening_enabled": True,
    "evening_time": "20:20",
    "telegram_bot_token": "",
    "telegram_chat_ids": [],
    "blacklist_emp_codes": [],
}


def _normalize_time(value: str, fallback: str) -> str:
    s = (value or "").strip()
    m = _TIME_RE.match(s)
    if not m:
        return fallback
    h, mi = int(m.group(1)), int(m.group(2))
    if h < 0 or h > 23 or mi < 0 or mi > 59:
        return fallback
    return f"{h:02d}:{mi:02d}"


def _normalize_chat_ids(values: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        s = str(raw).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def parse_chat_ids_text(text: str) -> list[str]:
    """Одна строка — один chat_id; также поддерживается разделение запятой."""
    parts: list[str] = []
    for line in (text or "").replace(",", "\n").splitlines():
        s = line.strip()
        if s:
            parts.append(s)
    return _normalize_chat_ids(parts)


def load_notification_settings() -> dict:
    if not NOTIFICATION_SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        raw = json.loads(NOTIFICATION_SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            return dict(DEFAULT_SETTINGS)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)

    out = dict(DEFAULT_SETTINGS)
    out["enabled"] = bool(raw.get("enabled", out["enabled"]))
    out["morning_enabled"] = bool(raw.get("morning_enabled", out["morning_enabled"]))
    out["evening_enabled"] = bool(raw.get("evening_enabled", out["evening_enabled"]))
    out["morning_time"] = _normalize_time(str(raw.get("morning_time") or ""), out["morning_time"])
    out["evening_time"] = _normalize_time(str(raw.get("evening_time") or ""), out["evening_time"])
    out["telegram_bot_token"] = str(raw.get("telegram_bot_token") or "").strip()
    out["telegram_chat_ids"] = _normalize_chat_ids(raw.get("telegram_chat_ids") or [])
    out["blacklist_emp_codes"] = normalize_emp_codes_list(raw.get("blacklist_emp_codes") or [])
    return out


def save_notification_settings(data: dict) -> dict:
    current = load_notification_settings()
    current["enabled"] = bool(data.get("enabled", current["enabled"]))
    current["morning_enabled"] = bool(data.get("morning_enabled", current["morning_enabled"]))
    current["evening_enabled"] = bool(data.get("evening_enabled", current["evening_enabled"]))
    current["morning_time"] = _normalize_time(str(data.get("morning_time") or ""), current["morning_time"])
    current["evening_time"] = _normalize_time(str(data.get("evening_time") or ""), current["evening_time"])
    if "telegram_bot_token" in data:
        token = str(data.get("telegram_bot_token") or "").strip()
        if token:
            current["telegram_bot_token"] = token
    if "telegram_chat_ids" in data:
        current["telegram_chat_ids"] = _normalize_chat_ids(data.get("telegram_chat_ids") or [])
    if "blacklist_emp_codes" in data:
        current["blacklist_emp_codes"] = normalize_emp_codes_list(data.get("blacklist_emp_codes") or [])
    NOTIFICATION_SETTINGS_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def blacklist_set(settings: dict | None = None) -> set[str]:
    s = settings or load_notification_settings()
    return {normalize_emp_code(c) for c in (s.get("blacklist_emp_codes") or []) if normalize_emp_code(c)}


def telegram_token_configured(settings: dict | None = None) -> bool:
    from biota_shifts.telegram_notify import resolve_telegram_bot_token

    s = settings or load_notification_settings()
    return bool(resolve_telegram_bot_token(s))
