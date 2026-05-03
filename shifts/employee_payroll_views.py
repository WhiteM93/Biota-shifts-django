"""Карточка сотрудника: ставки ₽/ч (день/ночь), длительность смены 8/10/12 ч."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from biota_shifts import db as biota_db
from biota_shifts.auth import _is_admin, employees_df_for_nav, nav_permissions_for_user
from biota_shifts.schedule import employee_label_row

from .auth_utils import biota_login_required, biota_user, write_permission_required
from .models import EmployeePayrollProfile

SHIFT_HOURS_ALLOWED = frozenset({8, 10, 12})


def _decimal_or_none(val: str) -> Decimal | None:
    raw = (val or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if d < 0:
        return None
    return d


def _resolve_employee_row(request, emp_code: str) -> dict | None:
    username = biota_user(request) or ""
    try:
        cfg = biota_db.db_config()
        full = biota_db.load_employees(cfg)
    except Exception:
        return None
    df = employees_df_for_nav(username, "employees", full)
    if df is None or getattr(df, "empty", True):
        return None
    want = (emp_code or "").strip()
    for _, row in df.iterrows():
        if str(row.get("emp_code") or "").strip() != want:
            continue
        return {
            "emp_code": want,
            "label": (employee_label_row(row) or "").strip() or want,
            "last_name": str(row.get("last_name") or "").strip(),
            "first_name": str(row.get("first_name") or "").strip(),
            "department_name": str(row.get("department_name") or "").strip(),
            "position_name": str(row.get("position_name") or "").strip(),
            "area_name": str(row.get("area_name") or "").strip(),
        }
    return None


@biota_login_required
@write_permission_required
@require_http_methods(["GET", "POST"])
def employee_payroll_detail_view(request, emp_code: str):
    username = biota_user(request) or ""
    if not _is_admin(username) and not nav_permissions_for_user(username).get("employees", True):
        messages.warning(request, "У вас нет доступа к разделу «Сотрудники».")
        return redirect(f"{reverse('inventory')}?panel=employees")

    emp = _resolve_employee_row(request, emp_code)
    if not emp:
        raise Http404()

    profile, _ = EmployeePayrollProfile.objects.get_or_create(
        emp_code=emp["emp_code"],
        defaults={"shift_hours": 8},
    )

    if request.method == "POST":
        try:
            sh = int((request.POST.get("shift_hours") or "8").strip())
        except ValueError:
            sh = -1
        if sh not in SHIFT_HOURS_ALLOWED:
            messages.error(request, "Выберите длительность смены: 8, 10 или 12 часов.")
            return redirect(reverse("employee_payroll_detail", args=[emp["emp_code"]]))

        day_raw = request.POST.get("hourly_rate_day")
        night_raw = request.POST.get("hourly_rate_night")
        day = _decimal_or_none(day_raw) if (day_raw or "").strip() else None
        night = _decimal_or_none(night_raw) if (night_raw or "").strip() else None
        if (day_raw or "").strip() and day is None:
            messages.error(request, "Некорректная дневная ставка (₽/ч).")
            return redirect(reverse("employee_payroll_detail", args=[emp["emp_code"]]))
        if (night_raw or "").strip() and night is None:
            messages.error(request, "Некорректная ночная ставка (₽/ч).")
            return redirect(reverse("employee_payroll_detail", args=[emp["emp_code"]]))

        profile.hourly_rate_day = day
        profile.hourly_rate_night = night
        profile.shift_hours = sh
        profile.updated_by = username
        profile.save()
        messages.success(request, "Данные сохранены.")
        return redirect(reverse("employee_payroll_detail", args=[emp["emp_code"]]))

    return render(
        request,
        "shifts/employee_payroll.html",
        {
            "employee": emp,
            "profile": profile,
            "shift_hours_allowed": sorted(SHIFT_HOURS_ALLOWED),
        },
    )
