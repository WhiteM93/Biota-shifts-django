"""Проверка доступности БД и хранилища графиков для страницы «ЛК / админ»."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from django.db import connection

from biota_shifts import db as biota_db
from biota_shifts.config import SCHEDULE_DIR


def _level(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "err"
    if warn:
        return "warn"
    return "ok"


def check_django_database() -> dict:
    """ORM и регламенты: PostgreSQL если задан SITE_DB_HOST, иначе SQLite."""
    d = connection.settings_dict
    engine = (d.get("ENGINE") or "").lower()
    name = d.get("NAME", "")
    host = (d.get("HOST") or "").strip()
    if isinstance(name, Path):
        name_s = str(name)
    else:
        name_s = str(name)

    is_sqlite = "sqlite" in engine
    title = "БД сайта (Django, регламенты, сессии)"
    detail_parts: list[str] = []
    if is_sqlite:
        detail_parts.append(f"SQLite: {name_s}")
    elif "postgres" in engine:
        port = d.get("PORT") or "5432"
        detail_parts.append(f"PostgreSQL {host or 'localhost'}:{port} / {d.get('USER', '')} → {d.get('NAME', '')}")
    else:
        detail_parts.append(engine.split(".")[-1] if engine else "unknown")

    ok = False
    err = ""
    try:
        connection.ensure_connection()
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        ok = True
    except Exception as exc:
        err = str(exc)

    warn = ok and is_sqlite
    detail = "; ".join(detail_parts)
    if not ok:
        detail = f"{detail} — ошибка: {err}" if detail else err
    elif warn:
        detail += ". Для продакшена задайте SITE_DB_HOST и переменные PostgreSQL."

    return {
        "id": "django",
        "title": title,
        "ok": ok,
        "detail": detail,
        "level": _level(ok, warn),
    }


def check_biota_database() -> dict:
    """Справочник сотрудников и данные Biota (PostgreSQL)."""
    cfg = biota_db.db_config()
    host = cfg.get("host", "")
    dbn = cfg.get("dbname", "")
    title = "БД Biota (справочник, график из Excel в интерфейсе)"
    detail = f"{host}:{cfg.get('port', 5432)} / {dbn}"
    try:
        with psycopg.connect(**cfg) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"id": "biota", "title": title, "ok": True, "detail": detail, "level": "ok"}
    except Exception as exc:
        return {
            "id": "biota",
            "title": title,
            "ok": False,
            "detail": f"{detail} — {exc}",
            "level": "err",
        }


def check_schedule_storage() -> dict:
    """Каталог файлов графика schedule_YYYY_MM.xlsx."""
    p = SCHEDULE_DIR
    title = "Папка графиков (Excel)"
    path_s = str(p.resolve())
    try:
        p.mkdir(parents=True, exist_ok=True)
        writable = os.access(p, os.W_OK)
        if not writable:
            return {
                "id": "schedules",
                "title": title,
                "ok": False,
                "detail": f"{path_s} — нет прав на запись",
                "level": "err",
            }
        return {
            "id": "schedules",
            "title": title,
            "ok": True,
            "detail": path_s,
            "level": "ok",
        }
    except Exception as exc:
        return {
            "id": "schedules",
            "title": title,
            "ok": False,
            "detail": f"{path_s} — {exc}",
            "level": "err",
        }


def collect_system_health() -> list[dict]:
    """Три проверки в фиксированном порядке."""
    return [
        check_django_database(),
        check_biota_database(),
        check_schedule_storage(),
    ]
