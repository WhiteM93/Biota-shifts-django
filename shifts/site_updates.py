"""Записи ленты обновлений из файла в git (site_updates.json)."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings

SITE_UPDATES_FILENAME = "site_updates.json"
ACCOUNT_PREFS_FILENAME = ".biota_account_prefs.json"
ACCOUNT_PREFS_SEEN_KEY = "site_updates_seen_id"

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


def account_prefs_path() -> Path:
    override = (os.getenv("BIOTA_ACCOUNT_PREFS") or "").strip()
    if override:
        return Path(override)
    return Path(settings.BASE_DIR) / ACCOUNT_PREFS_FILENAME


_prefs_mtime: float | None = None
_prefs_seen: dict[str, int] = {}
_prefs_ready = False


def _normalize_account_key(username: str) -> str:
    return (username or "").strip().casefold()


def _load_account_seen_map(*, force: bool = False) -> dict[str, int]:
    global _prefs_mtime, _prefs_seen, _prefs_ready
    path = account_prefs_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _prefs_mtime = None
        _prefs_seen = {}
        _prefs_ready = True
        return {}
    if not force and _prefs_ready and _prefs_mtime == mtime:
        return _prefs_seen
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    raw = payload.get(ACCOUNT_PREFS_SEEN_KEY) if isinstance(payload, dict) else {}
    seen: dict[str, int] = {}
    if isinstance(raw, dict):
        for login, val in raw.items():
            key = _normalize_account_key(str(login))
            if not key:
                continue
            try:
                seen[key] = max(seen.get(key, 0), int(val))
            except (TypeError, ValueError):
                continue
    _prefs_mtime = mtime
    _prefs_seen = seen
    _prefs_ready = True
    return seen


def _save_account_seen_map(seen: dict[str, int]) -> None:
    global _prefs_mtime, _prefs_seen, _prefs_ready
    path = account_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: seen[k] for k in sorted(seen.keys(), key=str.casefold)}
    path.write_text(
        json.dumps({ACCOUNT_PREFS_SEEN_KEY: ordered}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        _prefs_mtime = path.stat().st_mtime
    except OSError:
        _prefs_mtime = None
    _prefs_seen = dict(ordered)
    _prefs_ready = True


def account_site_updates_seen_id(username: str) -> int:
    key = _normalize_account_key(username)
    if not key:
        return 0
    return int(_load_account_seen_map().get(key) or 0)


def set_account_site_updates_seen_id(username: str, seen_id: int) -> int:
    """Запомнить для аккаунта, до какого id обновлений пользователь дошёл."""
    key = _normalize_account_key(username)
    if not key:
        return 0
    try:
        target = int(seen_id)
    except (TypeError, ValueError):
        return account_site_updates_seen_id(username)
    if target <= 0:
        return account_site_updates_seen_id(username)
    seen = dict(_load_account_seen_map(force=True))
    current = int(seen.get(key) or 0)
    if target <= current:
        return current
    seen[key] = target
    _save_account_seen_map(seen)
    return target


def effective_site_updates_seen_id(username: str, session_seen: int) -> int:
    try:
        session_val = int(session_seen or 0)
    except (TypeError, ValueError):
        session_val = 0
    account_val = account_site_updates_seen_id(username) if username else 0
    return max(session_val, account_val)
