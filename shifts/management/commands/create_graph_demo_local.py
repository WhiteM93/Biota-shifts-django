"""
Локальное демо: график (4 отдела × 6 должностей) и тестовые учётки.

  python manage.py create_graph_demo_local

Требует BIOTA_DEMO_DATA (по умолчанию включён при локальном fallback) или недоступную BIOTA_DB.
"""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime

from django.core.management.base import BaseCommand

from biota_shifts import auth as biota_auth
from biota_shifts import db as biota_db
from biota_shifts import schedule as biota_schedule
from biota_shifts.config import APP_DIR
from shifts.department_order import save_department_order
from shifts.management.commands.create_test_schedule_and_regulations import (
    _fill_test_schedule,
)
from shifts.position_order import save_position_order

DEMO_DEPTS = (
    "Механический",
    "Сборочный",
    "ОТК",
    "Инструментальный",
)
DEMO_POSITIONS = (
    "Токарь",
    "Фрезеровщик",
    "Сборщик",
    "Слесарь",
    "Наладчик",
    "Контролёр",
)
LAST_NAMES = (
    "Иванов",
    "Петров",
    "Сидоров",
    "Козлов",
    "Новиков",
    "Морозов",
    "Волков",
    "Лебедев",
    "Семёнов",
    "Егоров",
    "Павлов",
    "Кузнецов",
    "Соколов",
    "Попов",
    "Васильев",
    "Михайлов",
    "Фёдоров",
    "Андреев",
    "Макаров",
    "Никитин",
    "Захаров",
    "Зайцев",
    "Соловьёв",
    "Борисов",
)
FIRST_NAMES = (
    "Иван",
    "Пётр",
    "Сергей",
    "Андрей",
    "Дмитрий",
    "Алексей",
    "Виктор",
    "Николай",
    "Олег",
    "Павел",
    "Роман",
    "Егор",
    "Максим",
    "Артём",
    "Кирилл",
    "Илья",
    "Тимур",
    "Денис",
    "Владимир",
    "Глеб",
    "Ярослав",
    "Станислав",
    "Григорий",
    "Филипп",
)

GRAPH_DEMO_JSON = APP_DIR / "local" / "graph_demo_employees.json"

LEGACY_TEST_USERNAMES = ("test_graph", "test_view")

TEST_USERS = (
    {
        "username": "test1",
        "password": "test1",
        "display_name": "Тест 1 — редактор графика",
        "role": biota_auth.USER_ROLE_MANAGER,
        "email": "test1@local.test",
    },
    {
        "username": "test2",
        "password": "test2",
        "display_name": "Тест 2 — только просмотр",
        "role": biota_auth.USER_ROLE_EXECUTOR,
        "email": "test2@local.test",
    },
)


def build_graph_demo_employees() -> list[dict]:
    rows: list[dict] = []
    idx = 0
    for dept_i, dept in enumerate(DEMO_DEPTS):
        area = f"Участок {dept_i + 1}"
        for pos in DEMO_POSITIONS:
            code = str(2001 + idx)
            rows.append(
                {
                    "emp_code": code,
                    "last_name": LAST_NAMES[idx % len(LAST_NAMES)],
                    "first_name": FIRST_NAMES[idx % len(FIRST_NAMES)],
                    "department_name": dept,
                    "position_name": pos,
                    "area_name": area,
                }
            )
            idx += 1
    return rows


def _upsert_test_user(
    username: str,
    password: str,
    *,
    display_name: str,
    role: str,
    email: str,
) -> None:
    store = biota_auth._load_users_store()
    salt_hex, hash_hex = biota_auth._pbkdf2_hash(password)
    now = datetime.now(biota_auth.MSK).strftime("%Y-%m-%d %H:%M")
    rec = dict(store.get(username) or {})
    rec.update(
        {
            "salt_hex": salt_hex,
            "hash_hex": hash_hex,
            "approved": True,
            "approved_at": now,
            "email_verified": True,
            "role": role,
            "display_name": display_name,
            "email": email,
            "access_scope": "all",
            "allowed_department": "",
            "allowed_area": "",
            "allowed_departments": [],
            "allowed_areas": [],
            "nav_dep_filters": {},
            "nav": {k: True for k in biota_auth.NAV_KEYS},
        }
    )
    if "created_at" not in rec:
        rec["created_at"] = now
    store[username] = rec
    biota_auth._save_users_store(store)


class Command(BaseCommand):
    help = "Локальный график (4 отдела, 6 должностей) и тестовые логины test1 / test2"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)
        parser.add_argument(
            "--users-only",
            action="store_true",
            help="Только учётные записи, без Excel и JSON сотрудников",
        )
        parser.add_argument(
            "--schedule-only",
            action="store_true",
            help="Только сотрудники и график, без учёток",
        )

    def handle(self, *args, **options):
        today = date.today()
        year = options["year"] or today.year
        month = options["month"] or today.month
        if month < 1 or month > 12:
            self.stderr.write(self.style.ERROR("Месяц должен быть от 1 до 12."))
            return

        if not options["users_only"]:
            rows = build_graph_demo_employees()
            GRAPH_DEMO_JSON.parent.mkdir(parents=True, exist_ok=True)
            GRAPH_DEMO_JSON.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Сотрудники: {len(rows)} ({len(DEMO_DEPTS)} отдела, {len(DEMO_POSITIONS)} должностей) -> {GRAPH_DEMO_JSON}"
                )
            )

            save_department_order(list(DEMO_DEPTS))
            save_position_order(list(DEMO_POSITIONS))
            self.stdout.write("Порядок отделов и должностей обновлён (.biota_*_order.json).")

            import pandas as pd

            employees_df = pd.DataFrame(rows)
            base = biota_schedule.empty_schedule_from_db(employees_df, year, month)
            filled = _fill_test_schedule(base, year, month)
            filled = biota_schedule.normalize_schedule_excel(filled, employees_df, year, month)
            path = biota_schedule.save_schedule_table(filled, year, month)
            self.stdout.write(
                self.style.SUCCESS(
                    f"График: {path} ({calendar.month_name[month]} {year})"
                )
            )

        if not options["schedule_only"]:
            store = biota_auth._load_users_store()
            for old in LEGACY_TEST_USERNAMES:
                store.pop(old, None)
            biota_auth._save_users_store(store)
            for spec in TEST_USERS:
                _upsert_test_user(
                    spec["username"],
                    spec["password"],
                    display_name=spec["display_name"],
                    role=spec["role"],
                    email=spec["email"],
                )
            self.stdout.write(self.style.SUCCESS("Учётные записи (.biota_users.json):"))
            for spec in TEST_USERS:
                role_ru = (
                    "руководитель (редактирование графика)"
                    if spec["role"] == biota_auth.USER_ROLE_MANAGER
                    else "исполнитель (без сохранения)"
                )
                self.stdout.write(
                    f"  - {spec['username']} / {spec['password']} - {role_ru}"
                )

        self.stdout.write("")
        self.stdout.write(
            "Откройте /graph/ — редактирование при фильтрах «Все» (отделы и должности)."
        )
        self.stdout.write(
            "В .env добавьте BIOTA_GRAPH_DEMO=1 (или отключите BIOTA_DB) — справочник из local/graph_demo_employees.json."
        )
