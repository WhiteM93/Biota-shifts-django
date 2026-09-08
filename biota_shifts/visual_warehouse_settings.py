"""Настройки визуального склада (сроки актуальности инвентаризации)."""
from __future__ import annotations

import json
from pathlib import Path

from biota_shifts.config import APP_DIR

VISUAL_WAREHOUSE_SETTINGS_PATH = Path(APP_DIR) / ".biota_visual_warehouse_settings.json"

DEFAULT_SETTINGS: dict = {
    # Зелёный: инвентаризация не старше N дней
    "audit_ok_days": 30,
    # Жёлтый: старше ok, но не старше N дней; красный — ещё старше или нет даты
    "audit_warn_days": 90,
}


def _clamp_days(value, fallback: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(3650, n))


def load_visual_warehouse_settings() -> dict:
    if not VISUAL_WAREHOUSE_SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        raw = json.loads(VISUAL_WAREHOUSE_SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            return dict(DEFAULT_SETTINGS)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)

    ok = _clamp_days(raw.get("audit_ok_days"), DEFAULT_SETTINGS["audit_ok_days"])
    warn = _clamp_days(raw.get("audit_warn_days"), DEFAULT_SETTINGS["audit_warn_days"])
    if ok > warn:
        ok = warn
    return {"audit_ok_days": ok, "audit_warn_days": warn}


def save_visual_warehouse_settings(data: dict) -> dict:
    current = load_visual_warehouse_settings()
    ok = _clamp_days(data.get("audit_ok_days"), current["audit_ok_days"])
    warn = _clamp_days(data.get("audit_warn_days"), current["audit_warn_days"])
    if ok > warn:
        ok = warn
    out = {"audit_ok_days": ok, "audit_warn_days": warn}
    VISUAL_WAREHOUSE_SETTINGS_PATH.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out
