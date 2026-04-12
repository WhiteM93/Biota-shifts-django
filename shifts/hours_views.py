"""Страница «Часы по дням» — сетка как в Графике, факт часов из Biota."""
from datetime import date, datetime

import pandas as pd
from django.http import HttpResponse
from django.shortcuts import render

from biota_shifts import db as biota_db
from biota_shifts import export as biota_export
from biota_shifts import logic as biota_logic
from biota_shifts.auth import _filter_employees_for_user, _is_admin
from biota_shifts.constants import HOURS_GRID_NO_PUNCH, HOURS_GRID_SUFFIX_OUTSIDE_GRAPH, MONTH_NAMES_RU
from biota_shifts import schedule as biota_schedule

from .auth_utils import biota_login_required, biota_user
from .ru_work_calendar import is_ru_non_working_day


def _employees_for_user(request):
    cfg = biota_db.db_config()
    employees_df = biota_db.load_employees(cfg)
    user = biota_user(request)
    if user and not _is_admin(user):
        employees_df = _filter_employees_for_user(employees_df, user)
    return employees_df


def _parse_year_month(request, default_y: int, default_m: int) -> tuple[int, int]:
    try:
        y = int(request.GET.get("year") or request.POST.get("year") or default_y)
    except (TypeError, ValueError):
        y = default_y
    try:
        m = int(request.GET.get("month") or request.POST.get("month") or default_m)
    except (TypeError, ValueError):
        m = default_m
    return max(2000, min(2100, y)), max(1, min(12, m))


def _filter_lists(request, employees_df):
    """Отделы и должности из GET (как чекбоксы Streamlit): пустой список = все."""
    dep_mode = request.GET.get("dep_mode", "all")
    pos_mode = request.GET.get("pos_mode", "all")

    all_deps = sorted(employees_df["department_name"].unique().tolist())
    dep_list = request.GET.getlist("dep")
    if dep_mode == "all":
        selected_deps = all_deps
    else:
        selected_deps = [d for d in dep_list if d in all_deps]

    by_dep = employees_df[employees_df["department_name"].isin(selected_deps)].copy()
    all_pos = sorted(by_dep["position_name"].unique().tolist())
    pos_list = request.GET.getlist("pos")
    if pos_mode == "all":
        selected_pos = all_pos
    else:
        selected_pos = [p for p in pos_list if p in all_pos]

    filtered = employees_df[
        employees_df["department_name"].isin(selected_deps)
        & employees_df["position_name"].isin(selected_pos)
    ].copy()
    return filtered, selected_deps, selected_pos, all_deps, all_pos, dep_mode, pos_mode


@biota_login_required
def hours_view(request):
    now = datetime.now()
    try:
        employees_df = _employees_for_user(request)
    except Exception as exc:
        return render(request, "shifts/error.html", {"title": "Ошибка БД", "message": str(exc)})
    if employees_df.empty:
        return render(
            request,
            "shifts/error.html",
            {"title": "Нет сотрудников", "message": "Нет доступа к списку сотрудников."},
        )

    ref_emp = str(employees_df.iloc[0]["emp_code"])
    year_options = biota_db.merged_year_options(biota_db.db_config(), ref_emp)
    default_y = now.year if now.year in year_options else (year_options[0] if year_options else now.year)

    y, m = _parse_year_month(request, default_y, now.month)
    filtered, sel_deps, sel_pos, all_deps, all_pos, dep_mode, pos_mode = _filter_lists(request, employees_df)

    schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
    err_msg = None
    grid_view = None
    day_headers = []
    non_working_days: list[str] = []
    table_rows = []

    if schedule_df.empty:
        err_msg = "Нет строк графика за выбранный месяц."
    elif filtered.empty:
        err_msg = "По выбранным отделу и должности сотрудники не найдены."
    else:
        allow_hc = frozenset(filtered["emp_code"].astype(str))
        schedule_df_h = schedule_df[schedule_df["Код"].astype(str).isin(allow_hc)].copy()
        if schedule_df_h.empty:
            err_msg = "В графике за этот месяц нет сотрудников из выбранных отдела и должности."
        else:
            try:
                codes_h = schedule_df_h["Код"].astype(str).tolist()
                start_date, end_date = biota_schedule.month_bounds(date(y, m, 1))
                hours_batch_df = biota_db.load_shifts_hours_batch(
                    biota_db.db_config(), codes_h, start_date, end_date
                )
                grid_hours_df = biota_logic.build_hours_grid_from_schedule(
                    schedule_df_h, hours_batch_df
                )
                day_cols_h = sorted(
                    [c for c in schedule_df_h.columns if str(c).isdigit()],
                    key=lambda x: int(x),
                )
                cols = ["Сотрудник"] + day_cols_h
                grid_view = grid_hours_df[cols].copy()
                for d in day_cols_h:
                    di = int(d)
                    day_date = date(y, m, di)
                    is_non_working = is_ru_non_working_day(day_date)
                    day_headers.append((d, str(d), is_non_working))
                    if is_non_working:
                        non_working_days.append(str(d))
                for _, r in grid_view.iterrows():
                    row_cells = []
                    for c in day_cols_h:
                        v = "" if pd.isna(r[c]) else str(r[c])
                        row_cells.append(
                            {
                                "value": v,
                                "is_non_working": str(c) in non_working_days,
                            }
                        )
                    table_rows.append(
                        {
                            "name": r["Сотрудник"],
                            "cells": row_cells,
                        }
                    )
            except Exception as exc:
                err_msg = f"Не удалось загрузить часы по сотрудникам: {exc}"

    month_choices = [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)]
    query_string = request.GET.urlencode()

    ctx = {
        "year": y,
        "month": m,
        "month_name": MONTH_NAMES_RU[m],
        "year_options": year_options,
        "month_choices": month_choices,
        "all_deps": all_deps,
        "all_pos": all_pos,
        "sel_deps": sel_deps,
        "sel_pos": sel_pos,
        "dep_mode_pick": dep_mode != "all",
        "pos_mode_pick": pos_mode != "all",
        "grid_view": grid_view,
        "day_headers": day_headers,
        "non_working_days": non_working_days,
        "table_rows": table_rows,
        "error_message": err_msg,
        "no_punch": HOURS_GRID_NO_PUNCH,
        "suffix_out": HOURS_GRID_SUFFIX_OUTSIDE_GRAPH,
        "query_string": query_string,
    }
    return render(request, "shifts/hours.html", ctx)


def _hours_grid_for_download(request):
    employees_df = _employees_for_user(request)
    if employees_df.empty:
        return None, "Нет сотрудников"
    now = datetime.now()
    ref_emp = str(employees_df.iloc[0]["emp_code"])
    year_options = biota_db.merged_year_options(biota_db.db_config(), ref_emp)
    default_y = now.year if now.year in year_options else (year_options[0] if year_options else now.year)
    y, m = _parse_year_month(request, default_y, now.month)
    filtered, _, _, _, _, _, _ = _filter_lists(request, employees_df)
    schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
    if schedule_df.empty or filtered.empty:
        return None, "Нет данных"
    allow_hc = frozenset(filtered["emp_code"].astype(str))
    schedule_df_h = schedule_df[schedule_df["Код"].astype(str).isin(allow_hc)].copy()
    if schedule_df_h.empty:
        return None, "Нет строк"
    start_date, end_date = biota_schedule.month_bounds(date(y, m, 1))
    codes_h = schedule_df_h["Код"].astype(str).tolist()
    hours_batch_df = biota_db.load_shifts_hours_batch(
        biota_db.db_config(), codes_h, start_date, end_date
    )
    grid_hours_df = biota_logic.build_hours_grid_from_schedule(schedule_df_h, hours_batch_df)
    day_cols_h = sorted(
        [c for c in schedule_df_h.columns if str(c).isdigit()],
        key=lambda x: int(x),
    )
    grid_view = grid_hours_df[["Сотрудник"] + day_cols_h].copy()
    return (grid_view, y, m), None


@biota_login_required
def hours_excel(request):
    result, err = _hours_grid_for_download(request)
    if err:
        return HttpResponse(err, status=400)
    grid_view, y, m = result
    data = biota_export.build_pretty_excel(grid_view, sheet_name="Часы")
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="chasy_po_dnyam_{y}_{m:02d}.xlsx"'
    return resp


@biota_login_required
def hours_pdf(request):
    result, err = _hours_grid_for_download(request)
    if err:
        return HttpResponse(err, status=400)
    grid_view, y, m = result
    try:
        data = biota_export.build_hours_grid_pdf(grid_view, y, m)
    except Exception as exc:
        return HttpResponse(f"PDF недоступен: {exc}", status=500)
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="chasy_po_dnyam_{y}_{m:02d}.pdf"'
    return resp
