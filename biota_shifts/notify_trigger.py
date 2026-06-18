"""Ручной вызов сводки СКУД (API для Telegram-бота)."""
from __future__ import annotations

from datetime import datetime

from biota_shifts.attendance_summary import (
    SLOT_EVENING,
    SLOT_MORNING,
    format_summary_text,
    load_attendance_summary_from_db,
    send_summary_telegram,
)
from biota_shifts.config import _config_str
from biota_shifts.constants import MSK
from biota_shifts.notification_settings import load_notification_settings, parse_chat_ids_text
from biota_shifts.notify_relay import notify_delivery_configured, resolve_notify_relay_secret


def resolve_trigger_chat_ids(settings: dict | None = None) -> list[str]:
    env = (_config_str("BIOTA_NOTIFY_TRIGGER_CHAT_IDS", "") or "").strip()
    if env:
        return parse_chat_ids_text(env.replace(";", ","))
    s = settings or load_notification_settings()
    return list(s.get("telegram_chat_ids") or [])


def chat_id_allowed(chat_id: str, settings: dict | None = None) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    allowed = resolve_trigger_chat_ids(settings)
    if not allowed:
        return True
    return cid in allowed


def verify_notify_api_bearer(request) -> bool:
    secret = resolve_notify_relay_secret()
    if not secret:
        return False
    auth = (request.headers.get("Authorization") or "").strip()
    return auth == f"Bearer {secret}"


def resolve_slot_from_request(slot_raw: str | None) -> str:
    slot = (slot_raw or "auto").strip().lower()
    if slot in (SLOT_MORNING, SLOT_EVENING):
        return slot
    if slot in ("auto", "", "now"):
        hour = datetime.now(MSK).hour
        return SLOT_MORNING if hour < 15 else SLOT_EVENING
    raise ValueError(f"Неизвестный slot: {slot_raw}")


def trigger_attendance_summary(
    slot: str,
    *,
    chat_id: str | None = None,
    settings: dict | None = None,
    send: bool = True,
) -> dict:
    cfg = load_notification_settings() if settings is None else settings
    summary = load_attendance_summary_from_db(slot, settings=cfg)
    text = format_summary_text(summary)
    out = {
        "ok": True,
        "slot": slot,
        "text": text,
        "absent_count": summary.absent_count,
        "delivered": False,
    }
    if not send:
        return out
    if not notify_delivery_configured(cfg):
        out["ok"] = False
        out["error"] = "Доставка не настроена (relay или Telegram)"
        return out
    chat_ids = [str(chat_id).strip()] if chat_id else None
    send_summary_telegram(summary, cfg, chat_ids=chat_ids)
    out["delivered"] = True
    return out
