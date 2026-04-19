from __future__ import annotations

import json
from pathlib import Path

from biota_shifts.config import APP_DIR

POSITION_ORDER_PATH = Path(APP_DIR) / ".biota_position_order.json"


def load_position_order() -> list[str]:
    if not POSITION_ORDER_PATH.exists():
        return []
    try:
        raw = json.loads(POSITION_ORDER_PATH.read_text(encoding="utf-8-sig"))
        order = raw.get("positions", [])
        if not isinstance(order, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in order:
            s = str(item).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []


def save_position_order(order: list[str]) -> None:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in order:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    POSITION_ORDER_PATH.write_text(
        json.dumps({"positions": cleaned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def apply_position_order(all_positions: list[str], preferred: list[str]) -> list[str]:
    all_unique = sorted({str(p).strip() for p in all_positions if str(p).strip()})
    if not all_unique:
        return []
    pref_clean = [p for p in preferred if p in all_unique]
    rest = [p for p in all_unique if p not in pref_clean]
    return pref_clean + rest
