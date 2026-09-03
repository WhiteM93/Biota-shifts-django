"""Создать тестовые выдачи с невозвращённым остатком (локально)."""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "biota_site.settings")
os.environ["BIOTA_INVENTORY_NOTIFY"] = "0"

import django

django.setup()

from django.db import connection, transaction
from django.db.models.signals import post_save
from django.db.utils import OperationalError

from shifts.models import StockMovement, ToolItem


ISSUES = [
    ("Иванов И.", 2, 0, "admin", "Тест: фреза"),
    ("Иванов И.", 1, 1, "admin", "Тест: второй инструмент"),
    ("Петров П.", 3, 2, "maxim", "Тест: метчик"),
    ("Сидоров С.", 1, 3, "admin", "Тест: центровка"),
    ("Козлова А.", 2, 4, "maxim", "Тест: зенкер"),
]


def _wait_db(retries: int = 8) -> None:
    for i in range(retries):
        try:
            with connection.cursor() as cur:
                cur.execute("PRAGMA busy_timeout=60000")
                cur.execute("BEGIN IMMEDIATE")
                cur.execute("COMMIT")
            return
        except OperationalError:
            time.sleep(1.5 * (i + 1))
    raise OperationalError("database is locked")


def main() -> None:
    post_save.disconnect(sender=StockMovement)
    _wait_db()
    tools = list(
        ToolItem.objects.filter(is_deleted=False, quantity__gte=1).order_by("-quantity", "id")[:12]
    )
    if not tools:
        print("NO_TOOLS")
        return

    created = 0
    today = date.today()
    for emp, qty, day_offset, issuer, comment in ISSUES:
        for attempt in range(5):
            try:
                _wait_db()
                with transaction.atomic():
                    tool = None
                    for t in tools:
                        t.refresh_from_db(fields=["quantity"])
                        if t.quantity >= qty:
                            tool = t
                            break
                    if tool is None:
                        print(f"SKIP no_stock")
                        break
                    tool.quantity -= qty
                    tool.save(update_fields=["quantity", "updated_at"])
                    StockMovement.objects.create(
                        movement_type="issue",
                        tool=tool,
                        quantity=qty,
                        employee_name=emp,
                        movement_date=today - timedelta(days=day_offset),
                        comment=comment,
                        created_by_account=issuer,
                    )
                    created += 1
                    print(f"OK emp={emp!r} qty={qty} tool_id={tool.id}")
                break
            except OperationalError as exc:
                if attempt >= 4:
                    print(f"FAIL {emp!r}: {exc}")
                else:
                    time.sleep(2)

    open_n = (
        StockMovement.objects.filter(movement_type="issue", is_reverted=False)
        .exclude(employee_name="")
        .count()
    )
    print(f"CREATED={created} ISSUE_TOTAL={open_n}")


if __name__ == "__main__":
    main()
