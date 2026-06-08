"""Локальный кэш Google-графика: снимок листа, автообновление в 21:00 МСК, ручное обновление."""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path

import pandas as pd

from biota_shifts.config import SCHEDULE_DIR
from biota_shifts.constants import MSK

CACHE_SUBDIR = "google_cache"
DEFAULT_REFRESH_HOUR = 21
LOCK_STALE_SEC = 180


def _config_int(key: str, default: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def scheduled_refresh_hour() -> int:
    return max(0, min(23, _config_int("BIOTA_GOOGLE_SCHEDULE_REFRESH_HOUR", DEFAULT_REFRESH_HOUR)))


def cache_dir() -> Path:
    override = (os.getenv("BIOTA_GOOGLE_SCHEDULE_CACHE_DIR") or "").strip()
    p = Path(override) if override else (SCHEDULE_DIR / CACHE_SUBDIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_stem(year: int, month: int) -> str:
    return f"google_{year}_{month:02d}"


def _data_path(year: int, month: int) -> Path:
    return cache_dir() / f"{_cache_stem(year, month)}.pkl"


def _meta_path(year: int, month: int) -> Path:
    return cache_dir() / f"{_cache_stem(year, month)}.meta.json"


def _lock_path(year: int, month: int) -> Path:
    return cache_dir() / f"{_cache_stem(year, month)}.lock"


def _scheduled_refresh_dt_msk(day: date, hour: int | None = None) -> datetime:
    h = scheduled_refresh_hour() if hour is None else hour
    return datetime.combine(day, dt_time(h, 0), tzinfo=MSK)


def needs_scheduled_refresh(
    fetched_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """True, если после сегодняшнего 21:00 МСК кэш ещё не обновляли."""
    now = now or datetime.now(MSK)
    if fetched_at is None:
        return True
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=MSK)
    else:
        fetched_at = fetched_at.astimezone(MSK)
    today_cutoff = _scheduled_refresh_dt_msk(now.date())
    if now < today_cutoff:
        return False
    return fetched_at < today_cutoff


def read_cache_meta(year: int, month: int) -> dict | None:
    path = _meta_path(year, month)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_fetched_at(year: int, month: int) -> datetime | None:
    meta = read_cache_meta(year, month)
    if not meta or not meta.get("fetched_at"):
        return None
    try:
        dt = datetime.fromisoformat(str(meta["fetched_at"]))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MSK)
    return dt.astimezone(MSK)


def format_cache_fetched_at(year: int, month: int) -> str:
    dt = cache_fetched_at(year, month)
    if dt is None:
        return ""
    return dt.strftime("%d.%m.%Y %H:%M МСК")


def load_cached_dataframe(year: int, month: int) -> pd.DataFrame | None:
    path = _data_path(year, month)
    if not path.is_file():
        return None
    try:
        return pd.read_pickle(path)
    except Exception:
        return None


def save_cache(
    df: pd.DataFrame,
    year: int,
    month: int,
    *,
    worksheet_title: str = "",
    source: str = "google_api",
) -> datetime:
    now = datetime.now(MSK)
    _data_path(year, month).parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(_data_path(year, month))
    meta = {
        "fetched_at": now.isoformat(),
        "year": year,
        "month": month,
        "rows": int(len(df)),
        "worksheet": worksheet_title,
        "source": source,
    }
    _meta_path(year, month).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return now


def _lock_is_stale(lock: Path) -> bool:
    if not lock.exists():
        return True
    try:
        age = time.time() - lock.stat().st_mtime
        return age > LOCK_STALE_SEC
    except OSError:
        return True


def _try_acquire_lock(year: int, month: int) -> bool:
    lock = _lock_path(year, month)
    if not _lock_is_stale(lock):
        return False
    try:
        if lock.exists():
            lock.unlink()
        lock.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        return False


def _release_lock(year: int, month: int) -> None:
    try:
        _lock_path(year, month).unlink(missing_ok=True)
    except OSError:
        pass


def _fetch_live_dataframe(year: int, month: int) -> tuple[pd.DataFrame, str]:
    from biota_shifts.schedule_google import (
        GoogleScheduleError,
        _fetch_schedule_dataframe_from_api,
    )

    df, worksheet_title = _fetch_schedule_dataframe_from_api(year, month)
    if df.empty:
        raise GoogleScheduleError(f"Лист за {month:02d}.{year} пустой или не найден.")
    return df, worksheet_title


def refresh_google_schedule_cache(
    year: int,
    month: int,
    *,
    force: bool = False,
) -> datetime:
    """Принудительно загрузить лист из Google и сохранить в кэш."""
    from biota_shifts.schedule_google import GoogleScheduleError, google_schedule_configured

    if not google_schedule_configured():
        raise GoogleScheduleError("Google не настроен.")

    if force:
        try:
            _lock_path(year, month).unlink(missing_ok=True)
        except OSError:
            pass
    acquired = _try_acquire_lock(year, month)
    try:
        df, ws_title = _fetch_live_dataframe(year, month)
        return save_cache(df, year, month, worksheet_title=ws_title)
    finally:
        if acquired:
            _release_lock(year, month)


def load_google_schedule_cached(
    year: int,
    month: int,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Вернуть снимок листа Google из кэша.
    К Google API обращается только если: нет кэша, force_refresh, или наступило 21:00 МСК.
    """
    from biota_shifts.schedule_google import GoogleScheduleError, google_schedule_configured

    if not google_schedule_configured():
        raise GoogleScheduleError("Google не настроен.")

    cached = load_cached_dataframe(year, month)
    fetched_at = cache_fetched_at(year, month)
    should_fetch = (
        force_refresh
        or cached is None
        or needs_scheduled_refresh(fetched_at)
    )

    if not should_fetch and cached is not None:
        return cached

    acquired = _try_acquire_lock(year, month)
    if not acquired:
        if cached is not None:
            return cached
        time.sleep(0.3)
        cached = load_cached_dataframe(year, month)
        if cached is not None:
            return cached

    try:
        df, ws_title = _fetch_live_dataframe(year, month)
        save_cache(df, year, month, worksheet_title=ws_title)
        return df
    finally:
        if acquired:
            _release_lock(year, month)


def prev_month(year: int, month: int) -> tuple[int, int]:
    first = date(year, month, 1)
    prev_last = first - timedelta(days=1)
    return prev_last.year, prev_last.month


def refresh_for_cron(*, year: int | None = None, month: int | None = None) -> list[str]:
    """Обновить кэш текущего и предыдущего месяца (для cron в 21:00 МСК)."""
    now = datetime.now(MSK)
    y = year if year is not None else now.year
    m = month if month is not None else now.month
    py, pm = prev_month(y, m)
    done: list[str] = []
    for yy, mm in ((y, m), (py, pm)):
        try:
            at = refresh_google_schedule_cache(yy, mm, force=True)
            done.append(f"{mm:02d}.{yy} → {at.strftime('%H:%M %d.%m.%Y')}")
        except Exception as exc:
            done.append(f"{mm:02d}.{yy} → ошибка: {exc}")
    return done
