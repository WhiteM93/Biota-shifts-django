"""Страница «График» — как в Streamlit: таблица по дням, сохранение Excel, выгрузка/загрузка."""
from datetime import date, datetime

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from biota_shifts import db as biota_db
from biota_shifts.auth import _filter_employees_for_user, _is_admin
from biota_shifts.constants import MONTH_NAMES_RU, SCHEDULE_CODES
from biota_shifts import export as biota_export
from biota_shifts import schedule as biota_schedule

from .auth_utils import biota_login_required, biota_user


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
        schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
        day_columns = [c for c in schedule_df.columns if str(c).isdigit()]
        day_columns = sorted(day_columns, key=lambda x: int(x))
        for i in range(len(schedule_df)):
            for d in day_columns:
                key = f"cell_{i}_{d}"
                raw = (request.POST.get(key) or "").strip().lower()
                if raw not in SCHEDULE_CODES:
                    raw = ""
                schedule_df.at[i, d] = raw
        schedule_df = schedule_df.sort_values(["Порядок", "Код"]).reset_index(drop=True)
        saved_path = biota_schedule.save_schedule_table(schedule_df, y, m)
        messages.success(request, f"Сохранено: {saved_path.name}")
        return redirect(f"/graph/?year={y}&month={m}")

    # GET
    y, m = _parse_year_month(request, default_year=default_y, default_month=default_m)
    schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
    day_columns = [c for c in schedule_df.columns if str(c).isdigit()]
    day_columns = sorted(day_columns, key=lambda x: int(x))
    weekend_abbr = {5: "сб", 6: "вс"}
    day_headers: list[tuple[str, str]] = []
    for d in day_columns:
        di = int(d)
        wd = date(y, m, di).weekday()
        lab = f"{d} ({weekend_abbr[wd]})" if wd in weekend_abbr else str(d)
        day_headers.append((d, lab))

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
            "day_headers": day_headers,
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
