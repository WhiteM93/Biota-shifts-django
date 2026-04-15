"""Страница «СКУД»: статистика по отметкам и табелю, список отметок — как в Streamlit."""
from datetime import date, datetime, timedelta
from urllib.parse import quote

import pandas as pd
from django.http import HttpResponse
from django.shortcuts import render

from biota_shifts import db as biota_db
from biota_shifts import export as biota_export
from biota_shifts import logic as biota_logic
from biota_shifts.auth import (
    _filter_employees_for_user,
    _is_admin,
)
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts import schedule as biota_schedule
from biota_shifts.schedule import employee_label_row

from .auth_utils import biota_login_required, biota_user


def _fmt_minutes_human(v) -> str:
    try:
        mins = int(v)
    except (TypeError, ValueError):
        mins = 0
    mins = max(0, mins)
    if mins < 60:
        return f"{mins} мин"
    return f"{mins // 60} ч {mins % 60} мин"


def _employees_for_user(request):
    cfg = biota_db.db_config()
    employees_df = biota_db.load_employees(cfg)
    user = biota_user(request)
    if user and not _is_admin(user):
        employees_df = _filter_employees_for_user(employees_df, user)
    employees_df = employees_df.copy()
    employees_df["label"] = employees_df.apply(employee_label_row, axis=1)
    return employees_df


def _parse_year_month(request, default_y: int, default_m: int) -> tuple[int, int]:
    try:
        y = int(request.GET.get("year") or default_y)
    except (TypeError, ValueError):
        y = default_y
    try:
        m = int(request.GET.get("month") or default_m)
    except (TypeError, ValueError):
        m = default_m
    return max(2000, min(2100, y)), max(1, min(12, m))


def _skud_filter_employees(request, employees_df: pd.DataFrame):
    """Фильтры отдел/участок/должность отключены: для СКУД используем весь доступный сотрудникам список."""
    return employees_df.copy(), {}


def _df_to_table(df: pd.DataFrame | None) -> tuple[list[str], list[list[str]]]:
    if df is None or df.empty:
        return [], []
    cols = [str(c) for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        rows.append(["" if pd.isna(r[c]) else str(r[c]) for c in df.columns])
    return cols, rows


def _skud_load_bundle(request, employees_df: pd.DataFrame, filtered: pd.DataFrame, fmeta: dict):
    """Возвращает (context_dict, None) или (None, error_message)."""
    if filtered.empty:
        return None, "По выбранным отделу / участку / должности сотрудники не найдены."

    q = (request.GET.get("q") or "").strip().lower()
    labels_all = filtered["label"].tolist()
    if q:
        labels_choice = [lb for lb in labels_all if q in lb.lower()]
    else:
        labels_choice = labels_all
    if not labels_choice:
        return None, "По запросу никого не найдено — измените поиск или фильтры."

    sub = filtered[filtered["label"].isin(labels_choice)].copy()
    emp_param = (request.GET.get("emp") or "").strip()
    codes_ok = set(sub["emp_code"].astype(str))
    if emp_param and emp_param in codes_ok:
        selected_emp = emp_param
    else:
        selected_emp = str(sub.iloc[0]["emp_code"])
    selected_label = str(sub.loc[sub["emp_code"].astype(str) == selected_emp, "label"].iloc[0])

    ref_emp = selected_emp
    year_options = biota_db.merged_year_options(biota_db.db_config(), ref_emp)
    now = datetime.now()
    default_y = now.year if now.year in year_options else (year_options[0] if year_options else now.year)
    y, m = _parse_year_month(request, default_y, now.month)

    start_date, end_date = biota_schedule.month_bounds(date(y, m, 1))
    punch_day_from = start_date - timedelta(days=1)
    punch_day_to = end_date + timedelta(days=1)
    cfg = biota_db.db_config()

    try:
        schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
        df = biota_db.load_shifts(cfg, selected_emp, start_date, end_date)
        punches_df = biota_db.load_iclock_punches(cfg, selected_emp, punch_day_from, punch_day_to)
        stats_df = biota_logic.build_employee_stats_month(df, schedule_df, selected_emp, punches_df)
        punches_month_df = biota_logic.punches_list_for_month(punches_df, start_date, end_date)
    except Exception as exc:
        return None, str(exc)

    for col in ("Опоздал (мин)", "Ранний уход (мин)"):
        if col in stats_df.columns:
            stats_df[col] = stats_df[col].apply(
                lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else _fmt_minutes_human(x)
            )

    stats_cols, stats_rows = _df_to_table(stats_df)
    punch_cols, punch_rows = _df_to_table(punches_month_df)

    q_stats = request.GET.copy()
    q_stats["tab"] = "stats"
    q_ot = request.GET.copy()
    q_ot["tab"] = "otmetki"

    ctx = {
        "year": y,
        "month": m,
        "month_name": MONTH_NAMES_RU[m],
        "year_options": year_options,
        "month_choices": [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)],
        "selected_emp": selected_emp,
        "selected_label": selected_label,
        "employee_display_name": selected_label,
        "start_date": start_date,
        "end_date": end_date,
        "punch_count": len(punches_month_df) if punches_month_df is not None else 0,
        "stats_columns": stats_cols,
        "stats_rows": stats_rows,
        "punch_columns": punch_cols,
        "punch_rows": punch_rows,
        "search_q": request.GET.get("q") or "",
        "emp_options": [(str(r["emp_code"]), str(r["label"])) for _, r in sub.iterrows()],
        "filtered": filtered,
        "fmeta": fmeta,
        "all_deps": sorted(employees_df["department_name"].unique().tolist()),
        "qs_stats": q_stats.urlencode(),
        "qs_ot": q_ot.urlencode(),
        "active_tab": request.GET.get("tab") or "stats",
        "query_string": request.GET.urlencode(),
        "error_message": None,
    }
    return ctx, None


def _skud_empty_shell(request, employees_df: pd.DataFrame, fmeta: dict, err: str | None):
    now = datetime.now()
    ref_emp = str(employees_df.iloc[0]["emp_code"])
    year_options = biota_db.merged_year_options(biota_db.db_config(), ref_emp)
    default_y = now.year if now.year in year_options else (year_options[0] if year_options else now.year)
    y, m = _parse_year_month(request, default_y, now.month)
    q_stats = request.GET.copy()
    q_stats["tab"] = "stats"
    q_ot = request.GET.copy()
    q_ot["tab"] = "otmetki"
    return {
        "error_message": err,
        "all_deps": sorted(employees_df["department_name"].unique().tolist()),
        "fmeta": fmeta,
        "month_choices": [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)],
        "year_options": year_options,
        "year": y,
        "month": m,
        "emp_options": [],
        "search_q": request.GET.get("q") or "",
        "stats_columns": [],
        "stats_rows": [],
        "punch_columns": [],
        "punch_rows": [],
        "active_tab": request.GET.get("tab") or "stats",
        "qs_stats": q_stats.urlencode(),
        "qs_ot": q_ot.urlencode(),
        "selected_emp": "",
        "selected_label": "",
        "employee_display_name": "",
        "start_date": None,
        "end_date": None,
        "punch_count": 0,
        "month_name": MONTH_NAMES_RU[m],
        "query_string": request.GET.urlencode(),
    }


@biota_login_required
def skud_view(request):
    try:
        employees_df = _employees_for_user(request)
    except Exception as exc:
        return render(request, "shifts/error.html", {"title": "Ошибка БД", "message": str(exc)})
    if employees_df.empty:
        return render(
            request,
            "shifts/error.html",
            {"title": "Нет сотрудников", "message": "Нет доступа к списку сотрудников или база пуста."},
        )

    filtered, fmeta = _skud_filter_employees(request, employees_df)
    if filtered.empty:
        return render(
            request,
            "shifts/skud.html",
            _skud_empty_shell(request, employees_df, fmeta, "По выбранным отделу / участку / должности сотрудники не найдены."),
        )

    bundle, err = _skud_load_bundle(request, employees_df, filtered, fmeta)
    if err:
        return render(request, "shifts/skud.html", _skud_empty_shell(request, employees_df, fmeta, err))

    return render(request, "shifts/skud.html", bundle)


def _safe_filename_part(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-", ".") else "_" for c in s)[:120]


@biota_login_required
def skud_punches_csv(request):
    employees_df = _employees_for_user(request)
    if employees_df.empty:
        return HttpResponse("Нет сотрудников", status=400)
    filtered, fmeta = _skud_filter_employees(request, employees_df)
    bundle, err = _skud_load_bundle(request, employees_df, filtered, fmeta)
    if err:
        return HttpResponse(err, status=400)
    punches_df = biota_db.load_iclock_punches(
        biota_db.db_config(),
        bundle["selected_emp"],
        bundle["start_date"] - timedelta(days=1),
        bundle["end_date"] + timedelta(days=1),
    )
    punches_month_df = biota_logic.punches_list_for_month(
        punches_df,
        bundle["start_date"],
        bundle["end_date"],
    )
    data = punches_month_df.to_csv(index=False).encode("utf-8-sig")
    fn = f"otmetki_{bundle['selected_emp']}_{bundle['start_date'].strftime('%Y_%m')}.csv"
    resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


@biota_login_required
def skud_stats_excel(request):
    employees_df = _employees_for_user(request)
    if employees_df.empty:
        return HttpResponse("Нет сотрудников", status=400)
    filtered, fmeta = _skud_filter_employees(request, employees_df)
    bundle, err = _skud_load_bundle(request, employees_df, filtered, fmeta)
    if err:
        return HttpResponse(err, status=400)
    cfg = biota_db.db_config()
    start_date, end_date = bundle["start_date"], bundle["end_date"]
    schedule_df = biota_schedule.load_schedule_table(employees_df, bundle["year"], bundle["month"])
    df = biota_db.load_shifts(cfg, bundle["selected_emp"], start_date, end_date)
    punches_df = biota_db.load_iclock_punches(
        cfg,
        bundle["selected_emp"],
        start_date - timedelta(days=1),
        end_date + timedelta(days=1),
    )
    stats_df = biota_logic.build_employee_stats_month(df, schedule_df, bundle["selected_emp"], punches_df)
    data = biota_export.build_pretty_excel(stats_df, sheet_name="Статистика")
    name_part = _safe_filename_part(bundle["employee_display_name"].replace(" ", "_"))
    fn = f"stat_{bundle['selected_emp']}_{name_part}_{start_date.strftime('%Y_%m')}.xlsx"
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fn)}"
    return resp


@biota_login_required
def skud_stats_csv(request):
    employees_df = _employees_for_user(request)
    if employees_df.empty:
        return HttpResponse("Нет сотрудников", status=400)
    filtered, fmeta = _skud_filter_employees(request, employees_df)
    bundle, err = _skud_load_bundle(request, employees_df, filtered, fmeta)
    if err:
        return HttpResponse(err, status=400)
    cfg = biota_db.db_config()
    start_date, end_date = bundle["start_date"], bundle["end_date"]
    schedule_df = biota_schedule.load_schedule_table(employees_df, bundle["year"], bundle["month"])
    df = biota_db.load_shifts(cfg, bundle["selected_emp"], start_date, end_date)
    punches_df = biota_db.load_iclock_punches(
        cfg,
        bundle["selected_emp"],
        start_date - timedelta(days=1),
        end_date + timedelta(days=1),
    )
    stats_df = biota_logic.build_employee_stats_month(df, schedule_df, bundle["selected_emp"], punches_df)
    data = stats_df.to_csv(index=False).encode("utf-8-sig")
    name_part = _safe_filename_part(bundle["employee_display_name"].replace(" ", "_"))
    fn = f"stat_{bundle['selected_emp']}_{name_part}_{start_date.strftime('%Y_%m')}.csv"
    resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fn)}"
    return resp


@biota_login_required
def skud_stats_pdf(request):
    employees_df = _employees_for_user(request)
    if employees_df.empty:
        return HttpResponse("Нет сотрудников", status=400)
    filtered, fmeta = _skud_filter_employees(request, employees_df)
    bundle, err = _skud_load_bundle(request, employees_df, filtered, fmeta)
    if err:
        return HttpResponse(err, status=400)
    cfg = biota_db.db_config()
    start_date, end_date = bundle["start_date"], bundle["end_date"]
    schedule_df = biota_schedule.load_schedule_table(employees_df, bundle["year"], bundle["month"])
    df = biota_db.load_shifts(cfg, bundle["selected_emp"], start_date, end_date)
    punches_df = biota_db.load_iclock_punches(
        cfg,
        bundle["selected_emp"],
        start_date - timedelta(days=1),
        end_date + timedelta(days=1),
    )
    stats_df = biota_logic.build_employee_stats_month(df, schedule_df, bundle["selected_emp"], punches_df)
    try:
        data = biota_export.build_stats_pdf(
            stats_df, bundle["employee_display_name"], start_date
        )
    except Exception as exc:
        return HttpResponse(f"PDF недоступен: {exc}", status=500)
    name_part = _safe_filename_part(bundle["employee_display_name"].replace(" ", "_"))
    fn = f"stat_{bundle['selected_emp']}_{name_part}_{start_date.strftime('%Y_%m')}.pdf"
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fn)}"
    return resp
