"""Страница «График» — как в Streamlit: таблица по дням, сохранение Excel, выгрузка/загрузка."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
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

from biota_shifts.schedule_google import GoogleScheduleError, google_schedule_configured

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .department_order import apply_department_order, load_department_order
from .graph_schedule_source import (
    SCHEDULE_SOURCE_GOOGLE,
    append_schedule_source,
    get_graph_schedule_source,
)
from .position_order import apply_position_order, load_position_order
from .ru_work_calendar import is_ru_non_working_day
from .section_action_log import (
    EVT_SERVER_GRAPH_REJECT,
    EVT_SERVER_GRAPH_UPLOAD,
    analyze_graph_save_post,
    log_graph_save,
    record_from_request,
    SECTION_GRAPH,
)


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


def _graph_redirect(request, year: int, month: int):
    src = get_graph_schedule_source(request)
    return redirect(append_schedule_source(f"/graph/?year={year}&month={month}", src))


def _load_schedule_for_graph(request, employees_df, year: int, month: int) -> pd.DataFrame:
    source = get_graph_schedule_source(request)
    try:
        return biota_schedule.load_schedule_table(
            employees_df, year, month, source=source
        )
    except GoogleScheduleError as exc:
        messages.error(request, str(exc))
        if source == SCHEDULE_SOURCE_GOOGLE:
            messages.warning(
                request,
                "Показан локальный график (Excel). Проверьте настройки Google или переключите источник.",
            )
            return biota_schedule.load_schedule_table(
                employees_df, year, month, source="local"
            )
        raise


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


def _norm_emp_code(val) -> str:
    """Единый строковый код для имён полей формы и поиска в DataFrame."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    s = str(val).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _schedule_day_col_keys(day_columns) -> list[str]:
    return [str(d) for d in day_columns]


def _parse_schedule_cell_post_key(key: str, day_col_keys: list[str]) -> tuple[str, str] | None:
    """
    Разбор POST-поля cell_<код>_<день>.
    Код сотрудника не содержит «_»; день — p1/p2/p3 или число (1, 01, …).
    """
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


def apply_schedule_cells_from_post(full_schedule_df, request, *, year: int, month: int):
    """
    Записывает ячейки из POST в full_schedule_df по коду сотрудника (Код),
    без привязки к индексу строки в отфильтрованной таблице.
    """
    day_columns = sort_schedule_day_columns(
        [c for c in full_schedule_df.columns if is_schedule_day_column(c)], year, month
    )
    col_keys = _schedule_day_col_keys(day_columns)
    code_series = full_schedule_df["Код"].map(_norm_emp_code)

    for key in request.POST:
        parsed = _parse_schedule_cell_post_key(key, col_keys)
        if not parsed:
            continue
        code, col_key = parsed
        code = _norm_emp_code(code)
        if col_key in PREV_MONTH_KEYS:
            continue
        if col_key not in full_schedule_df.columns:
            continue
        raw = (request.POST.get(key) or "").strip().lower()
        if raw not in SCHEDULE_CODES:
            raw = ""
        match = code_series == code
        if not match.any():
            continue
        full_idx = full_schedule_df.index[match][0]
        full_schedule_df.at[full_idx, col_key] = raw
    return full_schedule_df


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
@write_permission_required
@require_http_methods(["GET", "POST"])
def graph_view(request):
    if request.method == "GET":
        from .graph_device import (
            apply_desktop_graph_query_redirect,
            prefers_mobile_graph,
            redirect_to_mobile_graph,
        )

        if prefers_mobile_graph(request):
            return redirect_to_mobile_graph(request)

        desk_redirect = apply_desktop_graph_query_redirect(request)
        if desk_redirect is not None:
            return desk_redirect

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
        post_dep_mode = (request.POST.get("dep_mode") or "all").strip()
        post_pos_mode = (request.POST.get("pos_mode") or "all").strip()
        if action in ("save", "upload") and (post_dep_mode != "all" or post_pos_mode != "all"):
            record_from_request(
                request,
                SECTION_GRAPH,
                EVT_SERVER_GRAPH_REJECT,
                f"Отклонено {action}: dep_mode={post_dep_mode}, pos_mode={post_pos_mode}",
                {"action": action, "dep_mode": post_dep_mode, "pos_mode": post_pos_mode},
            )
            messages.error(
                request,
                "Редактирование и загрузка доступны только при фильтрах «Все» (отделы и должности).",
            )
            return _graph_redirect(request, y, m)

        schedule_source = get_graph_schedule_source(request)

        if action == "refresh_google":
            if not google_schedule_configured():
                messages.error(request, "Google не настроен.")
                return _graph_redirect(request, y, m)
            if schedule_source != SCHEDULE_SOURCE_GOOGLE:
                messages.error(request, "Обновление из Google доступно только в режиме Google.")
                return _graph_redirect(request, y, m)
            try:
                from biota_shifts.schedule_google_cache import (
                    format_cache_fetched_at,
                    prev_month,
                    refresh_google_schedule_cache,
                )

                refresh_google_schedule_cache(y, m, force=True)
                py, pm = prev_month(y, m)
                refresh_google_schedule_cache(py, pm, force=True)
                label = format_cache_fetched_at(y, m)
                messages.success(request, f"График обновлён из Google ({label}).")
            except GoogleScheduleError as exc:
                messages.error(request, str(exc))
            return _graph_redirect(request, y, m)

        if action == "save" and schedule_source == SCHEDULE_SOURCE_GOOGLE:
            messages.error(
                request,
                "График только для просмотра. Редактируйте в Google Таблице.",
            )
            return _graph_redirect(request, y, m)

        if action == "upload":
            if schedule_source == SCHEDULE_SOURCE_GOOGLE:
                messages.error(
                    request,
                    "Загрузка Excel недоступна: график ведётся в Google Таблице.",
                )
                return _graph_redirect(request, y, m)
            upl = request.FILES.get("schedule_file")
            if not upl:
                messages.error(request, "Выберите файл .xlsx")
                return _graph_redirect(request, y, m)
            try:
                raw = upl.read()
                xl_imp = biota_schedule.read_schedule_sheet_from_bytes(raw)
                imported = biota_schedule.normalize_schedule_excel(xl_imp, employees_df, y, m)
                imported = biota_schedule.apply_prev_month_tail_from_previous_schedule(
                    imported, employees_df, y, m
                )
                saved_path = biota_schedule.save_schedule_table(imported, y, m)
                record_from_request(
                    request,
                    SECTION_GRAPH,
                    EVT_SERVER_GRAPH_UPLOAD,
                    f"Загрузка Excel: {upl.name}",
                    {"file": upl.name, "saved": saved_path.name, "rows": len(imported)},
                )
                messages.success(request, f"График загружен из файла ({upl.name}).")
            except ValueError as err:
                messages.error(request, str(err))
            except Exception as exc:
                messages.error(request, f"Не удалось прочитать файл: {exc}")
            return _graph_redirect(request, y, m)

        # save — ячейки привязаны к коду сотрудника (cell_<Код>_<день>), не к индексу строки
        try:
            full_schedule_df = _load_schedule_for_graph(request, employees_df, y, m)
        except GoogleScheduleError:
            return _graph_redirect(request, y, m)
        full_schedule_df = apply_schedule_cells_from_post(
            full_schedule_df, request, year=y, month=m
        )
        full_schedule_df = biota_schedule.apply_prev_month_tail_from_previous_schedule(
            full_schedule_df, employees_df, y, m, source=schedule_source
        )
        full_schedule_df = full_schedule_df.sort_values(["Порядок", "Код"]).reset_index(drop=True)
        try:
            saved_path = biota_schedule.save_schedule_table(
                full_schedule_df, y, m, source=schedule_source
            )
        except GoogleScheduleError as exc:
            messages.error(request, str(exc))
            return _graph_redirect(request, y, m)
        stats = log_graph_save(
            request, full_schedule_df, year=y, month=m, saved_name=saved_path.name
        )
        if schedule_source == SCHEDULE_SOURCE_GOOGLE:
            from biota_shifts.schedule_google import google_schedule_read_only

            if google_schedule_read_only():
                save_msg = f"Сохранено локально ({saved_path.name}); Google — только чтение"
            else:
                save_msg = f"Сохранено в Google и локально ({saved_path.name})"
        else:
            save_msg = f"Сохранено: {saved_path.name}"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": True,
                    "saved": saved_path.name,
                    "applied_cells": stats.get("applied_cells", 0),
                    "post_cell_fields": stats.get("post_cell_fields", 0),
                    "reload": (request.POST.get("_save_reload") or "").strip() == "1",
                    "schedule_source": schedule_source,
                }
            )
        messages.success(request, save_msg)
        return _graph_redirect(request, y, m)

    # GET
    y, m = _parse_year_month(request, default_year=default_y, default_month=default_m)
    schedule_source = get_graph_schedule_source(request)
    schedule_df = _load_schedule_for_graph(request, employees_df, y, m)
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
            col_key = str(d)
            meta = col_meta.get(col_key, {})
            day_cells.append(
                {
                    "key": col_key,
                    "val": str(row.get(col_key, "") or ""),
                    "is_prev_month": bool(meta.get("is_prev_month")),
                    "is_today": bool(meta.get("is_today")),
                }
            )
        table_rows.append(
            {
                "i": i,
                "order": row.get("Порядок", ""),
                "code": _norm_emp_code(row.get("Код", "")),
                "name": row.get("Сотрудник", ""),
                "department": row.get("Отдел", "Без отдела"),
                "department_class": dep_color_map.get(str(row.get("Отдел", "Без отдела")), "dept-c1"),
                "day_cells": day_cells,
            }
        )

    month_choices = [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)]
    google_cache_updated_at = ""
    if schedule_source == SCHEDULE_SOURCE_GOOGLE and google_schedule_configured():
        from biota_shifts.schedule_google_cache import format_cache_fetched_at

        google_cache_updated_at = format_cache_fetched_at(y, m)
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
            "graph_edit_allowed": (
                dep_mode == "all"
                and pos_mode == "all"
                and schedule_source != SCHEDULE_SOURCE_GOOGLE
            ),
            "day_headers": day_headers,
            "non_working_days": non_working_days,
            "table_rows": table_rows,
            "schedule_source": schedule_source,
            "schedule_source_google": SCHEDULE_SOURCE_GOOGLE,
            "google_schedule_available": google_schedule_configured(),
            "google_cache_updated_at": google_cache_updated_at,
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
    source = get_graph_schedule_source(request)
    try:
        schedule_df = biota_schedule.load_schedule_table(
            employees_df, y, m, source=source
        )
    except GoogleScheduleError:
        schedule_df = biota_schedule.load_schedule_table(employees_df, y, m, source="local")
    data = biota_export.build_schedule_excel(
        schedule_df, sheet_name="График", year=y, month=m
    )
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="grafik_{y}_{m:02d}.xlsx"'
    return resp
