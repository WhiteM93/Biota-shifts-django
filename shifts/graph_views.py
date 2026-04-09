"""Страница «График» — как в Streamlit: таблица по дням, сохранение Excel, выгрузка/загрузка."""
from datetime import date, datetime

from django.contrib import messages
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from biota_shifts import db as biota_db
from biota_shifts.auth import _filter_employees_for_user, _is_admin
from biota_shifts.constants import MONTH_NAMES_RU, SCHEDULE_CODES
from biota_shifts import export as biota_export
from biota_shifts import schedule as biota_schedule

from .auth_utils import biota_login_required, biota_user
from .department_order import apply_department_order, load_department_order
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
    user = biota_user(request)
    if user and not _is_admin(user):
        employees_df = _filter_employees_for_user(employees_df, user)
    return employees_df


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
    source = request.POST if from_post else request.GET
    dep_mode = source.get("dep_mode", "all")
    if dep_mode == "all":
        return list(all_deps), dep_mode
    dep_list = source.getlist("dep")
    if not dep_list:
        return list(all_deps), dep_mode
    selected = [d for d in dep_list if d in all_deps]
    return (selected if selected else list(all_deps)), dep_mode


def _dept_rank_map(all_deps: list[str]) -> dict[str, int]:
    return {d: i for i, d in enumerate(all_deps)}


def _sort_graph_rows(df, dep_rank: dict[str, int]):
    out = df.copy()
    out["_dep_rank"] = out["Отдел"].map(lambda d: dep_rank.get(str(d), 10_000))
    out["_ln_sort"] = out["_last_name"].astype(str).str.lower()
    out["_fn_sort"] = out["_first_name"].astype(str).str.lower()
    out["_name_sort"] = out["Сотрудник"].astype(str).str.lower()
    return out.sort_values(
        ["_dep_rank", "_ln_sort", "_fn_sort", "_name_sort", "Код"],
        kind="stable",
    )


@biota_login_required
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
        selected_deps, _dep_mode = _extract_selected_deps(request, all_deps, from_post=True)
        dep_rank = _dept_rank_map(all_deps)
        filtered = schedule_df[schedule_df["Отдел"].isin(selected_deps)].copy()
        filtered = _sort_graph_rows(filtered, dep_rank)

        day_columns = [c for c in full_schedule_df.columns if str(c).isdigit()]
        day_columns = sorted(day_columns, key=lambda x: int(x))
        for i, row in enumerate(filtered.itertuples(index=True)):
            base_idx = int(row.Index)
            for d in day_columns:
                key = f"cell_{i}_{d}"
                if key not in request.POST:
                    continue
                raw = (request.POST.get(key) or "").strip().lower()
                if raw not in SCHEDULE_CODES:
                    raw = ""
                full_schedule_df.at[base_idx, d] = raw
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
    selected_deps, dep_mode = _extract_selected_deps(request, all_deps, from_post=False)
    dep_rank = _dept_rank_map(all_deps)
    schedule_df = schedule_df[schedule_df["Отдел"].isin(selected_deps)].copy()
    schedule_df = _sort_graph_rows(schedule_df, dep_rank).reset_index(drop=True)

    dep_color_map = {
        dep: DEPT_COLOR_CLASSES[i % len(DEPT_COLOR_CLASSES)] for i, dep in enumerate(all_deps)
    }
    day_columns = [c for c in schedule_df.columns if str(c).isdigit()]
    day_columns = sorted(day_columns, key=lambda x: int(x))
    day_headers: list[tuple[str, str, bool]] = []
    non_working_days: list[str] = []
    for d in day_columns:
        di = int(d)
        day_date = date(y, m, di)
        is_non_working = is_ru_non_working_day(day_date)
        day_headers.append((d, str(d), is_non_working))
        if is_non_working:
            non_working_days.append(str(d))

    table_rows: list[dict] = []
    for i in range(len(schedule_df)):
        row = schedule_df.iloc[i]
        day_cells = [(d, str(row.get(d, "") or "")) for d in day_columns]
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
            "day_headers": day_headers,
            "non_working_days": non_working_days,
            "table_rows": table_rows,
        },
    )


@biota_login_required
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
