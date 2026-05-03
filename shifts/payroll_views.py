"""Расчёт ЗП: карточка месяца по сотруднику (табель / СКУД, премии, штрафы)."""
import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from biota_shifts import db as biota_db
from biota_shifts.auth import _is_admin, employees_df_for_nav, nav_permissions_for_user
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts.emp_codes import normalize_emp_code

from .auth_utils import biota_login_required, biota_user, write_permission_required
from .models import EmployeePayrollProfile, EmployeePayrollSettlement
from .payroll_helpers import (
    compute_payroll_totals,
    distribute_month_tab_hours,
    parse_payroll_year_month,
    payroll_day_rows,
    resolve_payroll_employee,
    skud_hours_for_payroll_month,
)


def _decimal_field(val: str, default: Decimal = Decimal("0")) -> Decimal:
    raw = (val or "").strip().replace(",", ".")
    if not raw:
        return default
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError):
        return default
    if d < 0:
        return default
    return d.quantize(Decimal("0.01"))


@biota_login_required
@write_permission_required
@require_http_methods(["GET", "POST"])
def payroll_settlement_view(request, emp_code: str):
    username = biota_user(request) or ""
    if not _is_admin(username) and not nav_permissions_for_user(username).get("payroll", True):
        messages.warning(request, "У вас нет доступа к разделу «Расчёт ЗП».")
        return redirect(f"{reverse('inventory')}?panel=payroll")

    emp = resolve_payroll_employee(username, emp_code)
    if not emp:
        raise Http404()

    year, month = parse_payroll_year_month(request)
    ec = emp["emp_code"]

    try:
        cfg = biota_db.db_config()
        full = biota_db.load_employees(cfg)
    except Exception:
        full = pd.DataFrame()

    pay_df = employees_df_for_nav(username, "payroll", full)
    _, skud_by_day_all = skud_hours_for_payroll_month(pay_df, year, month) if pay_df is not None and not pay_df.empty else ({}, {})
    skud_day = skud_by_day_all.get(ec, {})

    schedule_df = pd.DataFrame()
    if pay_df is not None and not pay_df.empty:
        try:
            from biota_shifts import schedule as biota_schedule

            schedule_df = biota_schedule.load_schedule_table(pay_df, year, month)
        except Exception:
            schedule_df = pd.DataFrame()

    profile, _ = EmployeePayrollProfile.objects.get_or_create(emp_code=ec, defaults={"shift_hours": 8})
    settlement, _ = EmployeePayrollSettlement.objects.get_or_create(
        emp_code=ec,
        year=year,
        month=month,
        defaults={
            "tab_by_day": {},
            "bonus_percent": 0,
            "bonus_rub": 0,
            "penalty_quality_pct": 20,
            "penalty_result_pct": 20,
            "penalty_mode_pct": 10,
            "penalty_rub": 0,
        },
    )

    tab = settlement.tab_by_day if isinstance(settlement.tab_by_day, dict) else {}

    if request.method == "POST":
        month_total_raw = (request.POST.get("month_tab_total") or "").strip().replace(",", ".")
        if month_total_raw:
            try:
                month_total_val = float(month_total_raw)
            except ValueError:
                messages.error(request, "Некорректная сумма часов по табелю за месяц.")
                return redirect(f"{reverse('payroll_settlement', args=[ec])}?year={year}&month={month}")
            if month_total_val < 0:
                messages.error(request, "Сумма часов за месяц не может быть отрицательной.")
                return redirect(f"{reverse('payroll_settlement', args=[ec])}?year={year}&month={month}")
            settlement.tab_by_day = distribute_month_tab_hours(
                year, month, month_total_val, skud_day
            )
        else:
            new_tab: dict = {}
            _, last_d = calendar.monthrange(year, month)
            for d in range(1, last_d + 1):
                dk = date(year, month, d).isoformat()
                key = f"tab_{dk}"
                raw = (request.POST.get(key) or "").strip().replace(",", ".")
                if raw == "":
                    new_tab[dk] = None
                else:
                    try:
                        new_tab[dk] = round(float(raw), 2)
                    except ValueError:
                        new_tab[dk] = 0.0
            settlement.tab_by_day = new_tab
        settlement.bonus_percent = _decimal_field(request.POST.get("bonus_percent") or "0")
        settlement.bonus_rub = _decimal_field(request.POST.get("bonus_rub") or "0")
        settlement.penalty_quality_pct = _decimal_field(request.POST.get("penalty_quality_pct") or "0")
        settlement.penalty_result_pct = _decimal_field(request.POST.get("penalty_result_pct") or "0")
        settlement.penalty_mode_pct = _decimal_field(request.POST.get("penalty_mode_pct") or "0")
        settlement.penalty_rub = _decimal_field(request.POST.get("penalty_rub") or "0")
        settlement.updated_by = username
        settlement.save()
        messages.success(request, "Расчёт сохранён.")
        return redirect(f"{reverse('payroll_settlement', args=[ec])}?year={year}&month={month}")

    day_rows = payroll_day_rows(ec, year, month, pay_df, tab, skud_day, schedule_df)
    totals = compute_payroll_totals(profile, settlement, day_rows)
    tab_month_sum = sum(float(r.get("tab_h") or 0) for r in day_rows)
    preview_data = {
        "day_rate": str(
            profile.hourly_rate_day
            if profile.hourly_rate_day is not None
            else Decimal("0")
        ),
        "night_rate": str(
            profile.hourly_rate_night
            if profile.hourly_rate_night is not None
            else Decimal("0")
        ),
        "rows": [
            {
                "date_iso": r["date_iso"],
                "graph": str(r.get("graph") or ""),
                "skud_h": float(r.get("skud_h") or 0),
            }
            for r in day_rows
        ],
    }

    return render(
        request,
        "shifts/payroll_settlement.html",
        {
            "employee": emp,
            "profile": profile,
            "settlement": settlement,
            "year": year,
            "month": month,
            "month_name": MONTH_NAMES_RU[month],
            "day_rows": day_rows,
            "totals": totals,
            "tab_month_sum": tab_month_sum,
            "preview_data": preview_data,
        },
    )
