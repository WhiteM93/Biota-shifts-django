"""Журнал действий на страницах «График» и «Регламенты» (отладка для админа)."""
from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from biota_shifts.schedule import PREV_MONTH_KEYS, is_schedule_day_column, sort_schedule_day_columns


def _norm_emp_code(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _parse_schedule_cell_post_key(key: str, day_col_keys: list[str]) -> tuple[str, str] | None:
    if not key.startswith("cell_"):
        return None
    rest = key[5:]
    if not rest:
        return None
    for col_key in sorted(day_col_keys, key=len, reverse=True):
        suffix = f"_{col_key}"
        if rest.endswith(suffix):
            code = rest[: -len(suffix)]
            if code:
                return code, col_key
    return None


def _schedule_day_col_keys(day_columns) -> list[str]:
    return [str(d) for d in day_columns]

SECTION_GRAPH = "graph"
SECTION_REGULATIONS = "regulations"
SECTION_CHOICES = (SECTION_GRAPH, SECTION_REGULATIONS)

_MAX_ROWS_PER_SECTION = 3000

# Клиент
EVT_CLIENT_EDIT_ON = "client_edit_on"
EVT_CLIENT_EDIT_OFF = "client_edit_off"
EVT_CLIENT_SAVE_START = "client_save_start"
EVT_CLIENT_SAVE_OK = "client_save_ok"
EVT_CLIENT_SAVE_FAIL = "client_save_fail"
EVT_CLIENT_FILTER = "client_filter"
EVT_CLIENT_BRUSH = "client_brush"
EVT_CLIENT_CELL = "client_cell"

# Сервер
EVT_SERVER_GRAPH_SAVE = "server_graph_save"
EVT_SERVER_GRAPH_UPLOAD = "server_graph_upload"
EVT_SERVER_GRAPH_REJECT = "server_graph_reject"
EVT_SERVER_REG_SAVE = "server_reg_save"
EVT_SERVER_REG_META = "server_reg_meta"
EVT_SERVER_REG_REJECT = "server_reg_reject"


def _actor(request: HttpRequest | None) -> str:
    if not request:
        return ""
    from shifts.auth_utils import biota_user

    return (biota_user(request) or "").strip() or "—"


def record_section_action(
    section: str,
    event_type: str,
    *,
    actor: str = "",
    summary: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    if section not in SECTION_CHOICES:
        return
    et = (event_type or "").strip()[:32]
    if not et:
        return
    from shifts.models import SectionActionLog

    SectionActionLog.objects.create(
        section=section,
        event_type=et,
        actor_username=(actor or "—")[:120],
        summary=(summary or "")[:500],
        details=details if isinstance(details, dict) else {},
    )
    qs = SectionActionLog.objects.filter(section=section).order_by("-id")
    excess = qs.count() - _MAX_ROWS_PER_SECTION
    if excess > 0:
        ids = list(qs.values_list("id", flat=True)[_MAX_ROWS_PER_SECTION:])
        if ids:
            SectionActionLog.objects.filter(id__in=ids).delete()


def record_from_request(
    request: HttpRequest,
    section: str,
    event_type: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> None:
    record_section_action(
        section,
        event_type,
        actor=_actor(request),
        summary=summary,
        details=details,
    )


def analyze_graph_save_post(
    request: HttpRequest,
    full_schedule_df,
    *,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Статистика POST сохранения графика (только dirty-ячейки с клиента)."""
    day_columns = sort_schedule_day_columns(
        [c for c in full_schedule_df.columns if is_schedule_day_column(c)],
        year,
        month,
    )
    col_keys = _schedule_day_col_keys(day_columns)
    code_series = full_schedule_df["Код"].map(_norm_emp_code)
    known_codes = set(code_series.tolist())

    post_keys = [k for k in request.POST if k.startswith("cell_")]
    applied: list[str] = []
    unknown_codes: list[str] = []
    invalid_code: list[str] = []
    skipped_prev: list[str] = []

    for key in post_keys:
        parsed = _parse_schedule_cell_post_key(key, col_keys)
        if not parsed:
            invalid_code.append(key[:40])
            continue
        code, col_key = parsed
        code = _norm_emp_code(code)
        if col_key in PREV_MONTH_KEYS:
            skipped_prev.append(f"{code}:{col_key}")
            continue
        if code not in known_codes:
            unknown_codes.append(code)
            continue
        applied.append(f"{code}:{col_key}")

    dirty_dom = request.POST.get("_debug_dirty_count")
    changed_dom = request.POST.get("_debug_changed_count")
    visible_dom = request.POST.get("_debug_visible_count")

    return {
        "year": year,
        "month": month,
        "dep_mode": (request.POST.get("dep_mode") or "").strip(),
        "pos_mode": (request.POST.get("pos_mode") or "").strip(),
        "post_cell_fields": len(post_keys),
        "applied_cells": len(applied),
        "unknown_codes": sorted(set(unknown_codes))[:30],
        "invalid_keys": invalid_code[:10],
        "skipped_prev_month": len(skipped_prev),
        "client_dirty_count": int(dirty_dom) if str(dirty_dom or "").isdigit() else None,
        "client_changed_count": int(changed_dom) if str(changed_dom or "").isdigit() else None,
        "client_visible_inputs": int(visible_dom) if str(visible_dom or "").isdigit() else None,
        "sample_applied": applied[:15],
    }


def log_graph_save(
    request: HttpRequest,
    full_schedule_df,
    *,
    year: int,
    month: int,
    saved_name: str,
    stats: dict | None = None,
) -> dict:
    if stats is None:
        stats = analyze_graph_save_post(request, full_schedule_df, year=year, month=month)
    unknown_n = len(stats.get("unknown_codes") or [])
    summary = (
        f"Сохранение {year}-{month:02d}: в POST {stats['post_cell_fields']} ячеек, "
        f"записано {stats['applied_cells']}"
    )
    if unknown_n:
        summary += f", неизвестных кодов {unknown_n}"
    if stats.get("client_changed_count") is not None:
        summary += f", изменено на клиенте {stats['client_changed_count']}"
    elif stats.get("client_dirty_count") is not None:
        summary += f", dirty на клиенте {stats['client_dirty_count']}"
    record_from_request(
        request,
        SECTION_GRAPH,
        EVT_SERVER_GRAPH_SAVE,
        summary,
        {**stats, "saved_file": saved_name},
    )
    return stats
