"""Страница «Нарушение дисциплины»: опоздания и ранние уходы за месяц."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pandas as pd
from django.shortcuts import render

from biota_shifts import db as biota_db
from biota_shifts import logic as biota_logic
from biota_shifts.auth import employees_df_for_nav
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts.schedule import employee_label_row

from .auth_utils import biota_login_required, biota_user, nav_permission_required
from .graph_schedule_source import get_skud_schedule_source, load_schedule_table_resolved


def _fmt_minutes_human(v) -> str:
    try:
        mins = int(v)
    except (TypeError, ValueError):
        mins = 0
    mins = max(0, mins)
    if mins <= 0:
        return "—"
    if mins < 60:
        return f"{mins} мин"
    return f"{mins // 60} ч {mins % 60} мин"


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


def _employees_for_user(request):
    cfg = biota_db.db_config()
    employees_df = biota_db.load_employees(cfg)
    employees_df = employees_df_for_nav(biota_user(request), "skud", employees_df)
    employees_df = employees_df.copy()
    employees_df["label"] = employees_df.apply(employee_label_row, axis=1)
    return employees_df


def _build_discipline_rows(
    cfg: dict,
    emp_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    year: int,
    month: int,
) -> list[dict]:
    """Сотрудники с опозданиями или ранним уходом за месяц + дни нарушений."""
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    emp_codes = []
    labels = {}
    for _, r in emp_df.iterrows():
        ec = biota_logic.normalize_emp_code(r.get("emp_code"))
        if not ec:
            continue
        emp_codes.append(ec)
        labels[ec] = str(r.get("label") or ec)
        if "department_name" in r and pd.notna(r.get("department_name")):
            labels[ec] = labels[ec]  # label already includes dept via employee_label_row
    emp_codes = list(dict.fromkeys(emp_codes))
    if not emp_codes:
        return []

    p_from = start - timedelta(days=1)
    p_to = end + timedelta(days=1)
    df_shifts_all = biota_db.load_shifts_batch(cfg, emp_codes, start, end)
    p_df_all = biota_db.load_iclock_punches_batch(cfg, emp_codes, p_from, p_to)
    _ec_shift = df_shifts_all["emp_code"].map(biota_logic.normalize_emp_code) if not df_shifts_all.empty else pd.Series(dtype=str)
    _ec_punch = p_df_all["emp_code"].map(biota_logic.normalize_emp_code) if not p_df_all.empty else pd.Series(dtype=str)

    out: list[dict] = []
    for ec in emp_codes:
        df_b = (
            df_shifts_all[_ec_shift == ec].drop(columns=["emp_code"], errors="ignore")
            if not df_shifts_all.empty
            else pd.DataFrame()
        )
        if df_b.empty:
            continue
        p_df = (
            p_df_all[_ec_punch == ec].drop(columns=["emp_code"], errors="ignore")
            if not p_df_all.empty
            else pd.DataFrame()
        )
        stats = biota_logic.build_employee_stats_month(df_b, schedule_df, ec, p_df)
        if stats.empty:
            continue

        days: list[dict] = []
        late_total = 0
        early_total = 0
        late_days = 0
        early_days = 0
        same_mark_days = 0
        for _, row in stats.iterrows():
            late = biota_logic._stat_minutes_cell_to_int(row.get("Опоздал (мин)"))
            early = biota_logic._stat_minutes_cell_to_int(row.get("Ранний уход (мин)"))
            arrived = str(row.get("Пришел") or "").strip()
            left = str(row.get("Ушел") or "").strip()
            # Одна и та же отметка на приход и уход → забыли отметиться с одной стороны
            same_mark = bool(arrived and left and arrived == left)
            if late <= 0 and early <= 0 and not same_mark:
                continue
            late_total += late
            early_total += early
            if late > 0:
                late_days += 1
            if early > 0:
                early_days += 1
            if same_mark:
                same_mark_days += 1
            raw_date = row.get("Дата")
            try:
                d_obj = pd.Timestamp(raw_date).date()
                date_label = d_obj.strftime("%d.%m.%Y")
                weekday = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][d_obj.weekday()]
            except Exception:
                date_label = str(raw_date or "")
                weekday = ""
            note = ""
            if same_mark:
                note = "Одинаковое время прихода и ухода — вероятно, забыли отметиться на приходе или на уходе"
            days.append(
                {
                    "date": date_label,
                    "weekday": weekday,
                    "graph": str(row.get("График") or "—"),
                    "arrived": arrived or "—",
                    "left": left or "—",
                    "late_min": late,
                    "early_min": early,
                    "late_h": _fmt_minutes_human(late),
                    "early_h": _fmt_minutes_human(early),
                    "same_mark": same_mark,
                    "note": note,
                }
            )
        if not days:
            continue
        dept = ""
        match = emp_df[emp_df["emp_code"].map(biota_logic.normalize_emp_code) == ec]
        if not match.empty and "department_name" in match.columns:
            dept = str(match.iloc[0].get("department_name") or "").strip()
        out.append(
            {
                "emp_code": ec,
                "label": labels.get(ec, ec),
                "department": dept,
                "late_total": late_total,
                "early_total": early_total,
                "total": late_total + early_total,
                "late_h": _fmt_minutes_human(late_total),
                "early_h": _fmt_minutes_human(early_total),
                "total_h": _fmt_minutes_human(late_total + early_total),
                "late_days": late_days,
                "early_days": early_days,
                "same_mark_days": same_mark_days,
                "days": days,
            }
        )

    out.sort(key=lambda r: (-r["total"], r["label"]))
    return out


@biota_login_required
@nav_permission_required("skud")
def discipline_view(request):
    return render(request, "shifts/discipline.html", _discipline_context(request))


@biota_login_required
@nav_permission_required("skud")
def discipline_print_view(request):
    """Версия для печати: сводка + каждый сотрудник отдельным блоком."""
    ctx = _discipline_context(request)
    emp = (request.GET.get("emp") or "").strip()
    if emp:
        ec = biota_logic.normalize_emp_code(emp) or emp
        ctx["rows"] = [r for r in ctx["rows"] if r.get("emp_code") == ec]
        ctx["emp_count"] = len(ctx["rows"])
        ctx["print_one"] = True
        ctx["print_all"] = False
    else:
        # Для раздачи: отдел → ФИО, чтобы листы можно было разложить по подразделениям
        ctx["rows"] = sorted(
            ctx["rows"],
            key=lambda r: (
                (r.get("department") or "\uffff").casefold(),
                (r.get("label") or "").casefold(),
            ),
        )
        ctx["print_one"] = False
        ctx["print_all"] = True
    total_late = sum(r["late_total"] for r in ctx["rows"])
    total_early = sum(r["early_total"] for r in ctx["rows"])
    total_same = sum(int(r.get("same_mark_days") or 0) for r in ctx["rows"])
    ctx["total_late_h"] = _fmt_minutes_human(total_late)
    ctx["total_early_h"] = _fmt_minutes_human(total_early)
    ctx["total_all_h"] = _fmt_minutes_human(total_late + total_early)
    ctx["total_same_mark_days"] = total_same
    return render(request, "shifts/discipline_print.html", ctx)


def _discipline_context(request) -> dict:
    now = datetime.now()
    y, m = _parse_year_month(request, now.year, now.month)
    employees_df = _employees_for_user(request)
    cfg = biota_db.db_config()

    year_options: list[int] = []
    if not employees_df.empty:
        ref = biota_logic.normalize_emp_code(employees_df.iloc[0]["emp_code"]) or str(
            employees_df.iloc[0]["emp_code"]
        ).strip()
        year_options = biota_db.merged_year_options(cfg, ref) or list(range(now.year - 2, now.year + 2))
    if not year_options:
        year_options = [now.year]
    if y not in year_options:
        y = year_options[0]

    error = ""
    rows: list[dict] = []
    if employees_df.empty:
        error = "Нет сотрудников для отчёта — проверьте права или справочник."
    else:
        try:
            schedule_df = load_schedule_table_resolved(
                employees_df, y, m, source=get_skud_schedule_source()
            )
        except Exception as exc:
            error = f"Не удалось загрузить график: {exc}"
            schedule_df = None
        if schedule_df is not None:
            try:
                rows = _build_discipline_rows(cfg, employees_df, schedule_df, y, m)
            except Exception as exc:
                error = f"Ошибка расчёта нарушений: {exc}"

    total_late = sum(r["late_total"] for r in rows)
    total_early = sum(r["early_total"] for r in rows)

    return {
        "year": y,
        "month": m,
        "month_name": MONTH_NAMES_RU[m],
        "year_options": year_options,
        "month_choices": [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)],
        "error": error,
        "rows": rows,
        "emp_count": len(rows),
        "total_late_h": _fmt_minutes_human(total_late),
        "total_early_h": _fmt_minutes_human(total_early),
        "total_all_h": _fmt_minutes_human(total_late + total_early),
    }
