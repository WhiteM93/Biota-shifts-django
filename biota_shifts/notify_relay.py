"""Отправка уведомлений на внешний сервер бота (relay → Telegram)."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from biota_shifts.config import _config_str
from biota_shifts.notification_settings import load_notification_settings

logger = logging.getLogger(__name__)


def resolve_notify_relay_url(settings: dict | None = None) -> str:
    env_url = (_config_str("BIOTA_NOTIFY_RELAY_URL", "") or "").strip()
    if env_url:
        return env_url
    if settings:
        return str(settings.get("relay_url") or "").strip()
    return str(load_notification_settings().get("relay_url") or "").strip()


def resolve_notify_relay_secret(settings: dict | None = None) -> str:
    env_secret = (_config_str("BIOTA_NOTIFY_RELAY_SECRET", "") or "").strip()
    if env_secret:
        return env_secret
    if settings:
        return str(settings.get("relay_secret") or "").strip()
    return str(load_notification_settings().get("relay_secret") or "").strip()


def notify_relay_configured(settings: dict | None = None) -> bool:
    return bool(resolve_notify_relay_url(settings))


def notify_delivery_configured(settings: dict | None = None) -> bool:
    from biota_shifts.telegram_notify import telegram_notify_configured

    s = settings or load_notification_settings()
    if notify_relay_configured(s):
        return True
    return telegram_notify_configured(s)


def post_notify_relay(payload: dict, settings: dict | None = None, *, timeout: float = 30) -> dict:
    """POST JSON на сервер бота. Возвращает распарсенный ответ (если JSON)."""
    url = resolve_notify_relay_url(settings)
    if not url:
        raise ValueError("Не задан URL сервера уведомлений (BIOTA_NOTIFY_RELAY_URL)")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8", "User-Agent": "Biota-Notify/1.0"}
    secret = resolve_notify_relay_secret(settings)
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {"ok": True, "status": resp.status}
            try:
                out = json.loads(raw)
            except json.JSONDecodeError:
                return {"ok": True, "status": resp.status, "body": raw}
            if isinstance(out, dict) and out.get("ok") is False:
                msg = str(out.get("error") or out.get("message") or "relay error")
                raise RuntimeError(msg)
            return out if isinstance(out, dict) else {"ok": True, "result": out}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            msg = parsed.get("error") or parsed.get("message") or parsed.get("detail") or detail
        except json.JSONDecodeError:
            msg = detail or str(exc)
        raise RuntimeError(f"Сервер бота вернул HTTP {exc.code}: {msg}") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason or exc)
        raise RuntimeError(f"Не удалось достучаться до сервера бота ({url}): {reason}") from exc


def attendance_summary_relay_payload(
    summary,
    settings: dict | None = None,
    *,
    chat_ids: list[str] | None = None,
) -> dict:
    from biota_shifts.attendance_summary import format_summary_text

    cfg = load_notification_settings() if settings is None else settings
    target_chats = list(chat_ids) if chat_ids is not None else list(cfg.get("telegram_chat_ids") or [])
    return {
        "kind": "attendance_summary",
        "text": format_summary_text(summary),
        "chat_ids": target_chats,
        "meta": {
            "slot": summary.slot,
            "shift_date": summary.shift_date.isoformat(),
            "check_at": summary.check_at.isoformat(),
            "shift_label": summary.shift_label,
            "absent_count": summary.absent_count,
            "absent": [
                {
                    "emp_code": item.emp_code,
                    "label": item.label,
                    "department_name": item.department_name,
                    "shift_code": item.shift_code,
                    "first_punch_at": item.first_punch_at.isoformat() if item.first_punch_at else None,
                }
                for item in summary.absent
            ],
        },
    }


def send_summary_relay(
    summary,
    settings: dict | None = None,
    *,
    chat_ids: list[str] | None = None,
) -> int:
    """Отправить сводку на сервер бота. Возвращает 1 при успехе."""
    payload = attendance_summary_relay_payload(summary, settings, chat_ids=chat_ids)
    post_notify_relay(payload, settings)
    return 1


def send_notify_test(settings: dict | None = None) -> int:
    """Тест доставки: через relay или напрямую в Telegram."""
    s = settings or load_notification_settings()
    text = "Biota: тест уведомлений. Если видите это сообщение — доставка настроена верно."
    if notify_relay_configured(s):
        post_notify_relay({"kind": "test", "text": text, "chat_ids": list(s.get("telegram_chat_ids") or [])}, s)
        return 1
    from biota_shifts.telegram_notify import resolve_telegram_bot_token, send_telegram_broadcast

    token = resolve_telegram_bot_token(s)
    return send_telegram_broadcast(token, s.get("telegram_chat_ids") or [], text)
