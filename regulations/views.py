"""Регламенты: интерактивная шкала времени + API сохранения (SQLite)."""
import json
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts import db as biota_db
from biota_shifts.auth import _filter_employees_for_user, _is_admin

from shifts.auth_utils import biota_login_required, biota_user

from .models import RegulationPlan

_DEFAULT_BREAKFAST = (time(9, 0), time(9, 30))
_DEFAULT_LUNCH = (time(12, 0), time(13, 0))


def _parse_plan_date(raw: str | None) -> date:
    if not raw:
        return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return date.today() + timedelta(days=1)


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
        _, was_created = RegulationPlan.objects.get_or_create(
            plan_date=plan_date,
            employee_code=code,
            defaults={
                "employee_name": name,
                "department": dept,
                "position": pos,
                "shift": "д",
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


def _scale_slots_30min() -> list[dict]:
    """Подписи в шапке: каждые 30 мин (08:00 … 19:30), 24 слота на 12 ч."""
    slots: list[dict] = []
    for i in range(24):
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
    }


def _parse_hm(s: str) -> time:
    s = (s or "").strip()
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError("time")
    return time(int(parts[0]), int(parts[1]))


@biota_login_required
@require_http_methods(["GET", "POST"])
def regulation_page(request):
    plan_date = _parse_plan_date(
        (request.GET.get("date") or request.POST.get("plan_date") or "").strip() or None
    )
    plan_date_s = plan_date.isoformat()

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
            messages.success(
                request,
                f"Добавлено новых строк: {n_new}. Уже были на эту дату: {n_skip}.",
            )
        return redirect(f"{reverse('regulations_page')}?date={plan_date_s}")

    qs = RegulationPlan.objects.filter(plan_date=plan_date).order_by("employee_name")
    rows = [_row_json(o) for o in qs]

    biota_ok = True
    emp_count = None
    try:
        df = _employees_for_user(request)
        emp_count = len(df) if df is not None else 0
    except Exception:
        biota_ok = False

    return render(
        request,
        "regulations/timeline.html",
        {
            "plan_date": plan_date_s,
            "plan_date_display": plan_date.strftime("%d.%m.%Y"),
            "rows": rows,
            "rows_json": json.dumps(rows, ensure_ascii=False),
            "biota_ok": biota_ok,
            "emp_count": emp_count,
            "scale_slots_30": _scale_slots_30min(),
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
        plan_date = date.fromisoformat(str(d_raw).strip())
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
        try:
            bf_s = _parse_hm(str(it.get("breakfast_start", "")))
            bf_e = _parse_hm(str(it.get("breakfast_end", "")))
            ln_s = _parse_hm(str(it.get("lunch_start", "")))
            ln_e = _parse_hm(str(it.get("lunch_end", "")))
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
