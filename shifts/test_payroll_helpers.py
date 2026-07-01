from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from datetime import date

from shifts.payroll_helpers import (
    compute_payroll_totals,
    default_tab_hours_for_schedule_cell,
    effective_tab_hours,
    payroll_calendar_weeks,
    payroll_day_accrual_rub,
    payroll_hourly_rate_for_shift,
    payroll_payout_parts_from_base,
    payroll_schedule_shift_kind,
    payroll_tab_day_night_hours,
)


class PayrollScheduleShiftKindTests(SimpleTestCase):
    def test_cyrillic_and_latin(self):
        self.assertEqual(payroll_schedule_shift_kind("н"), "н")
        self.assertEqual(payroll_schedule_shift_kind("N"), "н")
        self.assertEqual(payroll_schedule_shift_kind("д"), "д")
        self.assertEqual(payroll_schedule_shift_kind("D"), "д")
        self.assertEqual(payroll_schedule_shift_kind("от"), "")
        self.assertEqual(payroll_schedule_shift_kind(""), "")


class PayrollTabDefaultTests(SimpleTestCase):
    def test_work_shift_uses_shift_hours(self):
        self.assertEqual(default_tab_hours_for_schedule_cell("д", 10), 10.0)
        self.assertEqual(default_tab_hours_for_schedule_cell("н", 12), 12.0)
        self.assertEqual(default_tab_hours_for_schedule_cell("от", 8), 0.0)

    def test_explicit_zero_honored_on_shift_day(self):
        self.assertEqual(effective_tab_hours(0, 12.0), 0.0)
        self.assertEqual(effective_tab_hours(None, 12.0), 12.0)
        self.assertEqual(effective_tab_hours(8, 12.0), 8.0)
        self.assertEqual(effective_tab_hours(0, 0.0), 0.0)


class PayrollDayNightHoursTests(SimpleTestCase):
    def test_split_day_night_and_holiday_double(self):
        profile = MagicMock()
        profile.shift_hours = 12
        self.assertEqual(payroll_tab_day_night_hours(profile, "д", 12), (Decimal("12"), Decimal("0")))
        self.assertEqual(payroll_tab_day_night_hours(profile, "н", 12), (Decimal("0"), Decimal("12")))
        self.assertEqual(payroll_tab_day_night_hours(profile, "д", 24), (Decimal("24"), Decimal("0")))
        self.assertEqual(payroll_tab_day_night_hours(profile, "н", 24), (Decimal("0"), Decimal("24")))


class PayrollDayAccrualTests(SimpleTestCase):
    def test_holiday_double_pay_one_shift_rate(self):
        profile = MagicMock()
        profile.shift_hours = 12
        profile.hourly_rate_day = Decimal("500")
        profile.hourly_rate_night = Decimal("1000")
        self.assertEqual(payroll_day_accrual_rub(profile, "д", 24), Decimal("12000.00"))
        self.assertEqual(payroll_day_accrual_rub(profile, "н", 24), Decimal("24000.00"))
        self.assertEqual(payroll_day_accrual_rub(profile, "д", 12), Decimal("6000.00"))


class PayrollPayoutFormulaTests(SimpleTestCase):
    def test_user_formula_guaranteed_slices_bonus(self):
        base = Decimal("100000")
        parts = payroll_payout_parts_from_base(
            base,
            quality_pct=Decimal("20"),
            result_pct=Decimal("20"),
            mode_pct=Decimal("10"),
            bonus_percent=Decimal("5"),
            bonus_rub=Decimal("1000"),
            penalty_rub=Decimal("500"),
        )
        self.assertEqual(parts["guaranteed_rub"], Decimal("50000.00"))
        self.assertEqual(parts["slices_rub"], Decimal("50000.00"))
        self.assertEqual(parts["tab_payout"], Decimal("100000.00"))
        self.assertEqual(parts["bonus_pct_amount"], Decimal("5000.00"))
        self.assertEqual(parts["bonus_total"], Decimal("6000.00"))
        self.assertEqual(parts["total"], Decimal("105500.00"))


class PayrollRateTests(SimpleTestCase):
    def test_night_uses_night_rate(self):
        profile = MagicMock()
        profile.hourly_rate_day = Decimal("100")
        profile.hourly_rate_night = Decimal("150")
        self.assertEqual(payroll_hourly_rate_for_shift(profile, "н"), Decimal("150"))
        self.assertEqual(payroll_hourly_rate_for_shift(profile, "д"), Decimal("100"))
        self.assertEqual(payroll_hourly_rate_for_shift(profile, ""), Decimal("100"))


class PayrollCalendarTests(SimpleTestCase):
    def test_weeks_cover_month(self):
        rows = [
            {
                "date": date(2026, 6, d),
                "date_iso": date(2026, 6, d).isoformat(),
                "weekday": "пн",
                "graph_shift": "д" if d <= 5 else "",
                "skud_h": 0,
                "tab_h": 8,
                "default_tab_h": 8,
            }
            for d in range(1, 31)
        ]
        weeks = payroll_calendar_weeks(rows)
        self.assertGreaterEqual(len(weeks), 4)
        flat = [c for w in weeks for c in w if c]
        self.assertEqual(len(flat), 30)


class PayrollTotalsTests(SimpleTestCase):
    def test_night_hours_at_night_rate(self):
        profile = MagicMock()
        profile.hourly_rate_day = Decimal("100")
        profile.hourly_rate_night = Decimal("200")
        profile.shift_hours = 8
        settlement = MagicMock()
        settlement.penalty_quality_pct = 20
        settlement.penalty_result_pct = 20
        settlement.penalty_mode_pct = 10
        settlement.bonus_percent = 0
        settlement.bonus_rub = 0
        settlement.penalty_rub = 0
        day_rows = [
            {
                "date_iso": "2026-05-01",
                "graph_shift": "н",
                "tab_h": 8,
                "skud_h": 0,
            }
        ]
        totals = compute_payroll_totals(profile, settlement, day_rows)
        self.assertEqual(totals["base_tab"], Decimal("1600.00"))
