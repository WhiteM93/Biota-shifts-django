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
from biota_shifts.constants import MONTH_NAMES_RU, SCHEDULE_CODES
from biota_shifts.emp_codes import normalize_emp_code
from biota_shifts import schedule as biota_schedule
from biota_shifts.schedule import employee_label_row


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


def schedule_cell_for_day(row, day: int):
    """Значение ячейки графика для календарного дня (колонки «1»…«31» или int)."""
    if row is None:
        return None
    for key in (str(day), day, f"{day:02d}"):
        if key in row.index:
            return row.get(key)
    day_s = str(day)
    for col in row.index:
        if str(col).strip() == day_s:
            return row.get(col)
    return None


def effective_tab_hours(raw_tab, default_tab: float) -> float:
    """Часы табеля: сохранённое значение или авто из графика.

    Сохранённый 0 не блокирует подстановку, если по графику должна быть смена (default_tab > 0).
    """
    if raw_tab is None:
        return default_tab
    try:
        tab = float(raw_tab)
    except (TypeError, ValueError):
        return default_tab
    if tab == 0 and default_tab > 0:
        return default_tab
    return tab


def payroll_schedule_shift_kind(cell) -> str:
    """Код смены для расчёта ЗП: «д», «н» или пусто (не рабочая смена)."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return ""
    s = str(cell).strip().lower()
    if s in ("н", "n"):
        return "н"
    if s in ("д", "d"):
        return "д"
    if s in SCHEDULE_CODES:
        if s == "н":
            return "н"
        if s == "д":
            return "д"
    return ""


def default_tab_hours_for_schedule_cell(cell, shift_hours: int) -> float:
    """Часы табеля по умолчанию: длительность смены из настроек сотрудника на рабочие д/н."""
    sh = max(0, int(shift_hours or 0))
    return float(sh) if payroll_schedule_shift_kind(cell) in ("д", "н") else 0.0


def payroll_hourly_rate_for_shift(profile, shift_kind: str) -> Decimal:
    """Ставка ₽/ч по типу смены (дневная / ночная)."""
    D = Decimal
    day_rate = profile.hourly_rate_day if profile.hourly_rate_day is not None else D("0")
    night_rate = profile.hourly_rate_night if profile.hourly_rate_night is not None else D("0")
    if shift_kind == "н":
        return night_rate
    return day_rate


def _profile_shift_hours_int(profile, default: int = 8) -> int:
    raw = getattr(profile, "shift_hours", None)
    if isinstance(raw, bool):
        return default
    if isinstance(raw, (int, float)):
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return default
    return default


def payroll_tab_day_night_hours(profile, shift_kind: str, tab_h) -> tuple[Decimal, Decimal]:
    """Разбивка часов табеля: (дневные, ночные) для суммы дн×ставка + ноч×ставка.

    Если в табеле ≥ 2× длины смены (напр. 24 при смене 12 ч) — праздничная двойная оплата:
    одна смена по коду графика (д/н), часы для расчёта = 2× shift_hours по соответствующей ставке,
    а не «день + ночь» в одни сутки.
    """
    D = Decimal
    h = D(str(tab_h or 0))
    if h <= 0:
        return D("0"), D("0")
    sh = D(str(_profile_shift_hours_int(profile)))
    if sh > 0 and h >= sh * D("2") - D("0.01"):
        pay_h = sh * D("2")
        if shift_kind == "н":
            return D("0"), pay_h
        return pay_h, D("0")
    if shift_kind == "н":
        return D("0"), h
    return h, D("0")


def payroll_day_accrual_rub(profile, shift_kind: str, tab_h) -> Decimal:
    """Сумма за день: дневные_ч × дн.ставка + ночные_ч × ноч.ставка."""
    D = Decimal
    day_h, night_h = payroll_tab_day_night_hours(profile, shift_kind, tab_h)
    day_r = profile.hourly_rate_day if profile.hourly_rate_day is not None else D("0")
    night_r = profile.hourly_rate_night if profile.hourly_rate_night is not None else D("0")
    return (day_h * day_r + night_h * night_r).quantize(D("0.01"))


def payroll_base_from_hours(profile, day_hours: Decimal, night_hours: Decimal) -> Decimal:
    """Начисление (сумма) = дневные ч × дн.ставка + ночные ч × ноч.ставка."""
    D = Decimal
    day_r = profile.hourly_rate_day if profile.hourly_rate_day is not None else D("0")
    night_r = profile.hourly_rate_night if profile.hourly_rate_night is not None else D("0")
    return (day_hours * day_r + night_hours * night_r).quantize(D("0.01"))


def payroll_payout_parts_from_base(
    base: Decimal,
    *,
    quality_pct: Decimal,
    result_pct: Decimal,
    mode_pct: Decimal,
    bonus_percent: Decimal,
    bonus_rub: Decimal,
    penalty_rub: Decimal,
    include_fixed_rub: bool = True,
) -> dict[str, Decimal]:
    """Итог: 50% гарантия + доли % от суммы (20+20+10) + премия % и ₽ − штраф ₽."""
    D = Decimal
    b = D(str(base or 0)).quantize(D("0.01"))
    q = min(max(D(str(quality_pct or 0)), D("0")), TAB_SLICE_QUALITY_PCT)
    r = min(max(D(str(result_pct or 0)), D("0")), TAB_SLICE_RESULT_PCT)
    m = min(max(D(str(mode_pct or 0)), D("0")), TAB_SLICE_MODE_PCT)
    b_pct = max(D("0"), D(str(bonus_percent or 0)))

    guaranteed = (b / D("2")).quantize(D("0.01"))
    quality_pay = (b * q / D("100")).quantize(D("0.01"))
    result_pay = (b * r / D("100")).quantize(D("0.01"))
    mode_pay = (b * m / D("100")).quantize(D("0.01"))
    slices_pay = (quality_pay + result_pay + mode_pay).quantize(D("0.01"))
    tab_payout = (guaranteed + slices_pay).quantize(D("0.01"))

    bonus_pct_amt = (b * b_pct / D("100")).quantize(D("0.01"))
    b_rub = D(str(bonus_rub or 0)).quantize(D("0.01"))
    pen_rub = D(str(penalty_rub or 0)).quantize(D("0.01"))
    if b_rub < 0:
        b_rub = D("0")
    if pen_rub < 0:
        pen_rub = D("0")
    if not include_fixed_rub:
        b_rub = D("0")
        pen_rub = D("0")
    bonus_total = (bonus_pct_amt + b_rub).quantize(D("0.01"))
    total_raw = tab_payout + bonus_total - pen_rub
    total = total_raw.quantize(D("0.01"))
    if total < 0:
        total = D("0")
    penalties = (b - tab_payout).quantize(D("0.01"))
    penalty_pp_sum = (
        (TAB_SLICE_QUALITY_PCT - q) + (TAB_SLICE_RESULT_PCT - r) + (TAB_SLICE_MODE_PCT - m)
    ).quantize(D("0.01"))
    return {
        "guaranteed_rub": guaranteed,
        "slices_rub": slices_pay,
        "tab_payout": tab_payout,
        "bonus_pct_amount": bonus_pct_amt,
        "bonus_rub": b_rub,
        "bonus_total": bonus_total,
        "penalty_rub": pen_rub,
        "penalties": penalties,
        "total": total,
        "penalty_pp_sum": penalty_pp_sum,
        "penalty_pct_sum": penalty_pp_sum,
    }


def schedule_cell_display(cell) -> str:
    """Буква из графика для отображения (д/н или как в ячейке)."""
    kind = payroll_schedule_shift_kind(cell)
    if kind:
        return kind
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return ""
    s = str(cell).strip()
    return s[:4] if s else ""


def payroll_calendar_weeks(day_rows: list[dict]) -> list[list[dict | None]]:
    """Недели месяца для календарной сетки (пн–вс), ячейки None — пусто."""
    if not day_rows:
        return []
    first = day_rows[0]["date"]
    by_day = {r["date"].day: r for r in day_rows}
    weeks: list[list[dict | None]] = []
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(first.year, first.month):
        weeks.append([by_day.get(d) if d else None for d in week])
    return weeks


def tab_by_day_from_schedule(day_rows: list[dict]) -> dict[str, float]:
    """Словарь часов табеля из графика (д/н → длительность смены)."""
    out: dict[str, float] = {}
    for r in day_rows:
        dk = str(r.get("date_iso") or "")
        if not dk:
            continue
        if r.get("graph_shift"):
            out[dk] = round(float(r.get("default_tab_h") or 0), 2)
        else:
            out[dk] = 0.0
    return out


def payroll_day_rows(
    emp_code: str,
    year: int,
    month: int,
    employees_df: pd.DataFrame,
    tab_by_day: dict[str, Any],
    skud_by_day: dict[str, float],
    schedule_df: pd.DataFrame,
    *,
    shift_hours: int = 8,
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
        raw_cell = schedule_cell_for_day(row, d)
        shift_kind = payroll_schedule_shift_kind(raw_cell)
        graph_disp = schedule_cell_display(raw_cell) or "—"
        sk = float(skud_by_day.get(dk, 0.0))
        default_tab = default_tab_hours_for_schedule_cell(raw_cell, shift_hours)
        tab = effective_tab_hours(tab_by_day.get(dk), default_tab)
        _sh = type("_Sh", (), {"shift_hours": shift_hours})()
        tab_d, tab_n = payroll_tab_day_night_hours(_sh, shift_kind, tab)
        out.append(
            {
                "date": dd,
                "date_iso": dk,
                "weekday": wdays[dd.weekday()],
                "graph": graph_disp,
                "graph_shift": shift_kind,
                "skud_h": round(sk, 2),
                "tab_h": tab,
                "tab_day_h": float(tab_d),
                "tab_night_h": float(tab_n),
                "default_tab_h": default_tab,
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


# Сумма = дневные_ч×дн.ставка + ночные_ч×ноч.ставка.
# К выплате по табелю = 50% суммы (гарантия) + доли % от суммы (качество/результат/режим, макс. 20+20+10).
# Итог = гарантия + доли + премия (% от суммы + ₽) − штраф ₽.
# Поля penalty_* — выплачиваемый % от суммы по линии (0…макс.), не удержание.
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
    tab_sum = D("0")
    skud_sum = D("0")
    day_hours = D("0")
    night_hours = D("0")
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
        dh, nh = payroll_tab_day_night_hours(profile, str(r.get("graph_shift") or ""), h)
        day_hours += dh
        night_hours += nh
    gross = payroll_base_from_hours(profile, day_hours, night_hours)
    return {
        "total_tab_hours": tab_sum.quantize(D("0.01")),
        "total_skud_hours": skud_sum.quantize(D("0.01")),
        "total_day_hours": day_hours.quantize(D("0.01")),
        "total_night_hours": night_hours.quantize(D("0.01")),
        "gross_accrual_rub": gross,
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
    """Сумма по дн/ноч часам; итог = 50% + доли + премия − штраф ₽ (см. payroll_payout_parts_from_base)."""
    D = Decimal
    dadj = defect_adjust_sum_by_kind
    day_hours = D("0")
    night_hours = D("0")
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
        dh, nh = payroll_tab_day_night_hours(profile, str(r.get("graph_shift") or ""), h)
        day_hours += dh
        night_hours += nh

    base = payroll_base_from_hours(profile, day_hours, night_hours)
    side = effective_side_payroll_fields(settlement, dadj)
    parts = payroll_payout_parts_from_base(
        base,
        quality_pct=side["penalty_quality_pct"],
        result_pct=side["penalty_result_pct"],
        mode_pct=side["penalty_mode_pct"],
        bonus_percent=side["bonus_percent"],
        bonus_rub=side["bonus_rub"],
        penalty_rub=side["penalty_rub"],
        include_fixed_rub=through_day is None,
    )
    return {
        "base_tab": base,
        "tab_payout": parts["tab_payout"],
        "guaranteed_rub": parts["guaranteed_rub"],
        "slices_rub": parts["slices_rub"],
        "total_skud_hours": skud_sum.quantize(D("0.01")),
        "total_tab_hours": tab_sum.quantize(D("0.01")),
        "total_day_hours": day_hours.quantize(D("0.01")),
        "total_night_hours": night_hours.quantize(D("0.01")),
        "penalties": parts["penalties"],
        "bonus_pct_amount": parts["bonus_pct_amount"],
        "bonus_rub": parts["bonus_rub"],
        "bonus_total": parts["bonus_total"],
        "penalty_rub": parts["penalty_rub"],
        "total": parts["total"],
        "penalty_pp_sum": parts["penalty_pp_sum"],
        "penalty_pct_sum": parts["penalty_pct_sum"],
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
