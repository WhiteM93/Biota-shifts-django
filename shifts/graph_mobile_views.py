"""Мобильный просмотр графика смен (только чтение, отдельно от /graph/)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from biota_shifts import schedule as biota_schedule
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts.schedule import (
    PREV_MONTH_KEYS,
    is_schedule_day_column,
    schedule_column_to_date,
    sort_schedule_day_columns,
)

from .auth_utils import biota_login_required, nav_permission_required
from .department_order import apply_department_order, load_department_order
from .graph_views import (
    _dept_rank_map,
    _employees_for_user,
    _norm_emp_code,
    _pos_rank_map,
    _schedule_with_department,
    _sort_graph_rows,
)
from .position_order import apply_position_order, load_position_order
from .ru_work_calendar import is_ru_non_working_day

WEEKDAY_SHORT = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
MONTH_NAMES_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

# Код → (заголовок группы, css-модификатор, буква в иконке)
MOBILE_CODE_GROUPS = (
    ("д", "День", "gm-grp--day", "Д"),
    ("н", "Ночь", "gm-grp--night", "Н"),
    ("от", "Отпуск", "gm-grp--vacation", "от"),
    ("б", "Больничный", "gm-grp--sick", "б"),
    ("п", "Прогул", "gm-grp--absent", "п"),
    ("кп", "Компенсация", "gm-grp--kp", "кп"),
)


def _parse_selected_date(request, *, default: date | None = None) -> date:
    today = date.today()
    default = default or today
    raw = (request.GET.get("date") or "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    try:
        y = int(request.GET.get("year") or today.year)
        m = int(request.GET.get("month") or today.month)
        y = max(2000, min(2100, y))
        m = max(1, min(12, m))
        if y == today.year and m == today.month:
            return today
        return date(y, m, 1)
    except (TypeError, ValueError):
        pass
    return default


def _col_key_for_date(d: date, year: int, month: int) -> str | None:
    if d.year == year and d.month == month:
        try:
            return str(d.day)
        except ValueError:
            return None
    for key in PREV_MONTH_KEYS:
        col_date = schedule_column_to_date(key, year, month)
        if col_date == d:
            return key
    return None


def _short_employee_name(full_name: str) -> str:
    parts = str(full_name or "").strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    if parts:
        return parts[0]
    return "—"


def _load_schedule_for_user(request, year: int, month: int) -> pd.DataFrame:
    employees_df = _employees_for_user(request)
    schedule_df = biota_schedule.load_schedule_table(employees_df, year, month)
    schedule_df = _schedule_with_department(schedule_df, employees_df)
    all_deps = apply_department_order(
        sorted(schedule_df["Отдел"].unique().tolist()),
        load_department_order(),
    )
    all_positions = apply_position_order(
        sorted(schedule_df["Должность"].unique().tolist()),
        load_position_order(),
    )
    schedule_df = schedule_df[
        schedule_df["Отдел"].isin(all_deps) & schedule_df["Должность"].isin(all_positions)
    ].copy()
    return _sort_graph_rows(
        schedule_df,
        _dept_rank_map(all_deps),
        _pos_rank_map(all_positions),
    ).reset_index(drop=True)


@biota_login_required
@nav_permission_required("graph")
@require_http_methods(["GET"])
def graph_mobile_view(request):
    try:
        selected = _parse_selected_date(request)
        year, month = selected.year, selected.month
        schedule_df = _load_schedule_for_user(request, year, month)
    except Exception as exc:
        return render(
            request,
            "shifts/error.html",
            {"title": "Ошибка", "message": str(exc), "hide_nav": True},
        )

    if schedule_df.empty:
        return render(
            request,
            "shifts/error.html",
            {
                "title": "Нет данных",
                "message": "График пуст или нет доступа к сотрудникам.",
                "hide_nav": True,
            },
        )

    base_url = reverse("graph_mobile")
    strip_start = selected - timedelta(days=21)
    strip_end = selected + timedelta(days=21)

    week_strip: list[dict] = []
    d = strip_start
    while d <= strip_end:
        col_key = _col_key_for_date(d, year, month)
        in_sheet = col_key is not None and col_key in schedule_df.columns
        week_strip.append(
            {
                "date": d,
                "iso": d.isoformat(),
                "weekday": WEEKDAY_SHORT[d.weekday()],
                "day_num": d.day,
                "day_label": (
                    f"{d.day}.{d.month:02d}" if d.month != month else str(d.day)
                ),
                "is_selected": d == selected,
                "is_weekend": d.weekday() >= 5,
                "is_non_working": is_ru_non_working_day(d),
                "in_sheet": in_sheet,
                "href": f"{base_url}?date={d.isoformat()}",
            }
        )
        d += timedelta(days=1)

    selected_col = _col_key_for_date(selected, year, month)
    day_shift_count = 0
    night_shift_count = 0
    groups: list[dict] = []

    if selected_col and selected_col in schedule_df.columns:
        for code, title, css_mod, icon in MOBILE_CODE_GROUPS:
            names: list[str] = []
            for _, row in schedule_df.iterrows():
                val = str(row.get(selected_col, "") or "").strip().lower()
                if val == code:
                    names.append(_short_employee_name(row.get("Сотрудник", "")))
                    if code == "д":
                        day_shift_count += 1
                    elif code == "н":
                        night_shift_count += 1
            if names:
                groups.append(
                    {
                        "code": code,
                        "title": title,
                        "css_mod": css_mod,
                        "icon": icon,
                        "count": len(names),
                        "names": names,
                    }
                )

    wd = WEEKDAY_SHORT[selected.weekday()]
    month_gen = MONTH_NAMES_GENITIVE.get(month, "")
    if selected == date.today():
        today_label = f"Сегодня · {wd}, {selected.day} {month_gen}"
    else:
        today_label = f"{wd}, {selected.day} {month_gen}"

    today = date.today()
    picker_year = today.year
    month_picker_choices: list[dict] = []
    for mm in range(1, 13):
        if picker_year == today.year and mm == today.month:
            pick_date = today
        else:
            pick_date = date(picker_year, mm, 1)
        month_picker_choices.append(
            {
                "month": mm,
                "label": MONTH_NAMES_RU[mm],
                "href": f"{base_url}?date={pick_date.isoformat()}",
                "is_selected": year == picker_year and month == mm,
                "is_current": picker_year == today.year and mm == today.month,
            }
        )

    return render(
        request,
        "shifts/graph_mobile.html",
        {
            "hide_nav": True,
            "year": year,
            "month": month,
            "month_name_upper": MONTH_NAMES_RU[month].upper(),
            "selected": selected,
            "selected_iso": selected.isoformat(),
            "today_label": today_label,
            "week_strip": week_strip,
            "day_shift_count": day_shift_count,
            "night_shift_count": night_shift_count,
            "groups": groups,
            "has_day_column": bool(selected_col),
            "desktop_graph_url": f"{reverse('graph')}?year={year}&month={month}",
            "month_picker_year": picker_year,
            "month_picker_choices": month_picker_choices,
        },
    )
