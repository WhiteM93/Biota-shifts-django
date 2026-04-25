"""Страница «График» — как в Streamlit: таблица по дням, сохранение Excel, выгрузка/загрузка."""
from datetime import date, datetime

from django.contrib import messages
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from biota_shifts import db as biota_db
from biota_shifts.auth import employees_df_for_nav
from biota_shifts.constants import MONTH_NAMES_RU, SCHEDULE_CODES
from biota_shifts import export as biota_export
from biota_shifts import schedule as biota_schedule
from biota_shifts.schedule import (
    PREV_MONTH_KEYS,
    is_schedule_day_column,
    schedule_column_to_date,
    sort_schedule_day_columns,
)

from .auth_utils import biota_login_required, biota_user, nav_permission_required
from .department_order import apply_department_order, load_department_order
from .position_order import apply_position_order, load_position_order
from .ru_work_calendar import is_ru_non_working_day


DEPT_COLOR_CLASSES = [
    "dept-c1",
    "dept-c2",
    "dept-c3",
    "dept-c4",
    "dept-c5",
    "dept-c6",
    "dept-c7",
    "dept-c8",
]


def _employees_for_user(request):
    cfg = biota_db.db_config()
    employees_df = biota_db.load_employees(cfg)
    return employees_df_for_nav(biota_user(request), "graph", employees_df)


def _parse_year_month(request, *, default_year: int, default_month: int) -> tuple[int, int]:
    try:
        y = int(request.GET.get("year") or request.POST.get("year") or default_year)
    except (TypeError, ValueError):
        y = default_year
    try:
        m = int(request.GET.get("month") or request.POST.get("month") or default_month)
    except (TypeError, ValueError):
        m = default_month
    y = max(2000, min(2100, y))
    m = max(1, min(12, m))
    return y, m


def _schedule_with_department(schedule_df, employees_df):
    dep_map = {
        str(r["emp_code"]): str(r.get("department_name", "") or "").strip()
        for _, r in employees_df.iterrows()
    }
    out = schedule_df.copy()
    out["Отдел"] = out["Код"].astype(str).map(dep_map).fillna("")
    out["Отдел"] = out["Отдел"].apply(lambda v: v if str(v).strip() else "Без отдела")
    pos_map = {
        str(r["emp_code"]): str(r.get("position_name") or "").strip()
        for _, r in employees_df.iterrows()
    }
    out["Должность"] = out["Код"].astype(str).map(pos_map).fillna("")
    out["Должность"] = out["Должность"].apply(lambda v: v if str(v).strip() else "Без должности")
    last_map = {
        str(r["emp_code"]): str(r.get("last_name", "") or "").strip() for _, r in employees_df.iterrows()
    }
    first_map = {
        str(r["emp_code"]): str(r.get("first_name", "") or "").strip() for _, r in employees_df.iterrows()
    }
    out["_last_name"] = out["Код"].astype(str).map(last_map).fillna("")
    out["_first_name"] = out["Код"].astype(str).map(first_map).fillna("")
    return out


def _extract_selected_deps(request, all_deps, *, from_post: bool):
    """Режим «все отделы» — весь список; «по списку» — только отмеченные (пустой список = ни один)."""
    source = request.POST if from_post else request.GET
    dep_mode = source.get("dep_mode", "all")
    if dep_mode == "all":
        return list(all_deps), dep_mode
    dep_list = source.getlist("dep")
    selected = [d for d in dep_list if d in all_deps]
    return selected, dep_mode


def _extract_selected_positions(request, all_positions, *, from_post: bool):
    """Режим «все должности» — весь список; «по списку» — только отмеченные."""
    source = request.POST if from_post else request.GET
    pos_mode = source.get("pos_mode", "all")
    if pos_mode == "all":
        return list(all_positions), pos_mode
    pos_list = source.getlist("pos")
    selected = [p for p in pos_list if p in all_positions]
    return selected, pos_mode


def _dept_rank_map(all_deps: list[str]) -> dict[str, int]:
    return {d: i for i, d in enumerate(all_deps)}


def _pos_rank_map(all_positions: list[str]) -> dict[str, int]:
    return {p: i for i, p in enumerate(all_positions)}


def _parse_sort_mode(request, *, from_post: bool) -> str:
    """
    Совместимость с другими модулями.
    В интерфейсе графика сортировка больше не настраивается и всегда "dept".
    """
    _ = request, from_post
    return "dept"


def _sort_graph_rows(
    df,
    dep_rank: dict[str, int],
    pos_rank: dict[str, int],
    *,
    sort_mode: str = "dept",
):
    _ = sort_mode
    out = df.copy()
    out["_dep_rank"] = out["Отдел"].map(lambda d: dep_rank.get(str(d), 10_000))
    out["_pos_rank"] = out["Должность"].map(lambda p: pos_rank.get(str(p), 10_000))
    out["_ln_sort"] = out["_last_name"].astype(str).str.lower()
    out["_fn_sort"] = out["_first_name"].astype(str).str.lower()
    out["_name_sort"] = out["Сотрудник"].astype(str).str.lower()
    keys = ["_dep_rank", "_pos_rank", "_ln_sort", "_fn_sort", "_name_sort", "Код"]
    return out.sort_values(keys, kind="stable")


@biota_login_required
@nav_permission_required("graph")
@require_http_methods(["GET", "POST"])
def graph_view(request):
    now = datetime.now()
    default_y, default_m = now.year, now.month
    try:
        employees_df = _employees_for_user(request)
    except Exception as exc:
        return render(
            request,
            "shifts/error.html",
            {"title": "Ошибка БД", "message": str(exc)},
        )
    if employees_df.empty:
        return render(
            request,
            "shifts/error.html",
            {
                "title": "Нет сотрудников",
                "message": "По учётной записи нет доступа к списку сотрудников или база пуста.",
            },
        )

    ref_emp = str(employees_df.iloc[0]["emp_code"])
    year_options = biota_db.merged_year_options(biota_db.db_config(), ref_emp)
    if default_y not in year_options:
        default_y = year_options[0] if year_options else now.year

    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip().lower()
        y, m = _parse_year_month(request, default_year=default_y, default_month=default_m)

        if action == "upload":
            upl = request.FILES.get("schedule_file")
            if not upl:
                messages.error(request, "Выберите файл .xlsx")
                return redirect(f"/graph/?year={y}&month={m}")
            try:
                raw = upl.read()
                xl_imp = biota_schedule.read_schedule_sheet_from_bytes(raw)
                imported = biota_schedule.normalize_schedule_excel(xl_imp, employees_df, y, m)
                imported = biota_schedule.apply_prev_month_tail_from_previous_schedule(
                    imported, employees_df, y, m
                )
                biota_schedule.save_schedule_table(imported, y, m)
                messages.success(request, f"График загружен из файла ({upl.name}).")
            except ValueError as err:
                messages.error(request, str(err))
            except Exception as exc:
                messages.error(request, f"Не удалось прочитать файл: {exc}")
            return redirect(f"/graph/?year={y}&month={m}")

        # save
        full_schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
        schedule_df = _schedule_with_department(full_schedule_df, employees_df)
        all_deps = apply_department_order(
            sorted(schedule_df["Отдел"].unique().tolist()),
            load_department_order(),
        )
        all_positions = apply_position_order(
            sorted(schedule_df["Должность"].unique().tolist()),
            load_position_order(),
        )
        selected_deps, _dep_mode = _extract_selected_deps(request, all_deps, from_post=True)
        selected_positions, _pos_mode = _extract_selected_positions(
            request, all_positions, from_post=True
        )
        dep_rank = _dept_rank_map(all_deps)
        pos_rank = _pos_rank_map(all_positions)
        filtered = schedule_df[
            schedule_df["Отдел"].isin(selected_deps)
            & schedule_df["Должность"].isin(selected_positions)
        ].copy()
        filtered = _sort_graph_rows(filtered, dep_rank, pos_rank)

        day_columns = sort_schedule_day_columns(
            [c for c in full_schedule_df.columns if is_schedule_day_column(c)], y, m
        )
        for i, row in enumerate(filtered.itertuples(index=True)):
            base_idx = int(row.Index)
            for d in day_columns:
                if str(d) in PREV_MONTH_KEYS:
                    continue
                key = f"cell_{i}_{d}"
                if key not in request.POST:
                    continue
                raw = (request.POST.get(key) or "").strip().lower()
                if raw not in SCHEDULE_CODES:
                    raw = ""
                full_schedule_df.at[base_idx, d] = raw
        full_schedule_df = biota_schedule.apply_prev_month_tail_from_previous_schedule(
            full_schedule_df, employees_df, y, m
        )
        full_schedule_df = full_schedule_df.sort_values(["Порядок", "Код"]).reset_index(drop=True)
        saved_path = biota_schedule.save_schedule_table(full_schedule_df, y, m)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "saved": saved_path.name})
        messages.success(request, f"Сохранено: {saved_path.name}")
        return redirect(f"/graph/?year={y}&month={m}")

    # GET
    y, m = _parse_year_month(request, default_year=default_y, default_month=default_m)
    schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
    schedule_df = _schedule_with_department(schedule_df, employees_df)
    all_deps = apply_department_order(
        sorted(schedule_df["Отдел"].unique().tolist()),
        load_department_order(),
    )
    all_positions = apply_position_order(
        sorted(schedule_df["Должность"].unique().tolist()),
        load_position_order(),
    )
    selected_deps, dep_mode = _extract_selected_deps(request, all_deps, from_post=False)
    selected_positions, pos_mode = _extract_selected_positions(
        request, all_positions, from_post=False
    )
    dep_rank = _dept_rank_map(all_deps)
    pos_rank = _pos_rank_map(all_positions)
    schedule_df = schedule_df[
        schedule_df["Отдел"].isin(selected_deps)
        & schedule_df["Должность"].isin(selected_positions)
    ].copy()
    schedule_df = _sort_graph_rows(schedule_df, dep_rank, pos_rank).reset_index(drop=True)

    dep_color_map = {
        dep: DEPT_COLOR_CLASSES[i % len(DEPT_COLOR_CLASSES)] for i, dep in enumerate(all_deps)
    }
    day_columns = sort_schedule_day_columns(
        [c for c in schedule_df.columns if is_schedule_day_column(c)], y, m
    )
    today = date.today()
    day_headers: list[dict] = []
    non_working_days: list[str] = []
    day_shift_counts: list[dict] = []
    for d in day_columns:
        col_key = str(d)
        day_date = schedule_column_to_date(col_key, y, m)
        is_prev = col_key in PREV_MONTH_KEYS
        label = str(day_date.day) if day_date else col_key
        if is_prev and day_date:
            label = f"{day_date.day}.{day_date.month:02d}"
        is_non_working = bool(day_date) and is_ru_non_working_day(day_date)
        is_today = bool(day_date) and day_date == today
        day_headers.append(
            {
                "key": col_key,
                "label": label,
                "is_non_working": is_non_working,
                "is_prev_month": is_prev,
                "is_today": is_today,
            }
        )
        if is_non_working:
            non_working_days.append(col_key)
        d_cnt = n_cnt = 0
        if col_key in schedule_df.columns:
            for _, row in schedule_df.iterrows():
                v = str(row.get(col_key, "") or "").strip().lower()
                if v == "д":
                    d_cnt += 1
                elif v == "н":
                    n_cnt += 1
        day_shift_counts.append({"d": d_cnt, "n": n_cnt})

    for i, h in enumerate(day_headers):
        if i < len(day_shift_counts):
            h["d_count"] = day_shift_counts[i]["d"]
            h["n_count"] = day_shift_counts[i]["n"]
        else:
            h["d_count"] = h["n_count"] = 0

    col_meta = {str(h["key"]): h for h in day_headers}
    table_rows: list[dict] = []
    for i in range(len(schedule_df)):
        row = schedule_df.iloc[i]
        day_cells: list[dict] = []
        for d in day_columns:
            meta = col_meta.get(str(d), {})
            day_cells.append(
                {
                    "key": str(d),
                    "val": str(row.get(d, "") or ""),
                    "is_prev_month": bool(meta.get("is_prev_month")),
                    "is_today": bool(meta.get("is_today")),
                }
            )
        table_rows.append(
            {
                "i": i,
                "order": row.get("Порядок", ""),
                "code": row.get("Код", ""),
                "name": row.get("Сотрудник", ""),
                "department": row.get("Отдел", "Без отдела"),
                "department_class": dep_color_map.get(str(row.get("Отдел", "Без отдела")), "dept-c1"),
                "day_cells": day_cells,
            }
        )

    month_choices = [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)]
    return render(
        request,
        "shifts/graph.html",
        {
            "year": y,
            "month": m,
            "month_name": MONTH_NAMES_RU[m],
            "year_options": year_options,
            "month_choices": month_choices,
            "all_deps": all_deps,
            "sel_deps": selected_deps,
            "dep_mode_pick": dep_mode != "all",
            "all_positions": all_positions,
            "sel_positions": selected_positions,
            "pos_mode_pick": pos_mode != "all",
            "day_headers": day_headers,
            "non_working_days": non_working_days,
            "table_rows": table_rows,
        },
    )


@biota_login_required
@nav_permission_required("graph")
def graph_download(request):
    now = datetime.now()
    y, m = _parse_year_month(request, default_year=now.year, default_month=now.month)
    try:
        employees_df = _employees_for_user(request)
    except Exception as exc:
        return HttpResponse(str(exc), status=500)
    if employees_df.empty:
        return HttpResponse("Нет сотрудников", status=400)
    schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
    data = biota_export.build_schedule_excel(
        schedule_df, sheet_name="График", year=y, month=m
    )
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="grafik_{y}_{m:02d}.xlsx"'
    return resp
