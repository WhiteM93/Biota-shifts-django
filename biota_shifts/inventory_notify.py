"""Уведомления в Telegram о событиях склада."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from biota_shifts.config import _config_str
from biota_shifts.constants import MSK
from biota_shifts.notification_settings import load_notification_settings
from biota_shifts.notify_relay import notify_delivery_configured, notify_relay_configured, post_notify_relay
from biota_shifts.telegram_notify import resolve_telegram_bot_token, send_telegram_broadcast

if TYPE_CHECKING:
    from shifts.models import InventoryStockEvent, StockMovement

logger = logging.getLogger(__name__)

_MOVEMENT_LABELS = {
    "issue": "Выдача",
    "restock": "Пополнение",
    "writeoff": "Списание",
}


def inventory_notify_enabled(settings: dict | None = None) -> bool:
    env = (_config_str("BIOTA_INVENTORY_NOTIFY", "") or "").strip().lower()
    if env in ("0", "false", "no"):
        return False
    if env in ("1", "true", "yes"):
        return True
    s = settings or load_notification_settings()
    return bool(s.get("inventory_notify_enabled", True))


def _format_when(created_at) -> tuple[str, str]:
    if created_at is None:
        return "—", "—"
    from django.utils import timezone as dj_tz

    dt = created_at
    if dj_tz.is_naive(dt):
        dt = dj_tz.make_aware(dt, MSK)
    local = dt.astimezone(MSK)
    return local.strftime("%d.%m.%Y"), local.strftime("%H:%M")


def movement_operation_title(movement: StockMovement) -> str:
    comment = (movement.comment or "").strip()
    if comment.startswith("Откат движения"):
        return "Откат операции"
    if movement.parent_issue_id and movement.movement_type == "restock":
        return "Возврат на склад"
    if movement.parent_issue_id and movement.movement_type == "writeoff":
        return "Списание по выдаче"
    return _MOVEMENT_LABELS.get(movement.movement_type, movement.movement_type)


def format_stock_movement_message(movement: StockMovement) -> str:
    tool = movement.tool
    tool_name = (tool.name if tool else "—").strip() or "—"
    stock_qty = int(tool.quantity) if tool else "—"
    op = movement_operation_title(movement)
    date_op = movement.movement_date.strftime("%d.%m.%Y") if movement.movement_date else "—"
    date_created, time_created = _format_when(movement.created_at)
    actor = (movement.created_by_account or "—").strip() or "—"
    employee = (movement.employee_name or "").strip()

    lines = [
        f"Склад — {op}",
        f"Позиция: {tool_name}",
        f"Количество: {movement.quantity} шт. · на складе: {stock_qty} шт.",
        f"Дата операции: {date_op} · записано: {date_created} {time_created}",
        f"Кто: {actor}",
    ]
    if employee:
        lines.append(f"Сотрудник: {employee}")
    if movement.parent_issue_id:
        lines.append(f"По выдаче №{movement.parent_issue_id}")
    comment = (movement.comment or "").strip()
    if comment:
        lines.append(f"Комментарий: {comment}")
    lines.append("")
    lines.append("— Biota / Склад")
    return "\n".join(lines)


def format_inventory_event_message(event: InventoryStockEvent) -> str:
    from shifts.models import InventoryStockEvent

    date_created, time_created = _format_when(event.created_at)
    actor = (event.actor_username or "—").strip() or "—"
    title = event.get_event_type_display()
    tool_name = (event.tool.name if event.tool else "").strip()

    lines = [f"Склад — {title}", f"Кто: {actor} · {date_created} {time_created}"]
    if tool_name:
        lines.append(f"Позиция: {tool_name}")
    summary = (event.summary or "").strip()
    if summary:
        lines.append(summary)
    if event.event_type == InventoryStockEvent.EVENT_ROLLBACK and event.stock_movement_id:
        lines.append(f"Движение №{event.stock_movement_id}")
    lines.append("")
    lines.append("— Biota / Склад")
    return "\n".join(lines)


def build_inventory_test_message(*, actor: str = "тест") -> str:
    from datetime import datetime

    date_str, time_str = _format_when(datetime.now(MSK))
    lines = [
        "Склад — Пополнение (тест)",
        "Позиция: Тестовая позиция · сверло D10",
        "Количество: 1 шт. · на складе: 10 шт.",
        f"Дата операции: {date_str} · записано: {date_str} {time_str}",
        f"Кто: {actor}",
        "Комментарий: Проверка уведомлений склада из кабинета Biota",
        "",
        "— Biota / Склад",
    ]
    return "\n".join(lines)


def send_inventory_notify_test(settings: dict | None = None, *, actor: str = "тест") -> None:
    """Тестовое уведомление склада (из кабинета)."""
    cfg = load_notification_settings() if settings is None else settings
    if not notify_delivery_configured(cfg):
        raise ValueError("Доставка не настроена: укажите relay URL или токен + chat_id")
    text = build_inventory_test_message(actor=actor)
    chat_ids = list(cfg.get("telegram_chat_ids") or [])
    payload = {"kind": "inventory", "text": text, "chat_ids": chat_ids, "meta": {"test": True}}
    if notify_relay_configured(cfg):
        post_notify_relay(payload, cfg)
        return
    token = resolve_telegram_bot_token(cfg)
    if not token or not chat_ids:
        raise ValueError("Не задан токен или chat_id")
    send_telegram_broadcast(token, chat_ids, text)


def send_inventory_notification(text: str, *, meta: dict | None = None, settings: dict | None = None) -> None:
    cfg = load_notification_settings() if settings is None else settings
    if not inventory_notify_enabled(cfg) or not notify_delivery_configured(cfg):
        return
    chat_ids = list(cfg.get("telegram_chat_ids") or [])
    payload = {"kind": "inventory", "text": text, "chat_ids": chat_ids, "meta": meta or {}}
    try:
        if notify_relay_configured(cfg):
            post_notify_relay(payload, cfg)
            return
        token = resolve_telegram_bot_token(cfg)
        if token and chat_ids:
            send_telegram_broadcast(token, chat_ids, text)
    except Exception:
        logger.exception("Не удалось отправить уведомление склада в Telegram")


def try_notify_stock_movement(movement: StockMovement | int) -> None:
    from shifts.models import StockMovement

    if isinstance(movement, int):
        movement = (
            StockMovement.objects.select_related("tool", "parent_issue")
            .filter(pk=movement)
            .first()
        )
    if not movement or not movement.tool_id:
        return
    if (movement.comment or "").startswith("Откат движения"):
        return
    text = format_stock_movement_message(movement)
    send_inventory_notification(
        text,
        meta={
            "movement_id": movement.id,
            "movement_type": movement.movement_type,
            "tool_id": movement.tool_id,
            "quantity": movement.quantity,
        },
    )


def try_notify_inventory_event(event: InventoryStockEvent | int) -> None:
    from shifts.models import InventoryStockEvent

    if isinstance(event, int):
        event = (
            InventoryStockEvent.objects.select_related("tool", "stock_movement")
            .filter(pk=event)
            .first()
        )
    if not event:
        return
    if event.event_type not in {
        InventoryStockEvent.EVENT_TOOL_EDIT,
        InventoryStockEvent.EVENT_TOOL_DELETE,
        InventoryStockEvent.EVENT_ROLLBACK,
        InventoryStockEvent.EVENT_PRIVILEGE,
    }:
        return
    text = format_inventory_event_message(event)
    send_inventory_notification(
        text,
        meta={
            "event_id": event.id,
            "event_type": event.event_type,
            "tool_id": event.tool_id,
        },
    )
