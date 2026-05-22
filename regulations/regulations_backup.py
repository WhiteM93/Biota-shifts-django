"""Резервное копирование регламентов: экспорт/импорт JSON (RegulationPlan)."""
from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from regulations.models import RegulationPlan

BACKUP_FORMAT_VERSION = 1
BACKUP_FILENAME_PREFIX = "regulations_"


class RegulationsBackupError(Exception):
    pass


def _json_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, time):
        return val.isoformat()
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


def export_regulations_payload() -> dict[str, Any]:
    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "exported_at": timezone.now().isoformat(),
        "regulation_plans": [_model_to_row(o) for o in RegulationPlan.objects.order_by("id")],
    }


def payload_to_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def validate_regulations_payload(data: dict[str, Any]) -> dict[str, Any]:
    version = data.get("format_version")
    if version != BACKUP_FORMAT_VERSION:
        raise RegulationsBackupError(
            f"Неподдерживаемая версия резервной копии: {version!r} (ожидается {BACKUP_FORMAT_VERSION})"
        )
    if "regulation_plans" not in data or not isinstance(data["regulation_plans"], list):
        raise RegulationsBackupError("В резервной копии отсутствует или некорректен раздел «regulation_plans»")
    return data


def parse_regulations_backup_bytes(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegulationsBackupError("Файл не является корректным JSON") from exc
    if not isinstance(data, dict):
        raise RegulationsBackupError("Ожидается JSON-объект")
    return validate_regulations_payload(data)


def _parse_time_value(val: str) -> time:
    raw = (val or "").strip()
    if not raw:
        raise ValueError("empty time")
    if "T" in raw:
        raw = raw.split("T", 1)[-1]
    parts = raw.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    s = int(float(parts[2])) if len(parts) > 2 else 0
    return time(h, m, s)


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
        if field.get_internal_type() == "TimeField":
            out[name] = _parse_time_value(str(val)) if isinstance(val, str) else val
            continue
        if field.get_internal_type() in {"DateTimeField", "DateField"}:
            if isinstance(val, str):
                parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
                out[name] = parsed.date() if field.get_internal_type() == "DateField" else parsed
            else:
                out[name] = val
            continue
        if field.get_internal_type() == "BooleanField":
            out[name] = bool(val)
            continue
        if field.get_internal_type() == "JSONField":
            out[name] = val if isinstance(val, (dict, list)) else []
            continue
        if field.get_internal_type() in {
            "PositiveIntegerField",
            "PositiveSmallIntegerField",
            "IntegerField",
            "BigAutoField",
            "AutoField",
        }:
            out[name] = int(val) if val is not None else None
            continue
        out[name] = val
    return out


def _reset_sequences() -> None:
    if connection.vendor != "postgresql":
        return
    table = RegulationPlan._meta.db_table
    pk_col = RegulationPlan._meta.pk.column
    qn = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{pk_col}'), "
            f"COALESCE((SELECT MAX({qn(pk_col)}) FROM {qn(table)}), 1))"
        )


@transaction.atomic
def restore_regulations_from_payload(payload: dict[str, Any]) -> dict[str, int]:
    """Полная замена регламентов содержимым резервной копии."""
    data = validate_regulations_payload(payload)
    rows = data["regulation_plans"]

    RegulationPlan.objects.all().delete()

    if rows:
        objs = [RegulationPlan(**_coerce_row(RegulationPlan, row)) for row in rows]
        RegulationPlan.objects.bulk_create(objs)

    _reset_sequences()

    return {"plans": len(rows)}


def backup_filename_now() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{BACKUP_FILENAME_PREFIX}{ts}.json"


def is_safe_backup_filename(name: str) -> bool:
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    return name.startswith(BACKUP_FILENAME_PREFIX) and name.endswith(".json")


def write_backup_file(backups_dir: Path, payload: dict[str, Any] | None = None, *, filename: str | None = None) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    payload = payload if payload is not None else export_regulations_payload()
    fname = filename or backup_filename_now()
    path = backups_dir / fname
    path.write_bytes(payload_to_json_bytes(payload))
    return path


def list_backup_files(backups_dir: Path) -> list[dict[str, str]]:
    if not backups_dir.exists():
        return []
    items = []
    for path in sorted(
        backups_dir.glob(f"{BACKUP_FILENAME_PREFIX}*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        stat = path.stat()
        items.append({
            "filename": path.name,
            "size": f"{stat.st_size / 1024:.1f} KB",
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return items
