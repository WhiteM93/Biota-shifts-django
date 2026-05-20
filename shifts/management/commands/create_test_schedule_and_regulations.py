"""
Команда: python manage.py create_test_schedule_and_regulations

Создаёт тестовый Excel-график за месяц и строки регламента перерывов.
Безопасна для повторного запуска: график перезаписывается, регламент дополняется (get_or_create).

Если Biota PostgreSQL недоступна — используются демо-сотрудники из biota_shifts.db.
"""

from __future__ import annotations

import calendar
from datetime import date, time

from django.core.management.base import BaseCommand
from django.db import transaction

from biota_shifts import db as biota_db
from biota_shifts import schedule as biota_schedule
from regulations.models import RegulationPlan


def _load_employees_df():
    cfg = biota_db.db_config()
    try:
        df = biota_db.load_employees(cfg)
    except Exception:
        df = None
    if df is None or getattr(df, "empty", True):
        return biota_db._demo_employees(), True
    return df, False


def _shift_code_for_day(emp_index: int, year: int, month: int, day: int) -> str:
    wd = date(year, month, day).weekday()
    if wd >= 5:
        return ""
    if (day + emp_index) % 19 == 0:
        return "от"
    if (day + emp_index) % 23 == 0:
        return "б"
    group = emp_index % 10
    if group < 5:
        return "д"
    if group < 8:
        return "н"
    return "д" if day % 2 == 1 else "н"


def _fill_test_schedule(df, year: int, month: int):
    day_cols = biota_schedule._schedule_day_cols(year, month)
    out = df.copy()
    for idx in range(len(out)):
        for col in day_cols:
            if col in biota_schedule.PREV_MONTH_KEYS:
                out.at[idx, col] = ""
                continue
            day = int(col)
            out.at[idx, col] = _shift_code_for_day(idx, year, month, day)
    return out


def _breaks_for_shift(shift: str) -> tuple[time, time, time, time, list[dict]]:
    if shift == "н":
        bf_s, bf_e = time(1, 0), time(1, 30)
        ln_s, ln_e = time(4, 0), time(5, 0)
    else:
        bf_s, bf_e = time(9, 0), time(9, 30)
        ln_s, ln_e = time(12, 0), time(13, 0)
    breaks = [
        {"label": "Завтрак", "start": bf_s.strftime("%H:%M"), "end": bf_e.strftime("%H:%M"), "color_kind": "bf"},
        {"label": "Обед", "start": ln_s.strftime("%H:%M"), "end": ln_e.strftime("%H:%M"), "color_kind": "ln"},
    ]
    return bf_s, bf_e, ln_s, ln_e, breaks


class Command(BaseCommand):
    help = "Создать тестовый график (Excel) и регламент перерывов"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None, help="Год графика (по умолчанию — текущий)")
        parser.add_argument("--month", type=int, default=None, help="Месяц графика 1–12 (по умолчанию — текущий)")
        parser.add_argument(
            "--regulations-only",
            action="store_true",
            help="Только регламент, без перезаписи Excel-графика",
        )
        parser.add_argument(
            "--schedule-only",
            action="store_true",
            help="Только график, без регламента",
        )
        parser.add_argument(
            "--reset-regulations",
            action="store_true",
            help="Удалить все строки регламента перед созданием",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        today = date.today()
        year = options["year"] or today.year
        month = options["month"] or today.month
        if month < 1 or month > 12:
            self.stderr.write(self.style.ERROR("Месяц должен быть от 1 до 12."))
            return

        employees_df, used_demo = _load_employees_df()
        if employees_df.empty:
            self.stderr.write(self.style.ERROR("Нет сотрудников для заполнения графика и регламента."))
            return

        if used_demo:
            self.stdout.write(self.style.WARNING("Biota DB недоступна — демо-сотрудники (1001–1010)."))

        n_emp = len(employees_df)
        self.stdout.write(f"Сотрудников: {n_emp}")

        if not options["regulations_only"]:
            base = biota_schedule.empty_schedule_from_db(employees_df, year, month)
            filled = _fill_test_schedule(base, year, month)
            filled = biota_schedule.normalize_schedule_excel(filled, employees_df, year, month)
            path = biota_schedule.save_schedule_table(filled, year, month)
            self.stdout.write(self.style.SUCCESS(f"График: {path} ({calendar.month_name[month]} {year})"))

        if not options["schedule_only"]:
            if options["reset_regulations"]:
                deleted, _ = RegulationPlan.objects.all().delete()
                self.stdout.write(self.style.WARNING(f"Удалено строк регламента: {deleted}"))

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
                    bf_s, bf_e, ln_s, ln_e, breaks = _breaks_for_shift(shift_key)
                    _, was_created = RegulationPlan.objects.get_or_create(
                        employee_code=code,
                        shift=shift_key,
                        defaults={
                            "employee_name": name,
                            "department": dept,
                            "position": pos,
                            "breakfast_start": bf_s,
                            "breakfast_end": bf_e,
                            "lunch_start": ln_s,
                            "lunch_end": ln_e,
                            "breaks": breaks,
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        skipped += 1

            total = RegulationPlan.objects.count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Регламент: добавлено {created}, уже было {skipped}, всего строк {total}."
                )
            )

        self.stdout.write(self.style.SUCCESS("Готово. Откройте «График» и «Регламенты» в приложении."))
