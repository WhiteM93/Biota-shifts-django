from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from biota_shifts.config import ADMIN_USERNAME
from shifts.models import (
    WarehouseEmployee,
    WarehouseFastenerItem,
    WarehouseFastenerMovement,
    WarehouseFastenerType,
)


class InventoryFastenersViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = ADMIN_USERNAME
        session.save()
        self.url = reverse("inventory_fasteners")
        self.fastener_type, _ = WarehouseFastenerType.objects.get_or_create(
            code="button-head-hex-socket",
            defaults={
                "name": "Винт с полукруглой головкой под внутренний шестигранник",
                "standard": "ISO 7380",
                "is_active": True,
                "sort_order": 10,
            },
        )
        WarehouseEmployee.objects.get_or_create(
            name="Тестов Т.",
            defaults={"is_active": True},
        )

    def _messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_page_loads_and_contains_fasteners_tab(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn("Метизы", html)
        self.assertIn("inventory/fasteners", html)

    def test_add_fastener_creates_item_and_restock_movement(self):
        response = self.client.post(
            self.url,
            {
                "action": "add_fastener_item",
                "fastener_type_id": self.fastener_type.id,
                "thread_diameter": "M6",
                "length_mm": "16",
                "quantity": "120",
                "movement_date": date.today().isoformat(),
                "strength_class": "8.8",
                "material": "Сталь",
                "coating": "Цинк",
                "warehouse_location": "A-01-02",
                "comment": "Первый приход",
                "notes": "Для наладки Haas",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("Позиция добавлена" in m for m in self._messages(response)))

        item = WarehouseFastenerItem.objects.get(
            fastener_type=self.fastener_type,
            thread_diameter_mm=Decimal("6"),
            length_mm=16,
            strength_class="8.8",
            material="Сталь",
            coating="Цинк",
            warehouse_location="A-01-02",
        )
        self.assertEqual(item.quantity, 120)
        movement = WarehouseFastenerMovement.objects.get(item=item, movement_type="restock")
        self.assertEqual(movement.quantity, 120)
        self.assertEqual(movement.comment, "Первый приход")

    def test_issue_movement_reduces_stock_and_keeps_employee(self):
        item = WarehouseFastenerItem.objects.create(
            fastener_type=self.fastener_type,
            thread_diameter_mm=Decimal("8"),
            length_mm=20,
            quantity=50,
        )
        response = self.client.post(
            self.url,
            {
                "action": "move_fastener_stock",
                "item_id": item.id,
                "movement_type": "issue",
                "quantity": "12",
                "movement_date": date.today().isoformat(),
                "employee_name": "тестов т.",
                "comment": "Выдали на наладку",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("Движение метизов сохранено" in m for m in self._messages(response)))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 38)

        movement = WarehouseFastenerMovement.objects.filter(item=item, movement_type="issue").latest("id")
        self.assertEqual(movement.employee_name, "Тестов Т.")
        self.assertEqual(movement.quantity, 12)

    def test_filter_by_thread_and_length(self):
        WarehouseFastenerItem.objects.create(
            fastener_type=self.fastener_type,
            thread_diameter_mm=Decimal("6"),
            length_mm=16,
            quantity=30,
        )
        WarehouseFastenerItem.objects.create(
            fastener_type=self.fastener_type,
            thread_diameter_mm=Decimal("8"),
            length_mm=30,
            quantity=40,
        )
        response = self.client.get(self.url, {"thread_mm": "6", "length_mm": "16"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn("M6", html)
        self.assertIn(">16<", html)
        self.assertNotIn("M8", html)
