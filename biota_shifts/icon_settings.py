"""Переопределения иконок (JSON в корне проекта)."""
from __future__ import annotations

import json
from pathlib import Path

from biota_shifts.config import APP_DIR
from biota_shifts.hugeicons_map import is_valid_hugeicons_slug
from biota_shifts.icon_registry import DEFAULT_ICON_REGISTRY, ICON_KINDS

ICON_SETTINGS_PATH = Path(APP_DIR) / ".biota_icon_settings.json"
ICON_PRESETS = ("default", "hugeicons")
DEFAULT_ICON_PRESET = "hugeicons"


def _safe_key(key: str) -> str:
    return (key or "").strip()


def _clean_overrides(overrides: dict | None) -> dict[str, dict]:
    clean: dict[str, dict] = {}
    for key, spec in (overrides or {}).items():
        k = _safe_key(key)
        if not k or k not in DEFAULT_ICON_REGISTRY or not isinstance(spec, dict):
            continue
        kind = str(spec.get("kind") or "").strip()
        value = str(spec.get("value") or "").strip()
        if kind not in ICON_KINDS or not value:
            continue
        if kind == "partial" and not value.endswith(".html"):
            continue
        if kind == "svg_static" and not value.endswith(".svg"):
            continue
        if kind == "hugeicons" and not is_valid_hugeicons_slug(value):
            continue
        default = DEFAULT_ICON_REGISTRY[k]
        if kind == default["kind"] and value == default["value"]:
            continue
        clean[k] = {"kind": kind, "value": value}
    return clean


def _normalize_preset(value: str | None) -> str:
    preset = (value or DEFAULT_ICON_PRESET).strip()
    return preset if preset in ICON_PRESETS else DEFAULT_ICON_PRESET


def load_icon_settings() -> dict:
    if not ICON_SETTINGS_PATH.exists():
        return {"preset": DEFAULT_ICON_PRESET, "overrides": {}}
    try:
        raw = json.loads(ICON_SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            return {"preset": DEFAULT_ICON_PRESET, "overrides": {}}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {"preset": DEFAULT_ICON_PRESET, "overrides": {}}
    return {
        "preset": _normalize_preset(raw.get("preset")),
        "overrides": _clean_overrides(raw.get("overrides")),
    }


def get_effective_overrides() -> dict[str, dict]:
    data = load_icon_settings()
    effective: dict[str, dict] = {}
    if data.get("preset") == "hugeicons":
        from biota_shifts.hugeicons_map import build_hugeicons_overrides

        effective.update(build_hugeicons_overrides())
    effective.update(data.get("overrides") or {})
    return effective


def get_icon_preset() -> str:
    return load_icon_settings().get("preset") or "default"


def set_icon_preset(preset: str) -> dict:
    data = load_icon_settings()
    data["preset"] = _normalize_preset(preset)
    return _write_icon_settings(data)


def save_icon_settings(overrides: dict, *, preset: str | None = None) -> dict:
    current = load_icon_settings()
    data = {
        "preset": _normalize_preset(preset if preset is not None else current.get("preset")),
        "overrides": _clean_overrides(overrides),
    }
    return _write_icon_settings(data)


def _write_icon_settings(data: dict) -> dict:
    payload = {
        "preset": _normalize_preset(data.get("preset")),
        "overrides": _clean_overrides(data.get("overrides")),
    }
    ICON_SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload
