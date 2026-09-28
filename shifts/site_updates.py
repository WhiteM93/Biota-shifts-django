"""Записи ленты обновлений из файла в git (site_updates.json)."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings

SITE_UPDATES_FILENAME = "site_updates.json"

_cache_mtime: float | None = None
_cache_rows: list[SimpleNamespace] = []
_cache_ready = False


def site_updates_path() -> Path:
    return Path(settings.BASE_DIR) / SITE_UPDATES_FILENAME


def _parse_entry(raw: dict) -> SimpleNamespace | None:
    if not isinstance(raw, dict):
        return None
    try:
        pk = int(raw.get("id") or 0)
    except (TypeError, ValueError):
        return None
    title = str(raw.get("title") or "").strip()
    body = str(raw.get("body") or "").strip()
    if pk <= 0 or not title or not body:
        return None
    date_raw = str(raw.get("date") or "").strip()
    try:
        day = date.fromisoformat(date_raw) if date_raw else date.today()
    except ValueError:
        day = date.today()
    created = datetime(day.year, day.month, day.day)
    return SimpleNamespace(id=pk, pk=pk, title=title, body=body, created_at=created)


def load_site_updates(*, force: bool = False) -> list[SimpleNamespace]:
    global _cache_mtime, _cache_rows, _cache_ready
    path = site_updates_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache_mtime = None
        _cache_rows = []
        _cache_ready = True
        return []
    if not force and _cache_ready and _cache_mtime == mtime:
        return _cache_rows
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _cache_mtime = mtime
        _cache_rows = []
        _cache_ready = True
        return []
    raw_list = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(raw_list, list):
        raw_list = []
    rows = []
    for item in raw_list:
        row = _parse_entry(item)
        if row:
            rows.append(row)
    rows.sort(key=lambda r: (r.created_at, r.id), reverse=True)
    _cache_mtime = mtime
    _cache_rows = rows
    _cache_ready = True
    return rows


def latest_site_update_id() -> int:
    rows = load_site_updates()
    return max((r.id for r in rows), default=0)


def unread_site_updates_count(seen_id: int) -> int:
    seen = int(seen_id or 0)
    return sum(1 for r in load_site_updates() if r.id > seen)
