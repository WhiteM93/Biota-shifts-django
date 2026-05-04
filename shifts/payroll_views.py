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
from django.db.models import Count, Prefetch, Sum

from .models import (
    DEFECT_PAYROLL_ADJUST_KIND_CHOICES,
    EmployeeDefectPayrollAdjustment,
    EmployeeDefectRecord,
    EmployeePayrollMonthStatus,
    EmployeePayrollProfile,
    EmployeePayrollSettlement,
)
from .payroll_helpers import (
    compute_payroll_totals,
    distribute_month_tab_hours,
    effective_side_payroll_fields,
    parse_payroll_year_month,
    payroll_day_rows,
    payroll_gross_tab_skud_through_day,
    payroll_year_options_for_employees,
    resolve_payroll_employee,
    skud_hours_for_payroll_month,
    stored_side_payroll_fields_from_effective,
    sum_defect_payroll_adjustments_for_defects,
)


def _advance_balance(total: Decimal, advance: Decimal) -> tuple[Decimal, Decimal]:
    """Остаток ко второй выплате; переплата, если аванс больше расчёта «к выплате»."""
    tot = total if total is not None else Decimal("0")
    if tot < 0:
        tot = Decimal("0")
    adv = advance if advance is not None else Decimal("0")
    if adv < 0:
        adv = Decimal("0")
    adv = adv.quantize(Decimal("0.01"))
    rem = (tot - adv).quantize(Decimal("0.01"))
    if rem >= 0:
        return rem, Decimal("0").quantize(Decimal("0.01"))
    return Decimal("0").quantize(Decimal("0.01")), (-rem).quantize(Decimal("0.01"))


def _decimal_signed(val: str) -> Decimal:
    raw = (val or "").strip().replace(",", ".")
    if raw == "":
        return Decimal("0")
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return d.quantize(Decimal("0.01"))


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
    label = (emp.get("label") or "").strip()

    try:
        cfg = biota_db.db_config()
        full = biota_db.load_employees(cfg)
    except Exception:
        full = pd.DataFrame()

    pay_df = employees_df_for_nav(username, "payroll", full)
    year_options = payroll_year_options_for_employees(
        pay_df if pay_df is not None and not pay_df.empty else pd.DataFrame()
    )
    if not year_options:
        ny = date.today().year
        year_options = [ny - 1, ny, ny + 1]
    if year not in year_options:
        year_options = sorted(set(year_options) | {year}, reverse=True)
    month_choices = [(m, MONTH_NAMES_RU[m]) for m in range(1, 13)]

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
            "advance_rub": 0,
        },
    )

    tab = settlement.tab_by_day if isinstance(settlement.tab_by_day, dict) else {}

    if request.method == "POST":
        mark_act = (request.POST.get("payroll_mark_action") or "").strip()
        if mark_act in {"toggle_advance", "toggle_payroll"}:
            try:
                my = int(request.POST.get("mark_year") or request.GET.get("year") or year)
            except (TypeError, ValueError):
                my = year
            try:
                mm = int(request.POST.get("mark_month") or request.GET.get("month") or month)
            except (TypeError, ValueError):
                mm = month
            my = max(2000, min(2100, my))
            mm = max(1, min(12, mm))
            st, _ = EmployeePayrollMonthStatus.objects.get_or_create(
                emp_code=ec,
                year=my,
                month=mm,
                defaults={"advance_closed": False, "payroll_closed": False},
            )
            if mark_act == "toggle_advance":
                st.advance_closed = not st.advance_closed
                msg = (
                    "Отмечено: аванс за месяц учтён."
                    if st.advance_closed
                    else "Отметка «аванс учтён» снята."
                )
            else:
                st.payroll_closed = not st.payroll_closed
                msg = (
                    "Отмечено: расчёт ЗП за месяц завершён."
                    if st.payroll_closed
                    else "Отметка «расчёт завершён» снята."
                )
            st.updated_by = username or ""
            st.save(
                update_fields=["advance_closed", "payroll_closed", "updated_by", "updated_at"]
            )
            messages.success(request, msg)
            return redirect(f"{reverse('payroll_settlement', args=[ec])}?year={my}&month={mm}")

        if (request.POST.get("defect_adjust_action") or "").strip() == "save":
            try:
                did = int(request.POST.get("defect_id") or "0")
            except (TypeError, ValueError):
                did = 0
            kind = (request.POST.get("adjust_kind") or "").strip()
            valid_kinds = {k for k, _ in DEFECT_PAYROLL_ADJUST_KIND_CHOICES}
            intent = (request.POST.get("defect_adjust_intent") or "save").strip()
            if intent == "delete":
                amt = Decimal("0")
            else:
                amt = _decimal_signed(request.POST.get("adjust_amount") or "0")
            try:
                my = int(request.POST.get("mark_year") or request.GET.get("year") or year)
                mm = int(request.POST.get("mark_month") or request.GET.get("month") or month)
            except (TypeError, ValueError):
                my, mm = year, month
            my = max(2000, min(2100, my))
            mm = max(1, min(12, mm))
            _, last_dd = calendar.monthrange(my, mm)
            rec = (
                EmployeeDefectRecord.objects.filter(
                    id=did,
                    employee_name=label,
                    defect_date__gte=date(my, mm, 1),
                    defect_date__lte=date(my, mm, last_dd),
                ).first()
                if label
                else None
            )
            if not rec or kind not in valid_kinds:
                messages.error(request, "Некорректные данные для корректировки по браку.")
                return redirect(f"{reverse('payroll_settlement', args=[ec])}?year={my}&month={mm}")
            if amt == 0:
                EmployeeDefectPayrollAdjustment.objects.filter(defect_record=rec, adjust_kind=kind).delete()
                messages.success(request, "Корректировка по браку удалена.")
            else:
                EmployeeDefectPayrollAdjustment.objects.update_or_create(
                    defect_record=rec,
                    adjust_kind=kind,
                    defaults={"amount": amt, "updated_by": username or ""},
                )
                messages.success(request, "Корректировка по браку сохранена.")
            return redirect(f"{reverse('payroll_settlement', args=[ec])}?year={my}&month={mm}")

        _, last_d_adj = calendar.monthrange(year, month)
        if label:
            defect_ids_for_save = list(
                EmployeeDefectRecord.objects.filter(
                    defect_date__gte=date(year, month, 1),
                    defect_date__lte=date(year, month, last_d_adj),
                    employee_name=label,
                ).values_list("id", flat=True)
            )
            defect_adj_for_save = sum_defect_payroll_adjustments_for_defects(defect_ids_for_save)
        else:
            defect_adj_for_save = {}

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
        eff_from_post = {
            "bonus_percent": _decimal_signed(request.POST.get("bonus_percent") or "0"),
            "bonus_rub": _decimal_signed(request.POST.get("bonus_rub") or "0"),
            "penalty_quality_pct": _decimal_signed(request.POST.get("penalty_quality_pct") or "0"),
            "penalty_result_pct": _decimal_signed(request.POST.get("penalty_result_pct") or "0"),
            "penalty_mode_pct": _decimal_signed(request.POST.get("penalty_mode_pct") or "0"),
            "penalty_rub": _decimal_signed(request.POST.get("penalty_rub") or "0"),
        }
        stored_side = stored_side_payroll_fields_from_effective(
            eff_from_post, defect_adj_for_save or None
        )
        settlement.bonus_percent = stored_side["bonus_percent"]
        settlement.bonus_rub = stored_side["bonus_rub"]
        settlement.penalty_quality_pct = stored_side["penalty_quality_pct"]
        settlement.penalty_result_pct = stored_side["penalty_result_pct"]
        settlement.penalty_mode_pct = stored_side["penalty_mode_pct"]
        settlement.penalty_rub = stored_side["penalty_rub"]
        settlement.advance_rub = _decimal_field(request.POST.get("advance_rub") or "0")
        settlement.updated_by = username
        settlement.save()
        messages.success(request, "Расчёт сохранён.")
        return redirect(f"{reverse('payroll_settlement', args=[ec])}?year={year}&month={month}")

    payroll_month_status = EmployeePayrollMonthStatus.objects.filter(
        emp_code=ec, year=year, month=month
    ).first()

    _, last_d = calendar.monthrange(year, month)
    day_rows = payroll_day_rows(ec, year, month, pay_df, tab, skud_day, schedule_df)
    if label:
        defect_qs = (
            EmployeeDefectRecord.objects.filter(
                defect_date__gte=date(year, month, 1),
                defect_date__lte=date(year, month, last_d),
                employee_name=label,
            )
            .prefetch_related(
                Prefetch(
                    "payroll_adjustments",
                    queryset=EmployeeDefectPayrollAdjustment.objects.order_by("adjust_kind"),
                )
            )
            .order_by("-defect_date", "-id")
        )
        defect_records = list(defect_qs)
        defect_ids = [r.id for r in defect_records]
        defect_adj_sums = sum_defect_payroll_adjustments_for_defects(defect_ids)
        defect_agg = EmployeeDefectRecord.objects.filter(
            defect_date__gte=date(year, month, 1),
            defect_date__lte=date(year, month, last_d),
            employee_name=label,
        ).aggregate(
            cnt=Count("id"),
            defect_qty=Sum("defect_quantity"),
            good_qty=Sum("good_quantity"),
            bad_qty=Sum("bad_quantity"),
            potential_qty=Sum("potential_defect_quantity"),
        )
    else:
        defect_records = []
        defect_ids = []
        defect_adj_sums = {}
        defect_agg = {
            "cnt": 0,
            "defect_qty": None,
            "good_qty": None,
            "bad_qty": None,
            "potential_qty": None,
        }
    totals = compute_payroll_totals(
        profile, settlement, day_rows, defect_adjust_sum_by_kind=defect_adj_sums or None
    )
    remainder_after_advance, advance_overpayment = _advance_balance(
        totals["total"], settlement.advance_rub
    )
    advance_last_day = min(20, last_d)
    advance_slice = payroll_gross_tab_skud_through_day(profile, day_rows, advance_last_day)
    tab_month_sum = sum(float(r.get("tab_h") or 0) for r in day_rows)
    defect_month = {
        "count": int(defect_agg.get("cnt") or 0),
        "defect_quantity": int(defect_agg.get("defect_qty") or 0),
        "good_quantity": int(defect_agg.get("good_qty") or 0),
        "bad_quantity": int(defect_agg.get("bad_qty") or 0),
        "potential_defect_quantity": int(defect_agg.get("potential_qty") or 0),
    }
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
        "advance_last_day": advance_last_day,
    }

    side_effective = effective_side_payroll_fields(settlement, defect_adj_sums or None)

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
            "year_choices": year_options,
            "month_choices": month_choices,
            "day_rows": day_rows,
            "totals": totals,
            "advance_slice": advance_slice,
            "advance_last_day": advance_last_day,
            "defect_month": defect_month,
            "defect_records": defect_records,
            "defect_adjust_kind_choices": DEFECT_PAYROLL_ADJUST_KIND_CHOICES,
            "tab_month_sum": tab_month_sum,
            "preview_data": preview_data,
            "remainder_after_advance": remainder_after_advance,
            "advance_overpayment": advance_overpayment,
            "payroll_month_status": payroll_month_status,
            "side_effective": side_effective,
        },
    )
