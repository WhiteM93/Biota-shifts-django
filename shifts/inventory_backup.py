"""Резервное копирование склада: экспорт/импорт JSON (позиции, движения, закупки, журнал)."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from shifts.models import (
    CenterDrillSpec,
    CountersinkSpec,
    DrillSpec,
    EndMillSpec,
    InventoryStockEvent,
    PurchaseRequest,
    StockMovement,
    TapSpec,
    ToolItem,
)

BACKUP_FORMAT_VERSION = 1
BACKUP_FILENAME_PREFIX = "inventory_"


class InventoryBackupError(Exception):
    pass


def _json_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, (datetime, date)):
        if isinstance(val, datetime) and timezone.is_aware(val):
            return val.isoformat()
        if isinstance(val, datetime):
            return val.isoformat()
        return val.isoformat()
    return val


def _model_to_row(instance) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in instance._meta.fields:
        row[field.attname] = _json_value(getattr(instance, field.attname))
    return row


def export_inventory_payload() -> dict[str, Any]:
    """Снимок всех таблиц склада для JSON-файла."""
    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "exported_at": timezone.now().isoformat(),
        "tool_items": [_model_to_row(o) for o in ToolItem.objects.order_by("id")],
        "end_mill_specs": [_model_to_row(o) for o in EndMillSpec.objects.order_by("id")],
        "tap_specs": [_model_to_row(o) for o in TapSpec.objects.order_by("id")],
        "center_drill_specs": [_model_to_row(o) for o in CenterDrillSpec.objects.order_by("id")],
        "countersink_specs": [_model_to_row(o) for o in CountersinkSpec.objects.order_by("id")],
        "drill_specs": [_model_to_row(o) for o in DrillSpec.objects.order_by("id")],
        "stock_movements": [_model_to_row(o) for o in StockMovement.objects.order_by("id")],
        "purchase_requests": [_model_to_row(o) for o in PurchaseRequest.objects.order_by("id")],
        "inventory_stock_events": [_model_to_row(o) for o in InventoryStockEvent.objects.order_by("id")],
    }


def payload_to_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def validate_inventory_payload(data: dict[str, Any]) -> dict[str, Any]:
    version = data.get("format_version")
    if version != BACKUP_FORMAT_VERSION:
        raise InventoryBackupError(
            f"Неподдерживаемая версия резервной копии: {version!r} (ожидается {BACKUP_FORMAT_VERSION})"
        )
    required = (
        "tool_items",
        "end_mill_specs",
        "tap_specs",
        "center_drill_specs",
        "countersink_specs",
        "drill_specs",
        "stock_movements",
        "purchase_requests",
        "inventory_stock_events",
    )
    for key in required:
        if key not in data or not isinstance(data[key], list):
            raise InventoryBackupError(f"В резервной копии отсутствует или некорректен раздел «{key}»")
    return data


def parse_inventory_backup_bytes(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryBackupError("Файл не является корректным JSON") from exc
    if not isinstance(data, dict):
        raise InventoryBackupError("Ожидается JSON-объект")
    return validate_inventory_payload(data)


def _coerce_row(model_cls, row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in model_cls._meta.fields:
        name = field.attname
        if name not in row:
            continue
        val = row[name]
        if val is None:
            out[name] = None
            continue
        if field.get_internal_type() in {"DateTimeField", "DateField"}:
            if isinstance(val, str):
                parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
                if field.get_internal_type() == "DateField":
                    out[name] = parsed.date()
                elif timezone.is_aware(parsed):
                    out[name] = parsed
                else:
                    out[name] = timezone.make_aware(parsed) if settings_use_tz() else parsed
            else:
                out[name] = val
            continue
        if field.get_internal_type() in {"DecimalField"}:
            out[name] = Decimal(str(val))
            continue
        if field.get_internal_type() in {"BooleanField"}:
            out[name] = bool(val)
            continue
        if field.get_internal_type() in {"PositiveIntegerField", "PositiveSmallIntegerField", "IntegerField", "BigAutoField", "AutoField"}:
            out[name] = int(val) if val is not None else None
            continue
        if field.get_internal_type() == "JSONField":
            out[name] = val if isinstance(val, (dict, list)) else {}
            continue
        out[name] = val
    return out


def settings_use_tz() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "USE_TZ", True))


def _clear_inventory_tables() -> None:
    InventoryStockEvent.objects.all().delete()
    StockMovement.objects.all().delete()
    EndMillSpec.objects.all().delete()
    TapSpec.objects.all().delete()
    CenterDrillSpec.objects.all().delete()
    CountersinkSpec.objects.all().delete()
    DrillSpec.objects.all().delete()
    ToolItem.objects.all().delete()
    PurchaseRequest.objects.all().delete()


def _bulk_create(model_cls, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    objs = [model_cls(**_coerce_row(model_cls, row)) for row in rows]
    model_cls.objects.bulk_create(objs)


def _reset_sequences() -> None:
    """После явных pk — обновить счётчики (PostgreSQL)."""
    if connection.vendor != "postgresql":
        return
    seq_models = (
        ToolItem,
        EndMillSpec,
        TapSpec,
        CenterDrillSpec,
        CountersinkSpec,
        DrillSpec,
        StockMovement,
        PurchaseRequest,
        InventoryStockEvent,
    )
    qn = connection.ops.quote_name
    with connection.cursor() as cursor:
        for model in seq_models:
            table = qn(model._meta.db_table)
            pk_col = qn(model._meta.pk.column)
            cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{model._meta.db_table}', '{model._meta.pk.column}'), "
                f"COALESCE((SELECT MAX({pk_col}) FROM {table}), 1))"
            )


@transaction.atomic
def restore_inventory_from_payload(payload: dict[str, Any]) -> dict[str, int]:
    """Полная замена данных склада содержимым резервной копии."""
    data = validate_inventory_payload(payload)

    _clear_inventory_tables()

    _bulk_create(ToolItem, data["tool_items"])
    _bulk_create(EndMillSpec, data["end_mill_specs"])
    _bulk_create(TapSpec, data["tap_specs"])
    _bulk_create(CenterDrillSpec, data["center_drill_specs"])
    _bulk_create(CountersinkSpec, data["countersink_specs"])
    _bulk_create(DrillSpec, data["drill_specs"])
    _bulk_create(StockMovement, data["stock_movements"])
    _bulk_create(PurchaseRequest, data["purchase_requests"])
    _bulk_create(InventoryStockEvent, data["inventory_stock_events"])

    _reset_sequences()

    return {
        "tools": len(data["tool_items"]),
        "movements": len(data["stock_movements"]),
        "purchases": len(data["purchase_requests"]),
        "events": len(data["inventory_stock_events"]),
    }


def backup_filename_now() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{BACKUP_FILENAME_PREFIX}{ts}.json"


def is_safe_backup_filename(name: str) -> bool:
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    if not name.startswith(BACKUP_FILENAME_PREFIX) or not name.endswith(".json"):
        return False
    return True


def write_backup_file(backups_dir: Path, payload: dict[str, Any] | None = None, *, filename: str | None = None) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    payload = payload if payload is not None else export_inventory_payload()
    fname = filename or backup_filename_now()
    path = backups_dir / fname
    path.write_bytes(payload_to_json_bytes(payload))
    return path


def list_backup_files(backups_dir: Path) -> list[dict[str, str]]:
    if not backups_dir.exists():
        return []
    items = []
    for path in sorted(backups_dir.glob(f"{BACKUP_FILENAME_PREFIX}*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append({
            "filename": path.name,
            "size": f"{stat.st_size / 1024:.1f} KB",
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return items
