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
    payroll_schedule_shift_kind,
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

    def test_stored_zero_yields_schedule_default(self):
        self.assertEqual(effective_tab_hours(0, 12.0), 12.0)
        self.assertEqual(effective_tab_hours(None, 12.0), 12.0)
        self.assertEqual(effective_tab_hours(8, 12.0), 8.0)
        self.assertEqual(effective_tab_hours(0, 0.0), 0.0)


class PayrollDayAccrualTests(SimpleTestCase):
    def test_double_shift_splits_day_and_night(self):
        profile = MagicMock()
        profile.shift_hours = 12
        profile.hourly_rate_day = Decimal("450")
        profile.hourly_rate_night = Decimal("500")
        self.assertEqual(payroll_day_accrual_rub(profile, "д", 24), Decimal("11400.00"))
        self.assertEqual(payroll_day_accrual_rub(profile, "д", 12), Decimal("5400.00"))


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
