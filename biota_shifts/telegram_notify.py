"""Отправка сообщений через Telegram Bot API."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from biota_shifts.config import _config_str
from biota_shifts.notification_settings import load_notification_settings

logger = logging.getLogger(__name__)

TELEGRAM_TEXT_LIMIT = 4096


def resolve_telegram_bot_token(settings: dict | None = None) -> str:
    env_token = (
        _config_str("BIOTA_TELEGRAM_BOT_TOKEN", "")
        or _config_str("BOT_TOKEN", "")
        or ""
    ).strip()
    if env_token:
        return env_token
    if settings:
        return str(settings.get("telegram_bot_token") or "").strip()
    return str(load_notification_settings().get("telegram_bot_token") or "").strip()


def telegram_notify_configured(settings: dict | None = None) -> bool:
    s = settings or load_notification_settings()
    token = resolve_telegram_bot_token(s)
    chat_ids = s.get("telegram_chat_ids") or []
    return bool(token) and bool(chat_ids)


def split_telegram_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    body = text or ""
    if len(body) <= limit:
        return [body] if body else [""]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in body.splitlines(keepends=True):
        if len(line) > limit:
            if buf:
                chunks.append("".join(buf))
                buf = []
                size = 0
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue
        if size + len(line) > limit and buf:
            chunks.append("".join(buf))
            buf = [line]
            size = len(line)
        else:
            buf.append(line)
            size += len(line)
    if buf:
        chunks.append("".join(buf))
    return chunks


def explain_telegram_error(message: str) -> str:
    m = (message or "").strip()
    low = m.lower()
    if "can't initiate conversation" in low or "bot was blocked" in low:
        return m + " — откройте бота в Telegram и нажмите /start (или разблокируйте)."
    if "chat not found" in low:
        return m + " — проверьте chat_id (для лички нужно число, не @username)."
    if "unauthorized" in low:
        return m + " — неверный токен бота."
    if "not enough rights" in low or "need administrator" in low:
        return m + " — для канала добавьте бота администратором с правом публикации."
    return m


def telegram_api_get(token: str, method: str, timeout: float = 15) -> dict:
    if not token:
        raise ValueError("Не задан токен Telegram-бота")
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            if not out.get("ok"):
                raise RuntimeError(explain_telegram_error(out.get("description") or "Telegram API error"))
            return out
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(detail).get("description") or detail
        except json.JSONDecodeError:
            msg = detail or str(exc)
        raise RuntimeError(explain_telegram_error(msg)) from exc


def fetch_telegram_bot_username(token: str) -> str:
    try:
        data = telegram_api_get(token, "getMe")
        result = data.get("result") or {}
        return str(result.get("username") or "").strip()
    except Exception:
        return ""


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    timeout: float = 30,
) -> dict:
    if not token:
        raise ValueError("Не задан токен Telegram-бота")
    if not str(chat_id).strip():
        raise ValueError("Не задан chat_id")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": str(chat_id).strip(), "text": text}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            out = json.loads(raw)
            if not out.get("ok"):
                raise RuntimeError(explain_telegram_error(out.get("description") or "Telegram API error"))
            return out
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            msg = parsed.get("description") or detail
        except json.JSONDecodeError:
            msg = detail or str(exc)
        raise RuntimeError(explain_telegram_error(msg)) from exc


def send_telegram_broadcast(
    token: str,
    chat_ids: list[str],
    text: str,
) -> int:
    """Отправить текст во все чаты/каналы. Возвращает число успешных отправок."""
    ids = [str(c).strip() for c in chat_ids if str(c).strip()]
    if not ids:
        return 0
    parts = split_telegram_text(text)
    sent = 0
    for chat_id in ids:
        for part in parts:
            send_telegram_message(token, chat_id, part)
        sent += 1
    return sent


def send_telegram_test(settings: dict | None = None) -> int:
    s = settings or load_notification_settings()
    token = resolve_telegram_bot_token(s)
    text = "Biota: тест уведомлений Telegram. Если видите это сообщение — бот настроен верно."
    return send_telegram_broadcast(token, s.get("telegram_chat_ids") or [], text)
