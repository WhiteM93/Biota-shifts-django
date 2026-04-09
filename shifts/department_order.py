from __future__ import annotations

import json
from pathlib import Path

from biota_shifts.config import APP_DIR

DEPT_ORDER_PATH = Path(APP_DIR) / ".biota_department_order.json"


def load_department_order() -> list[str]:
    if not DEPT_ORDER_PATH.exists():
        return []
    try:
        raw = json.loads(DEPT_ORDER_PATH.read_text(encoding="utf-8-sig"))
        order = raw.get("departments", [])
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


def save_department_order(order: list[str]) -> None:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in order:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    DEPT_ORDER_PATH.write_text(
        json.dumps({"departments": cleaned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def apply_department_order(all_departments: list[str], preferred: list[str]) -> list[str]:
    all_unique = sorted({str(d).strip() for d in all_departments if str(d).strip()})
    if not all_unique:
        return []
    pref_clean = [d for d in preferred if d in all_unique]
    rest = [d for d in all_unique if d not in pref_clean]
    return pref_clean + rest

