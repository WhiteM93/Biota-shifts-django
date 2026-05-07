"""Read-only проверки к PostgreSQL Biota (те же параметры, что у Django)."""
from __future__ import annotations

import time
from typing import Any

import psycopg
from fastapi import APIRouter, Query

from api_fastapi.biota_env import biota_db_connection_kwargs

router = APIRouter(prefix="/biota", tags=["biota"])


@router.get("/ping")
def biota_ping() -> dict[str, Any]:
    """SELECT 1 в Biota DB; для мониторинга и быстрой диагностики."""
    kw = biota_db_connection_kwargs()
    t0 = time.perf_counter()
    try:
        with psycopg.connect(**kw) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "ok": True,
            "elapsed_ms": elapsed_ms,
            "host": kw["host"],
            "dbname": kw["dbname"],
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "host": kw["host"],
            "dbname": kw["dbname"],
            "error": str(exc),
        }


@router.get("/employees/sample")
def biota_employees_sample(
    limit: int = Query(default=5, ge=1, le=50, description="Сколько строк вернуть"),
) -> dict[str, Any]:
    """Пример read-only выборки из personnel_employee (без привязки к Django ORM)."""
    kw = biota_db_connection_kwargs()
    sql = """
    select coalesce(e.emp_code::text, '') as emp_code,
           coalesce(e.last_name, '') as last_name,
           coalesce(e.first_name, '') as first_name
    from personnel_employee e
    where coalesce(e.emp_code, '') <> ''
    order by e.emp_code
    limit %s
    """
    try:
        with psycopg.connect(**kw) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (limit,))
                cols = [d.name for d in cur.description] if cur.description else []
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"ok": True, "count": len(rows), "items": rows}
    except Exception as exc:
        return {"ok": False, "count": 0, "items": [], "error": str(exc)}
