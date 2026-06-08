"""Тесты сводки «не отметились в СКУД»."""
from datetime import date, datetime

import pandas as pd
from django.test import SimpleTestCase

from biota_shifts.attendance_summary import (
    SLOT_EVENING,
    SLOT_MORNING,
    build_attendance_summary,
    format_summary_text,
)
from biota_shifts.constants import MSK
from biota_shifts.notification_settings import parse_chat_ids_text, save_notification_settings


def _emp_df():
    return pd.DataFrame(
        [
            {
                "emp_code": "101",
                "last_name": "Иванов",
                "first_name": "Иван",
                "department_name": "Цех 1",
            },
            {
                "emp_code": "202",
                "last_name": "Петров",
                "first_name": "Пётр",
                "department_name": "Цех 1",
            },
            {
                "emp_code": "303",
                "last_name": "Сидоров",
                "first_name": "Сидор",
                "department_name": "Цех 2",
            },
        ]
    )


def _schedule_df(d: date):
    cols = ["Код", "Сотрудник"] + [str(i) for i in range(1, 32)]
    row1 = {"Код": "101", "Сотрудник": "Иванов И."}
    row2 = {"Код": "202", "Сотрудник": "Петров П."}
    row3 = {"Код": "303", "Сотрудник": "Сидоров С."}
    for c in cols[2:]:
        row1[c] = ""
        row2[c] = ""
        row3[c] = ""
    row1[str(d.day)] = "д"
    row2[str(d.day)] = "д"
    row3[str(d.day)] = "н"
    return pd.DataFrame([row1, row2, row3])


def _punch(emp_code: str, dt: datetime) -> dict:
    return {
        "emp_code": emp_code,
        "punch_time": dt.astimezone(datetime.now().astimezone().tzinfo).isoformat(),
    }


class AttendanceSummaryTests(SimpleTestCase):
    def setUp(self):
        self.d = date(2026, 5, 26)
        self.morning_cutoff = datetime(2026, 5, 26, 8, 20, 0, tzinfo=MSK)
        self.evening_cutoff = datetime(2026, 5, 26, 20, 20, 0, tzinfo=MSK)

    def test_morning_lists_only_day_shift_without_punch(self):
        punches = pd.DataFrame(
            [
                {
                    "emp_code": "202",
                    "punch_time": datetime(2026, 5, 26, 7, 55, 0, tzinfo=MSK),
                }
            ]
        )
        summary = build_attendance_summary(
            SLOT_MORNING,
            employees_df=_emp_df(),
            schedule_df=_schedule_df(self.d),
            punches_df=punches,
            shift_date=self.d,
            check_at=self.morning_cutoff,
            settings={"blacklist_emp_codes": [], "morning_time": "08:20"},
        )
        codes = {a.emp_code for a in summary.absent}
        self.assertEqual(codes, {"101"})
        self.assertEqual(summary.absent_count, 1)

    def test_blacklist_excludes_employee(self):
        summary = build_attendance_summary(
            SLOT_MORNING,
            employees_df=_emp_df(),
            schedule_df=_schedule_df(self.d),
            punches_df=pd.DataFrame(),
            shift_date=self.d,
            check_at=self.morning_cutoff,
            settings={"blacklist_emp_codes": ["101", "202"]},
        )
        self.assertEqual(summary.absent_count, 0)

    def test_evening_lists_night_shift_without_punch(self):
        punches = pd.DataFrame()
        summary = build_attendance_summary(
            SLOT_EVENING,
            employees_df=_emp_df(),
            schedule_df=_schedule_df(self.d),
            punches_df=punches,
            shift_date=self.d,
            check_at=self.evening_cutoff,
            settings={"blacklist_emp_codes": [], "evening_time": "20:20"},
        )
        codes = {a.emp_code for a in summary.absent}
        self.assertEqual(codes, {"303"})

    def test_late_first_punch_counts_as_not_marked(self):
        punches = pd.DataFrame(
            [
                {
                    "emp_code": "101",
                    "punch_time": datetime(2026, 5, 26, 8, 25, 0, tzinfo=MSK),
                }
            ]
        )
        summary = build_attendance_summary(
            SLOT_MORNING,
            employees_df=_emp_df(),
            schedule_df=_schedule_df(self.d),
            punches_df=punches,
            shift_date=self.d,
            check_at=self.morning_cutoff,
            settings={"blacklist_emp_codes": [], "morning_time": "08:20"},
        )
        codes = {a.emp_code for a in summary.absent}
        self.assertIn("101", codes)
        late = next(a for a in summary.absent if a.emp_code == "101")
        self.assertIsNotNone(late.first_punch_at)

    def test_format_summary_text_empty(self):
        summary = build_attendance_summary(
            SLOT_MORNING,
            employees_df=_emp_df(),
            schedule_df=_schedule_df(self.d),
            punches_df=pd.DataFrame(
                [
                    {"emp_code": "101", "punch_time": datetime(2026, 5, 26, 7, 50, 0, tzinfo=MSK)},
                    {"emp_code": "202", "punch_time": datetime(2026, 5, 26, 7, 55, 0, tzinfo=MSK)},
                ]
            ),
            shift_date=self.d,
            check_at=self.morning_cutoff,
            settings={"blacklist_emp_codes": [], "morning_time": "08:20"},
        )
        text = format_summary_text(summary)
        self.assertIn("замечаний нет", text)

    def test_parse_chat_ids_multiline(self):
        self.assertEqual(parse_chat_ids_text("@a\n-100\n@a"), ["@a", "-100"])

    def test_save_notification_settings_normalizes(self):
        saved = save_notification_settings(
            {
                "enabled": True,
                "morning_time": "8:20",
                "evening_time": "20:20",
                "telegram_bot_token": "123:ABC",
                "telegram_chat_ids": ["@chan", "@chan", " 999 "],
                "blacklist_emp_codes": ["101.0", "101"],
            }
        )
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["morning_time"], "08:20")
        self.assertEqual(saved["telegram_bot_token"], "123:ABC")
        self.assertEqual(saved["telegram_chat_ids"], ["@chan", "999"])
        self.assertEqual(saved["blacklist_emp_codes"], ["101"])
