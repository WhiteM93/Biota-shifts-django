"""Регламенты: интерактивная шкала времени + API сохранения (БД Django)."""
import json
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts import db as biota_db
from biota_shifts import export as biota_export
from biota_shifts import schedule as biota_schedule
from biota_shifts.auth import _filter_employees_for_user, _is_admin

from shifts.auth_utils import biota_login_required, biota_user
from shifts.department_order import apply_department_order, load_department_order
from shifts.graph_views import (
    DEPT_COLOR_CLASSES,
    _dept_rank_map,
    _extract_selected_deps,
    _schedule_with_department,
    _sort_graph_rows,
)

from .models import RegulationPlan

_DEFAULT_BREAKFAST = (time(9, 0), time(9, 30))
_DEFAULT_LUNCH = (time(12, 0), time(13, 0))


def _department_filter_context(request, plan_date: date) -> dict:
    """Фильтр отделов как на «Графике» (пустой список = ни один отдел)."""
    ctx = {
        "reg_filter_deps": [],
        "reg_sel_deps": [],
        "reg_dep_mode_pick": False,
        "reg_dep_qs": "",
        "post_dep_mode": request.GET.get("dep_mode") or "",
        "post_dep_list": list(request.GET.getlist("dep")),
    }
    try:
        employees_df = _employees_for_user(request)
        schedule_df = biota_schedule.load_schedule_table(
            employees_df, plan_date.year, plan_date.month
        )
        schedule_df = _schedule_with_department(schedule_df, employees_df)
        all_deps = apply_department_order(
            sorted(schedule_df["Отдел"].unique().tolist()),
            load_department_order(),
        )
        sel, depm = _extract_selected_deps(request, all_deps, from_post=False)
        ctx["reg_filter_deps"] = all_deps
        ctx["reg_sel_deps"] = sel
        ctx["reg_dep_mode_pick"] = depm != "all"
        q = []
        if request.GET.get("dep_mode"):
            q.append(("dep_mode", request.GET.get("dep_mode")))
        for d in request.GET.getlist("dep"):
            q.append(("dep", d))
        ctx["reg_dep_qs"] = ("&" + urlencode(q)) if q else ""
    except Exception:
        pass
    return ctx


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _prev_month_first(plan_day: date) -> date:
    first = _first_of_month(plan_day)
    if first.month == 1:
        return date(first.year - 1, 12, 1)
    return date(first.year, first.month - 1, 1)


def _parse_plan_date(raw: str | None) -> date:
    """Любая дата или YYYY-MM → первый день месяца (регламент ведётся по месяцу)."""
    if not raw:
        return _first_of_month(date.today())
    s = raw.strip()
    if len(s) == 7 and s[4] == "-":
        try:
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, 1)
        except ValueError:
            return _first_of_month(date.today())
    try:
        d = date.fromisoformat(s)
        return _first_of_month(d)
    except ValueError:
        return _first_of_month(date.today())


def _resolve_plan_date(request) -> date:
    month = (request.GET.get("month") or request.POST.get("month") or "").strip()
    if month and len(month) >= 7 and month[4] == "-":
        try:
            y, m = int(month[:4]), int(month[5:7])
            return date(y, m, 1)
        except ValueError:
            pass
    return _parse_plan_date(
        (request.GET.get("date") or request.POST.get("date") or "").strip() or None
    )


def _parse_shift(raw: str | None) -> str:
    s = (raw or "д").strip().lower()
    return "н" if s in ("н", "n") else "д"


def _shift_title(shift: str) -> str:
    return "Ночная смена" if shift == "н" else "Дневная смена"


def _employees_for_user(request):
    cfg = biota_db.db_config()
    employees_df = biota_db.load_employees(cfg)
    user = biota_user(request)
    if user and not _is_admin(user):
        employees_df = _filter_employees_for_user(employees_df, user)
    return employees_df


def _fill_from_catalog(plan_date: date, employees_df) -> tuple[int, int]:
    created = 0
    skipped = 0
    for _, row in employees_df.iterrows():
        code = str(row.get("emp_code") or "").strip()
        if not code:
            continue
        ln = str(row.get("last_name") or "").strip()
        fn = str(row.get("first_name") or "").strip()
        name = f"{ln} {fn}".strip() or code
        dept = str(row.get("department_name") or "").strip()
        pos = str(row.get("position_name") or "").strip()
        for shift_key in ("д", "н"):
            _, was_created = RegulationPlan.objects.get_or_create(
                plan_date=plan_date,
                employee_code=code,
                shift=shift_key,
                defaults={
                    "employee_name": name,
                    "department": dept,
                    "position": pos,
                    "breakfast_start": _DEFAULT_BREAKFAST[0],
                    "breakfast_end": _DEFAULT_BREAKFAST[1],
                    "lunch_start": _DEFAULT_LUNCH[0],
                    "lunch_end": _DEFAULT_LUNCH[1],
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1
    return created, skipped


def _seed_from_previous_month(plan_date: date, shift: str) -> int:
    """Если на первый день месяца нет строк — копируем все с прошлого месяца (та же смена)."""
    if RegulationPlan.objects.filter(plan_date=plan_date, shift=shift).exists():
        return 0
    prev = _prev_month_first(plan_date)
    prev_rows = list(RegulationPlan.objects.filter(plan_date=prev, shift=shift))
    if not prev_rows:
        return 0
    created = 0
    for p in prev_rows:
        RegulationPlan.objects.create(
            plan_date=plan_date,
            employee_code=p.employee_code,
            employee_name=p.employee_name,
            department=p.department,
            position=p.position,
            shift=p.shift,
            breakfast_start=p.breakfast_start,
            breakfast_end=p.breakfast_end,
            lunch_start=p.lunch_start,
            lunch_end=p.lunch_end,
            locked=p.locked,
            eight_hour_shift=p.eight_hour_shift,
        )
        created += 1
    return created


def _overlay_from_previous_month(plan_date: date, shift: str) -> int:
    """Для уже существующих строк подставить время и флаги с прошлого месяца (незаблокированные)."""
    prev = _prev_month_first(plan_date)
    prev_map = {
        str(o.employee_code).strip(): o
        for o in RegulationPlan.objects.filter(plan_date=prev, shift=shift)
    }
    if not prev_map:
        return 0
    updated = 0
    for o in RegulationPlan.objects.filter(plan_date=plan_date, shift=shift):
        if o.locked:
            continue
        src = prev_map.get(str(o.employee_code).strip())
        if not src:
            continue
        RegulationPlan.objects.filter(pk=o.pk).update(
            breakfast_start=src.breakfast_start,
            breakfast_end=src.breakfast_end,
            lunch_start=src.lunch_start,
            lunch_end=src.lunch_end,
            locked=src.locked,
            eight_hour_shift=src.eight_hour_shift,
        )
        updated += 1
    return updated


def _scale_slots_30min() -> list[dict]:
    """Подписи в шапке каждые 30 мин: 08:00 … 20:00 (25 отметок на полную шкалу до конца)."""
    slots: list[dict] = []
    for i in range(25):
        total_min = 8 * 60 + i * 30
        h, m = divmod(total_min, 60)
        lbl = f"{h:02d}:{m:02d}"
        slots.append({"label": lbl, "strong": m == 0})
    return slots


def _row_json(o: RegulationPlan) -> dict:
    return {
        "id": o.pk,
        "employee_code": o.employee_code,
        "employee_name": o.employee_name,
        "breakfast_start": o.breakfast_start.strftime("%H:%M"),
        "breakfast_end": o.breakfast_end.strftime("%H:%M"),
        "lunch_start": o.lunch_start.strftime("%H:%M"),
        "lunch_end": o.lunch_end.strftime("%H:%M"),
        "locked": o.locked,
        "eight_hour_shift": o.eight_hour_shift,
    }


def _dept_color_map_from_list(all_deps: list[str]) -> dict[str, str]:
    return {
        dep: DEPT_COLOR_CLASSES[i % len(DEPT_COLOR_CLASSES)]
        for i, dep in enumerate(all_deps)
    }


def _fallback_dep_color_map(plans: list[RegulationPlan]) -> dict[str, str]:
    names = sorted({((o.department or "").strip() or "Без отдела") for o in plans})
    all_deps = apply_department_order(names, load_department_order())
    return _dept_color_map_from_list(all_deps)


def _regulation_plans_and_colors(
    plan_date: date, request, shift: str = "д"
) -> tuple[list[RegulationPlan], dict[str, str]]:
    """Порядок строк как на «Графике» + цвета отделов; только выбранная смена (д/н)."""
    if shift not in ("д", "н"):
        shift = "д"
    base_all = list(RegulationPlan.objects.filter(plan_date=plan_date))
    base = [o for o in base_all if o.shift == shift]
    if not base:
        return [], {}
    try:
        employees_df = _employees_for_user(request)
    except Exception:
        base.sort(key=lambda o: (o.employee_name.lower(), o.employee_code))
        return base, _fallback_dep_color_map(base)
    if employees_df.empty:
        base.sort(key=lambda o: (o.employee_name.lower(), o.employee_code))
        return base, _fallback_dep_color_map(base)
    try:
        y, m = plan_date.year, plan_date.month
        schedule_df = biota_schedule.load_schedule_table(employees_df, y, m)
        schedule_df = _schedule_with_department(schedule_df, employees_df)
        all_deps = apply_department_order(
            sorted(schedule_df["Отдел"].unique().tolist()),
            load_department_order(),
        )
        dep_color_map = _dept_color_map_from_list(all_deps)
        selected_deps, dep_mode = _extract_selected_deps(request, all_deps, from_post=False)
        dep_rank = _dept_rank_map(all_deps)
        if not selected_deps:
            return [], dep_color_map
        schedule_df = schedule_df[schedule_df["Отдел"].isin(selected_deps)].copy()
        schedule_df = _sort_graph_rows(schedule_df, dep_rank).reset_index(drop=True)
        code_order = [str(c).strip() for c in schedule_df["Код"].tolist()]
    except Exception:
        base.sort(key=lambda o: (o.employee_name.lower(), o.employee_code))
        return base, _fallback_dep_color_map(base)

    by_key = {(str(o.employee_code).strip(), o.shift): o for o in base_all}
    ordered: list[RegulationPlan] = []
    seen: set[str] = set()
    for code in code_order:
        o = by_key.get((code, shift))
        if o is not None:
            ordered.append(o)
            seen.add(code)
    # В режиме «По списку» не подмешиваем остальных из SQLite — иначе снова видны «все».
    if dep_mode == "all":
        rest = [o for o in base if str(o.employee_code).strip() not in seen]
        rest.sort(key=lambda o: (o.employee_name.lower(), o.employee_code))
        ordered.extend(rest)
    return ordered, dep_color_map


def _parse_hm(s: str) -> time:
    s = (s or "").strip()
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError("time")
    return time(int(parts[0]), int(parts[1]))


def _regulation_timeline_export_rows(
    plans: list[RegulationPlan], dep_color_map: dict[str, str]
) -> list[dict]:
    out: list[dict] = []
    for o in plans:
        dept = (o.department or "").strip() or "Без отдела"
        out.append(
            {
                "employee_name": o.employee_name,
                "department_class": dep_color_map.get(dept, "dept-c1"),
                "breakfast_start": o.breakfast_start.strftime("%H:%M"),
                "breakfast_end": o.breakfast_end.strftime("%H:%M"),
                "lunch_start": o.lunch_start.strftime("%H:%M"),
                "lunch_end": o.lunch_end.strftime("%H:%M"),
            }
        )
    return out


@biota_login_required
@require_http_methods(["GET"])
def regulations_excel(request):
    plan_date = _resolve_plan_date(request)
    shift = _parse_shift(request.GET.get("shift"))
    plans, dep_color_map = _regulation_plans_and_colors(plan_date, request, shift=shift)
    if not plans:
        return HttpResponse("Нет данных на выбранную дату и смену", status=400, content_type="text/plain; charset=utf-8")
    rows = _regulation_timeline_export_rows(plans, dep_color_map)
    data = biota_export.build_regulations_timeline_excel(rows, plan_date, shift)
    y, m, d = plan_date.year, plan_date.month, plan_date.day
    tag = "n" if shift == "н" else "d"
    fn = f"reglament_{tag}_{y}_{m:02d}_{d:02d}.xlsx"
    # FileResponse(BytesIO) на части стеков (gunicorn/nginx) даёт 500 из‑за fileno() — отдаём из памяти.
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


@biota_login_required
@require_http_methods(["GET"])
def regulations_pdf(request):
    plan_date = _resolve_plan_date(request)
    shift = _parse_shift(request.GET.get("shift"))
    plans, dep_color_map = _regulation_plans_and_colors(plan_date, request, shift=shift)
    if not plans:
        return HttpResponse("Нет данных на выбранную дату и смену", status=400, content_type="text/plain; charset=utf-8")
    rows = _regulation_timeline_export_rows(plans, dep_color_map)
    try:
        data = biota_export.build_regulations_list_pdf(rows, plan_date, shift)
    except Exception as exc:
        return HttpResponse(f"PDF недоступен: {exc}", status=500, content_type="text/plain; charset=utf-8")
    y, m, d = plan_date.year, plan_date.month, plan_date.day
    tag = "n" if shift == "н" else "d"
    fn = f"reglament_{tag}_{y}_{m:02d}_{d:02d}.pdf"
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


@ensure_csrf_cookie
@biota_login_required
@require_http_methods(["GET", "POST"])
def regulation_page(request):
    plan_date = _resolve_plan_date(request)
    plan_date_s = plan_date.isoformat()
    plan_month_value = f"{plan_date.year:04d}-{plan_date.month:02d}"
    reg_shift = _parse_shift(request.GET.get("shift") or request.POST.get("shift"))

    if request.method == "POST" and request.POST.get("action") == "from_catalog":
        try:
            employees_df = _employees_for_user(request)
        except Exception as exc:
            return render(
                request,
                "shifts/error.html",
                {"title": "Ошибка БД", "message": str(exc)},
            )
        if employees_df.empty:
            messages.warning(
                request,
                "Справочник сотрудников пуст или нет прав — нечего подставлять.",
            )
        else:
            n_new, n_skip = _fill_from_catalog(plan_date, employees_df)
            n_ov = _overlay_from_previous_month(plan_date, _parse_shift(request.POST.get("shift")))
            msg = f"Добавлено новых строк: {n_new}. Уже были на этот месяц: {n_skip}."
            if n_ov:
                msg += f" Подтянуто с прошлого месяца (время и отметки): {n_ov}."
            messages.success(request, msg)
        post_shift = _parse_shift(request.POST.get("shift"))
        redir_q = [("month", plan_month_value), ("shift", post_shift)]
        dm = (request.POST.get("dep_mode") or "").strip()
        if dm:
            redir_q.append(("dep_mode", dm))
        for d in request.POST.getlist("dep"):
            if d:
                redir_q.append(("dep", d))
        return redirect(f"{reverse('regulations_page')}?{urlencode(redir_q)}")

    if request.method == "GET":
        seeded = _seed_from_previous_month(plan_date, reg_shift)
        if seeded:
            messages.info(
                request,
                f"Для этого месяца не было строк — скопировано из прошлого месяца: {seeded}.",
            )

    plans, dep_color_map = _regulation_plans_and_colors(
        plan_date, request, shift=reg_shift
    )
    rows: list[dict] = []
    for o in plans:
        row = _row_json(o)
        dept = (o.department or "").strip() or "Без отдела"
        row["department"] = dept
        row["department_class"] = dep_color_map.get(dept, "dept-c1")
        rows.append(row)

    biota_ok = True
    emp_count = None
    try:
        df = _employees_for_user(request)
        emp_count = len(df) if df is not None else 0
    except Exception:
        biota_ok = False

    dep_ctx = _department_filter_context(request, plan_date)

    return render(
        request,
        "regulations/timeline.html",
        {
            "plan_date": plan_date_s,
            "plan_month_value": plan_month_value,
            "plan_date_display": plan_date.strftime("%m.%Y"),
            "reg_shift": reg_shift,
            "reg_shift_title": _shift_title(reg_shift),
            "rows": rows,
            "biota_ok": biota_ok,
            "emp_count": emp_count,
            "scale_slots_30": _scale_slots_30min(),
            **dep_ctx,
        },
    )


@csrf_protect
@biota_login_required
@require_POST
def regulations_api_save(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("invalid json")
    d_raw = payload.get("date")
    items = payload.get("items")
    if not d_raw or not isinstance(items, list):
        return HttpResponseBadRequest("date, items required")
    try:
        plan_date = _first_of_month(date.fromisoformat(str(d_raw).strip()))
    except ValueError:
        return HttpResponseBadRequest("bad date")

    updated = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            pk = int(it.get("id"))
        except (TypeError, ValueError):
            continue
        row = RegulationPlan.objects.filter(pk=pk, plan_date=plan_date).first()
        if not row:
            continue
        try:
            ln_s = _parse_hm(str(it.get("lunch_start", "")))
            ln_e = _parse_hm(str(it.get("lunch_end", "")))
            if row.eight_hour_shift:
                bf_s, bf_e = ln_s, ln_e
            else:
                bf_s = _parse_hm(str(it.get("breakfast_start", "")))
                bf_e = _parse_hm(str(it.get("breakfast_end", "")))
        except ValueError:
            return HttpResponseBadRequest("bad time")
        n = RegulationPlan.objects.filter(pk=pk, plan_date=plan_date).update(
            breakfast_start=bf_s,
            breakfast_end=bf_e,
            lunch_start=ln_s,
            lunch_end=ln_e,
        )
        updated += n

    return JsonResponse({"ok": True, "updated": updated, "saved_at": datetime.now().isoformat(timespec="seconds")})


@csrf_protect
@biota_login_required
@require_POST
def regulations_api_meta(request):
    """Переключение замка и 8-часовой смены (без сохранения шкалы)."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("invalid json")
    d_raw = payload.get("date")
    updates = payload.get("updates")
    if not d_raw or not isinstance(updates, list):
        return HttpResponseBadRequest("date, updates required")
    try:
        plan_date = date.fromisoformat(str(d_raw).strip())
    except ValueError:
        return HttpResponseBadRequest("bad date")
    plan_date = _first_of_month(plan_date)

    changed = 0
    updated_rows: list[dict] = []
    for u in updates:
        if not isinstance(u, dict):
            continue
        try:
            pk = int(u.get("id"))
        except (TypeError, ValueError):
            continue
        fields: dict = {}
        if "locked" in u:
            fields["locked"] = bool(u.get("locked"))
        if "eight_hour_shift" in u:
            fields["eight_hour_shift"] = bool(u.get("eight_hour_shift"))
        if not fields:
            continue
        n = RegulationPlan.objects.filter(pk=pk, plan_date=plan_date).update(**fields)
        changed += n
        if n:
            obj = RegulationPlan.objects.filter(pk=pk, plan_date=plan_date).first()
            if obj:
                updated_rows.append(_row_json(obj))

    return JsonResponse({"ok": True, "changed": changed, "rows": updated_rows})
