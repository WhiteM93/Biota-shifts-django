from __future__ import annotations

import os
from datetime import date

import holidays


def _parse_date_list_env(var_name: str) -> set[date]:
    raw = (os.getenv(var_name) or "").strip()
    if not raw:
        return set()
    out: set[date] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            out.add(date.fromisoformat(token))
        except ValueError:
            continue
    return out


def is_ru_non_working_day(day: date) -> bool:
    """Russian production-like rule for UI highlighting.

    - weekends are non-working by default;
    - official RU public holidays are non-working;
    - BIOTA_RU_WORKDAYS can force specific dates to working;
    - BIOTA_RU_HOLIDAYS can force specific dates to non-working.
    """
    forced_workdays = _parse_date_list_env("BIOTA_RU_WORKDAYS")
    forced_holidays = _parse_date_list_env("BIOTA_RU_HOLIDAYS")

    if day in forced_workdays:
        return False
    if day in forced_holidays:
        return True

    ru_holidays = holidays.country_holidays("RU", years=[day.year])
    return day.weekday() >= 5 or day in ru_holidays

