"""Расчёт ЗП: СКУД-часы из отметок, график д/н, табель по дням."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from biota_shifts import db as biota_db
from biota_shifts import logic as biota_logic
from biota_shifts.auth import employees_df_for_nav
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts.emp_codes import normalize_emp_code
from biota_shifts import schedule as biota_schedule
from biota_shifts.schedule import employee_label_row, sanitize_schedule_cell


def parse_payroll_year_month(request) -> tuple[int, int]:
    """Год и месяц из GET для панели «Расчёт ЗП»."""
    now = datetime.now()
    return _parse_year_month_get(request, now.year, now.month)


def _parse_year_month_get(request, default_y: int, default_m: int) -> tuple[int, int]:
    try:
        y = int(request.GET.get("year") or default_y)
    except (TypeError, ValueError):
        y = default_y
    try:
        m = int(request.GET.get("month") or default_m)
    except (TypeError, ValueError):
        m = default_m
    return max(2000, min(2100, y)), max(1, min(12, m))


def skud_hours_for_payroll_month(
    employees_df: pd.DataFrame, year: int, month: int
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """Сумма часов СКУД за месяц по сотрудникам + по дням (iso-дата → часы) для каждого кода."""
    totals: dict[str, float] = {}
    by_day: dict[str, dict[str, float]] = {}
    if employees_df is None or getattr(employees_df, "empty", True):
        return totals, by_day
    cfg = biota_db.db_config()
    start_date, end_date = biota_schedule.month_bounds(date(year, month, 1))
    try:
        schedule_full = biota_schedule.load_schedule_table(employees_df, year, month)
    except Exception:
        return totals, by_day
    if schedule_full.empty or "Код" not in schedule_full.columns:
        return totals, by_day
    allow = {normalize_emp_code(str(x)) for x in employees_df["emp_code"].tolist() if normalize_emp_code(str(x))}
    sch = schedule_full[schedule_full["Код"].astype(str).map(normalize_emp_code).isin(allow)].copy()
    if sch.empty:
        return totals, by_day
    codes = sch["Код"].astype(str).map(normalize_emp_code).tolist()
    try:
        punches = biota_db.load_iclock_punches_batch(
            cfg, codes, start_date - timedelta(days=1), end_date + timedelta(days=1)
        )
    except Exception:
        return totals, by_day
    hl = biota_logic.build_hours_long_from_punches(sch, punches, year, month)
    if hl is None or hl.empty:
        return {c: 0.0 for c in allow}, by_day
    hl = hl.copy()
    hl["emp_code"] = hl["emp_code"].map(normalize_emp_code)
    for _, r in hl.iterrows():
        ec = str(r.get("emp_code") or "").strip()
        if not ec:
            continue
        h = float(r.get("worked_hours") or 0)
        totals[ec] = totals.get(ec, 0.0) + h
        sd = r.get("shift_date")
        if hasattr(sd, "isoformat"):
            dk = sd.isoformat()
        else:
            dk = str(sd)[:10]
        by_day.setdefault(ec, {})[dk] = by_day.get(ec, {}).get(dk, 0.0) + h
    for c in allow:
        totals.setdefault(c, 0.0)
    return totals, by_day


def payroll_day_rows(
    emp_code: str,
    year: int,
    month: int,
    employees_df: pd.DataFrame,
    tab_by_day: dict[str, Any],
    skud_by_day: dict[str, float],
    schedule_df: pd.DataFrame,
) -> list[dict]:
    """Строки по дням месяца: дата, график, часы СКУД, часы табеля (редактируемые)."""
    ec = normalize_emp_code(emp_code)
    row = biota_logic._schedule_row_for_emp(schedule_df, ec) if not schedule_df.empty else None
    _, last_d = calendar.monthrange(year, month)
    wdays = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    out: list[dict] = []
    for d in range(1, last_d + 1):
        dd = date(year, month, d)
        dk = dd.isoformat()
        code = ""
        if row is not None and str(d) in row.index:
            code = sanitize_schedule_cell(row.get(str(d)))
        sk = float(skud_by_day.get(dk, 0.0))
        raw_tab = tab_by_day.get(dk)
        if raw_tab is None:
            tab = sk
        else:
            try:
                tab = float(raw_tab)
            except (TypeError, ValueError):
                tab = sk
        out.append(
            {
                "date": dd,
                "date_iso": dk,
                "weekday": wdays[dd.weekday()],
                "graph": code or "—",
                "skud_h": round(sk, 2),
                "tab_h": tab,
            }
        )
    return out


def distribute_month_tab_hours(
    year: int, month: int, month_total: float, skud_by_day: dict[str, float]
) -> dict[str, float]:
    """Распределить суммарные часы табеля по дням месяца.

    Если сумма часов СКУД за месяц > 0 — пропорционально СКУД по дням.
    Иначе — поровну по числу календарных дней. Остаток от округления на последний день.
    """
    _, last_d = calendar.monthrange(year, month)
    days = [date(year, month, d).isoformat() for d in range(1, last_d + 1)]
    sk_list = [float(skud_by_day.get(dk, 0.0)) for dk in days]
    sk_sum = sum(sk_list)
    if month_total <= 0:
        return {dk: 0.0 for dk in days}
    if sk_sum > 0:
        raw = [month_total * (sk_list[i] / sk_sum) for i in range(len(days))]
    else:
        share = month_total / len(days)
        raw = [share for _ in days]
    out_vals: list[float] = []
    acc = 0.0
    for r in raw[:-1]:
        v = round(r, 2)
        out_vals.append(max(0.0, v))
        acc += v
    last_v = max(0.0, round(month_total - acc, 2))
    out_vals.append(last_v)
    return {dk: out_vals[i] for i, dk in enumerate(days)}


# Начисление по табелю (base): 50% гарантированно + три доли от начисления — до 20%, 20%, 10%.
# Поля penalty_* — выплачиваемый % от начисления по своей линии (0…макс). 20/20/10 = полная сумма;
# например 18 по «результат» = 18% от base с этой строки (минус 2 п.п. от максимума → −2% от base).
TAB_GUARANTEED_PCT = Decimal("50")
TAB_SLICE_QUALITY_PCT = Decimal("20")
TAB_SLICE_RESULT_PCT = Decimal("20")
TAB_SLICE_MODE_PCT = Decimal("10")


def payroll_gross_tab_skud_through_day(
    profile,
    day_rows: list[dict],
    through_day: int,
) -> dict[str, Decimal]:
    """За календарные дни 1…through_day: часы табеля, СКУД и сумма h×ставка (д/н), без премий и штрафов."""
    D = Decimal
    day_rate = profile.hourly_rate_day if profile.hourly_rate_day is not None else D("0")
    night_rate = profile.hourly_rate_night if profile.hourly_rate_night is not None else D("0")
    tab_sum = D("0")
    skud_sum = D("0")
    gross = D("0")
    for r in day_rows:
        dd = r.get("date")
        if not isinstance(dd, date):
            try:
                dd = date.fromisoformat(str(r.get("date_iso") or "")[:10])
            except ValueError:
                continue
        if dd.day > through_day:
            continue
        h = D(str(r.get("tab_h") or 0))
        sk = D(str(r.get("skud_h") or 0))
        tab_sum += h
        skud_sum += sk
        g = str(r.get("graph") or "").strip().lower()
        rate = night_rate if g == "н" else day_rate
        gross += h * rate
    return {
        "total_tab_hours": tab_sum.quantize(D("0.01")),
        "total_skud_hours": skud_sum.quantize(D("0.01")),
        "gross_accrual_rub": gross.quantize(D("0.01")),
    }


def sum_defect_payroll_adjustments_for_defects(defect_ids: list[int]) -> dict[str, Decimal]:
    """Суммы добавок по всем записям брака (по полю adjust_kind) для включения в расчёт ЗП."""
    from django.db.models import Sum

    from .models import EmployeeDefectPayrollAdjustment

    D = Decimal
    if not defect_ids:
        return {}
    out: dict[str, Decimal] = {}
    for row in (
        EmployeeDefectPayrollAdjustment.objects.filter(defect_record_id__in=defect_ids)
        .values("adjust_kind")
        .annotate(s=Sum("amount"))
    ):
        k = row.get("adjust_kind") or ""
        s = row.get("s")
        if k and s is not None:
            out[k] = D(str(s)).quantize(D("0.01"))
    return out


def _adj_d(d: dict[str, Decimal] | None, key: str, D) -> Decimal:
    if not d:
        return D("0")
    v = d.get(key)
    if v is None:
        return D("0")
    return D(str(v)).quantize(D("0.01"))


def effective_side_payroll_fields(
    settlement, defect_adjust_sum_by_kind: dict[str, Decimal] | None
) -> dict[str, Decimal]:
    """Итоговые коэффициенты для полей боковой карточки (сумма сохранённого расчёта и корректировок по браку).

    Должны совпадать с тем, как compute_payroll_totals применяет settlement + defect_adjust.
    """
    D = Decimal
    dadj = defect_adjust_sum_by_kind
    q = min(
        max(D(str(settlement.penalty_quality_pct or 0)) + _adj_d(dadj, "penalty_quality_pct", D), D("0")),
        TAB_SLICE_QUALITY_PCT,
    )
    r = min(
        max(D(str(settlement.penalty_result_pct or 0)) + _adj_d(dadj, "penalty_result_pct", D), D("0")),
        TAB_SLICE_RESULT_PCT,
    )
    m = min(
        max(D(str(settlement.penalty_mode_pct or 0)) + _adj_d(dadj, "penalty_mode_pct", D), D("0")),
        TAB_SLICE_MODE_PCT,
    )
    b_pct = max(D("0"), D(str(settlement.bonus_percent or 0)) + _adj_d(dadj, "bonus_percent", D))
    b_rub = D(str(settlement.bonus_rub or 0)).quantize(D("0.01")) + _adj_d(dadj, "bonus_rub", D)
    if b_rub < 0:
        b_rub = D("0")
    pen_rub = D(str(settlement.penalty_rub or 0)).quantize(D("0.01")) + _adj_d(dadj, "penalty_rub", D)
    if pen_rub < 0:
        pen_rub = D("0")
    return {
        "bonus_percent": b_pct.quantize(D("0.01")),
        "bonus_rub": b_rub.quantize(D("0.01")),
        "penalty_quality_pct": q.quantize(D("0.01")),
        "penalty_result_pct": r.quantize(D("0.01")),
        "penalty_mode_pct": m.quantize(D("0.01")),
        "penalty_rub": pen_rub.quantize(D("0.01")),
    }


def stored_side_payroll_fields_from_effective(
    eff: dict[str, Decimal],
    defect_adjust_sum_by_kind: dict[str, Decimal] | None,
) -> dict[str, Decimal]:
    """Обратное к effective_side_payroll_fields: из значений в форме (итог) получить поля settlement для сохранения."""
    D = Decimal
    dadj = defect_adjust_sum_by_kind

    def effv(key: str) -> Decimal:
        v = eff.get(key)
        if v is None:
            return D("0")
        return D(str(v)).quantize(D("0.01"))

    q_eff = effv("penalty_quality_pct")
    r_eff = effv("penalty_result_pct")
    m_eff = effv("penalty_mode_pct")
    b_pct_eff = effv("bonus_percent")
    b_rub_eff = effv("bonus_rub")
    pen_rub_eff = effv("penalty_rub")

    b_pct_st = b_pct_eff - _adj_d(dadj, "bonus_percent", D)
    if b_pct_st < 0:
        b_pct_st = D("0")
    b_rub_st = b_rub_eff - _adj_d(dadj, "bonus_rub", D)
    if b_rub_st < 0:
        b_rub_st = D("0")
    pen_rub_st = pen_rub_eff - _adj_d(dadj, "penalty_rub", D)
    if pen_rub_st < 0:
        pen_rub_st = D("0")

    return {
        "bonus_percent": b_pct_st.quantize(D("0.01")),
        "bonus_rub": b_rub_st.quantize(D("0.01")),
        "penalty_quality_pct": (q_eff - _adj_d(dadj, "penalty_quality_pct", D)).quantize(D("0.01")),
        "penalty_result_pct": (r_eff - _adj_d(dadj, "penalty_result_pct", D)).quantize(D("0.01")),
        "penalty_mode_pct": (m_eff - _adj_d(dadj, "penalty_mode_pct", D)).quantize(D("0.01")),
        "penalty_rub": pen_rub_st.quantize(D("0.01")),
    }


def compute_payroll_totals(
    profile,
    settlement,
    day_rows: list[dict],
    *,
    through_day: int | None = None,
    defect_adjust_sum_by_kind: dict[str, Decimal] | None = None,
) -> dict[str, Decimal]:
    """Начисление по табелю (ставка д/н): 50% + доли % от base, премия % и +руб.

    through_day: если задано (например 20), учитываются только дни месяца с 1 по это число
    (для оценки аванса / табеля до 20-го).
    defect_adjust_sum_by_kind: добавки из учёта брака (сумма по всем записям месяца) к полям премий/штрафов.
    """
    D = Decimal
    dadj = defect_adjust_sum_by_kind
    day_rate = profile.hourly_rate_day if profile.hourly_rate_day is not None else D("0")
    night_rate = profile.hourly_rate_night if profile.hourly_rate_night is not None else D("0")
    base = D("0")
    skud_sum = D("0")
    tab_sum = D("0")
    for r in day_rows:
        if through_day is not None:
            dd = r.get("date")
            if not isinstance(dd, date):
                try:
                    dd = date.fromisoformat(str(r.get("date_iso") or "")[:10])
                except ValueError:
                    continue
            if dd.day > through_day:
                continue
        h = D(str(r.get("tab_h") or 0))
        sk = D(str(r.get("skud_h") or 0))
        tab_sum += h
        skud_sum += sk
        g = str(r.get("graph") or "").strip().lower()
        rate = night_rate if g == "н" else day_rate
        base += h * rate

    side = effective_side_payroll_fields(settlement, dadj)
    q = side["penalty_quality_pct"]
    r = side["penalty_result_pct"]
    m = side["penalty_mode_pct"]
    b_pct = side["bonus_percent"]

    guaranteed = (base * TAB_GUARANTEED_PCT / D("100")).quantize(D("0.01"))
    quality_pay = (base * q / D("100")).quantize(D("0.01"))
    result_pay = (base * r / D("100")).quantize(D("0.01"))
    mode_pay = (base * m / D("100")).quantize(D("0.01"))
    tab_payout = (guaranteed + quality_pay + result_pay + mode_pay).quantize(D("0.01"))

    penalties = (base - tab_payout).quantize(D("0.01"))
    penalty_pp_sum = (
        (TAB_SLICE_QUALITY_PCT - q) + (TAB_SLICE_RESULT_PCT - r) + (TAB_SLICE_MODE_PCT - m)
    ).quantize(D("0.01"))

    bonus_pct_amt = (base * b_pct / D("100")).quantize(D("0.01"))
    b_rub = side["bonus_rub"]
    pen_rub = side["penalty_rub"]
    if through_day is not None:
        # Фикс. премия и штраф ₽ задаются на месяц целиком — в срезе 1–N не смешиваем с авансом.
        b_rub = D("0")
        pen_rub = D("0")
    total_raw = tab_payout + bonus_pct_amt + b_rub - pen_rub
    total = total_raw.quantize(D("0.01"))
    if total < 0:
        total = D("0")
    return {
        "base_tab": base.quantize(D("0.01")),
        "tab_payout": tab_payout,
        "total_skud_hours": skud_sum.quantize(D("0.01")),
        "total_tab_hours": tab_sum.quantize(D("0.01")),
        "penalties": penalties,
        "bonus_pct_amount": bonus_pct_amt,
        "bonus_rub": b_rub,
        "penalty_rub": pen_rub,
        "total": total,
        "penalty_pp_sum": penalty_pp_sum,
        "penalty_pct_sum": penalty_pp_sum,
    }


def payroll_year_options_for_employees(employees_df: pd.DataFrame) -> list[int]:
    """Годы для селектора «Расчёт ЗП» без N запросов в Biota на каждого сотрудника.

    Раньше для до 50 сотрудников вызывался merged_year_options → десятки тяжёлых обращений к БД
    и страница грузилась очень долго. Для выбора месяца ЗП достаточно годов из файлов графика
    плюс небольшое окно вокруг текущего года.
    """
    _ = employees_df  # сигнатура сохранена для вызывающего кода; список годов больше не зависит от Biota по каждому коду
    now_y = datetime.now().year
    ys = set(biota_schedule.available_schedule_years())
    ys.update({now_y - 1, now_y, now_y + 1})
    if not ys:
        return [now_y - 1, now_y, now_y + 1]
    return sorted(ys, reverse=True)


def build_payroll_employee_rows(
    username: str,
    year: int,
    month: int,
) -> tuple[pd.DataFrame, dict[str, float], list[int]]:
    """DataFrame сотрудников для payroll, суммы СКУД за месяц, годы для селектора."""
    try:
        cfg = biota_db.db_config()
        full = biota_db.load_employees(cfg)
    except Exception:
        return pd.DataFrame(), {}, [datetime.now().year]
    df = employees_df_for_nav(username, "payroll", full)
    if df is None or getattr(df, "empty", True):
        return df, {}, payroll_year_options_for_employees(df)
    totals, _ = skud_hours_for_payroll_month(df, year, month)
    years = payroll_year_options_for_employees(df)
    return df, totals, years


def resolve_payroll_employee(username: str, emp_code: str) -> dict | None:
    try:
        cfg = biota_db.db_config()
        full = biota_db.load_employees(cfg)
    except Exception:
        return None
    df = employees_df_for_nav(username, "payroll", full)
    if df is None or getattr(df, "empty", True):
        return None
    want = normalize_emp_code(emp_code)
    for _, row in df.iterrows():
        if normalize_emp_code(str(row.get("emp_code") or "")) != want:
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
