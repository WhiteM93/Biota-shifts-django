"""Интеграционные тесты: приход (bulk) и списание/возврат по выдаче."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.contrib.messages import get_messages
from django.db.models import Sum
from django.test import Client, TestCase
from django.urls import reverse

from biota_shifts.config import ADMIN_USERNAME

from shifts.inventory_views import _arrival_bulk_row_validation_errors
from shifts.models import (
    DrillSpec,
    EndMillSpec,
    InsertSpec,
    StockMovement,
    ToolItem,
    normalize_work_material_codes,
)


class InventoryFlowClientMixin:
    """Сессия admin для inventory_view (biota_username)."""

    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = ADMIN_USERNAME
        session.save()
        self.today = date.today().isoformat()
        self.inv_url = reverse("inventory")

    def _messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]

    def _post_arrival_bulk(self, rows: list[dict]):
        return self.client.post(
            self.inv_url,
            {
                "action": "add_arrival_bulk",
                "rows_json": json.dumps(rows, ensure_ascii=False),
            },
            follow=True,
        )

    def _post_issue_outcome(
        self,
        *,
        issue_id: int,
        returned_qty: int = 0,
        writeoff_qty: int = 0,
        comment: str = "тест",
    ):
        return self.client.post(
            self.inv_url,
            {
                "action": "process_issue_outcome",
                "issue_id": issue_id,
                "returned_qty": returned_qty,
                "writeoff_qty": writeoff_qty,
                "movement_date": self.today,
                "comment": comment,
                "employee_name": "Тестов Т.",
            },
            follow=True,
        )

    def _post_move_stock(self, tool_id: int, movement_type: str, quantity: int, comment: str = ""):
        return self.client.post(
            self.inv_url,
            {
                "action": "move_stock",
                "tool_id": tool_id,
                "movement_type": movement_type,
                "quantity": quantity,
                "movement_date": self.today,
                "comment": comment or "тест движения",
                "employee_name": "Тестов Т.",
            },
            follow=True,
        )


def _drill_row(
    *,
    diameter: str = "8",
    qty: int = 5,
    work_material: str = "P,M",
    supplier: str = "Тест-поставщик",
) -> dict:
    return {
        "category": "drill",
        "quantity": qty,
        "movement_date": date.today().isoformat(),
        "supplier_name": supplier,
        "tool_material": "carbide",
        "coating_type": "yellow",
        "work_material": work_material,
        "dr_diameter_mm": diameter,
        "dr_overall_length_mm": "80",
        "dr_cutting_length_mm": "40",
        "dr_angle_deg": "118",
    }


def _insert_row(*, qty: int = 3, machining: str = "1,3", work_material: str = "P,K") -> dict:
    return {
        "category": "insert",
        "quantity": qty,
        "movement_date": date.today().isoformat(),
        "supplier_name": "Тест",
        "tool_material": "carbide",
        "coating_type": "none",
        "work_material": work_material,
        "ins_shape": "C",
        "ins_edge_code": "12",
        "ins_thickness_code": "04",
        "ins_nose_code": "08",
        "ins_machining_app": machining,
        "ins_family": "APKT",
        "ins_grade": "YG501",
    }


class ArrivalBulkValidationTests(TestCase):
    def test_drill_requires_diameter(self):
        row = _drill_row()
        row.pop("dr_diameter_mm")
        errs = _arrival_bulk_row_validation_errors(row, 1)
        self.assertTrue(any("диаметр" in e.lower() for e in errs))

    def test_requires_work_material_all_categories(self):
        row = _drill_row(work_material="")
        errs = _arrival_bulk_row_validation_errors(row, 1)
        self.assertTrue(any("материала обработки" in e for e in errs))


class ArrivalBulkPostTests(InventoryFlowClientMixin, TestCase):
    def test_arrival_panel_loads(self):
        resp = self.client.get(self.inv_url + "?panel=arrival")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", errors="replace")
        self.assertIn("inv-page--arrival", html)
        self.assertIn("arrival-bulk-form", html)
        self.assertIn("arrival-bulk-add-row", html)
        self.assertIn("work_material_types", html)

    def test_bulk_drill_creates_tool_movement_and_multi_wm(self):
        resp = self._post_arrival_bulk([_drill_row(diameter="7.5", qty=4)])
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any("Оприходовано" in m for m in self._messages(resp)))

        tool = ToolItem.objects.get(category="drill", drill_spec__diameter_mm=Decimal("7.5"))
        self.assertEqual(tool.quantity, 4)
        self.assertEqual(tool.work_material, "P,M")

        mv = StockMovement.objects.filter(tool=tool, movement_type="restock").first()
        self.assertIsNotNone(mv)
        self.assertEqual(mv.quantity, 4)
        self.assertIn("Тест-поставщик", mv.comment)

    def test_bulk_drill_merges_same_spec(self):
        self._post_arrival_bulk([_drill_row(diameter="9", qty=2)])
        self._post_arrival_bulk([_drill_row(diameter="9", qty=3)])

        tools = ToolItem.objects.filter(category="drill", drill_spec__diameter_mm=Decimal("9"))
        self.assertEqual(tools.count(), 1)
        self.assertEqual(tools.first().quantity, 5)
        self.assertEqual(
            StockMovement.objects.filter(tool=tools.first(), movement_type="restock").count(),
            2,
        )

    def test_bulk_insert_creates_spec_with_machining_apps(self):
        resp = self._post_arrival_bulk([_insert_row(qty=6, machining="2,3")])
        self.assertEqual(resp.status_code, 200)

        tool = ToolItem.objects.filter(category="insert", insert_spec__chipbreaker_grade="YG501").first()
        self.assertIsNotNone(tool)
        self.assertEqual(tool.quantity, 6)
        self.assertEqual(tool.insert_spec.machining_application, "2,3")
        self.assertEqual(tool.work_material, "P,K")

    def test_bulk_rejects_missing_work_material(self):
        row = _drill_row(work_material="")
        resp = self._post_arrival_bulk([row])
        self.assertTrue(any("материала обработки" in m for m in self._messages(resp)))
        self.assertEqual(ToolItem.objects.filter(category="drill", drill_spec__diameter_mm=Decimal("8")).count(), 0)

    def test_bulk_rejects_insert_without_machining(self):
        row = _insert_row()
        row["ins_machining_app"] = ""
        resp = self._post_arrival_bulk([row])
        self.assertTrue(any("вид обработки" in m for m in self._messages(resp)))
        self.assertEqual(ToolItem.objects.filter(category="insert", insert_spec__chipbreaker_grade="YG501").count(), 0)

    def test_bulk_rejects_empty_payload(self):
        resp = self.client.post(
            self.inv_url,
            {"action": "add_arrival_bulk", "rows_json": "[]"},
            follow=True,
        )
        self.assertTrue(any("хотя бы одну строку" in m.lower() for m in self._messages(resp)))

    def test_bulk_end_mill_row(self):
        row = {
            "category": "end_mill",
            "quantity": 2,
            "movement_date": self.today,
            "supplier_name": "MV",
            "tool_material": "hss",
            "coating_type": "none",
            "work_material": "P",
            "mill_type": "end",
            "em_diameter_mm": "12",
            "em_overall_length_mm": "100",
            "em_cutting_length_mm": "30",
            "em_flutes_count": "4",
        }
        resp = self._post_arrival_bulk([row])
        self.assertEqual(resp.status_code, 200)
        tool = ToolItem.objects.filter(category="end_mill", end_mill_spec__diameter_mm=Decimal("12")).first()
        self.assertIsNotNone(tool)
        self.assertEqual(tool.quantity, 2)
        self.assertEqual(normalize_work_material_codes(tool.work_material), "P")


class IssueOutcomePostTests(InventoryFlowClientMixin, TestCase):
    def _make_issued_drill(self, stock_qty: int = 10, issue_qty: int = 7) -> tuple[ToolItem, StockMovement]:
        tool = ToolItem.objects.create(
            category="drill",
            name="Сверло для возврата",
            tool_material="carbide",
            work_material="P",
            coating_type="none",
            quantity=stock_qty,
        )
        DrillSpec.objects.create(
            tool=tool,
            diameter_mm=Decimal("6"),
            overall_length_mm=Decimal("60"),
            cutting_length_mm=Decimal("30"),
            angle_deg=Decimal("118"),
        )
        self._post_move_stock(tool.id, "issue", issue_qty, comment="выдача в цех")
        tool.refresh_from_db()
        issue = StockMovement.objects.filter(tool=tool, movement_type="issue").latest("id")
        return tool, issue

    def test_issue_outcome_panel_loads(self):
        tool, issue = self._make_issued_drill()
        resp = self.client.get(self.inv_url + "?panel=issue_outcome")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", errors="replace")
        self.assertIn("issue-outcome", html)
        self.assertIn(f'data-issue-id="{issue.id}"', html)

    def test_return_increases_stock(self):
        tool, issue = self._make_issued_drill(stock_qty=10, issue_qty=7)
        qty_before = tool.quantity

        resp = self._post_issue_outcome(issue_id=issue.id, returned_qty=3, comment="возврат на склад")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any("сохранена" in m.lower() for m in self._messages(resp)))

        tool.refresh_from_db()
        self.assertEqual(tool.quantity, qty_before + 3)

        ret = StockMovement.objects.get(parent_issue=issue, movement_type="restock")
        self.assertEqual(ret.quantity, 3)
        self.assertIn("Возврат", ret.comment)

    def test_writeoff_does_not_increase_stock(self):
        tool, issue = self._make_issued_drill(stock_qty=10, issue_qty=5)
        qty_before = tool.quantity

        resp = self._post_issue_outcome(issue_id=issue.id, writeoff_qty=2, comment="износ")
        self.assertEqual(resp.status_code, 200)

        tool.refresh_from_db()
        self.assertEqual(tool.quantity, qty_before)

        wo = StockMovement.objects.get(parent_issue=issue, movement_type="writeoff")
        self.assertEqual(wo.quantity, 2)
        self.assertIn("Списание", wo.comment)

    def test_return_and_writeoff_together(self):
        tool, issue = self._make_issued_drill(stock_qty=12, issue_qty=8)
        qty_before = tool.quantity

        resp = self._post_issue_outcome(
            issue_id=issue.id,
            returned_qty=3,
            writeoff_qty=2,
            comment="частичный возврат",
        )
        self.assertEqual(resp.status_code, 200)

        tool.refresh_from_db()
        self.assertEqual(tool.quantity, qty_before + 3)

        processed = (
            StockMovement.objects.filter(parent_issue=issue, movement_type__in=["restock", "writeoff"])
            .aggregate(total=Sum("quantity"))
            .get("total")
            or 0
        )
        self.assertEqual(int(processed), 5)

    def test_rejects_quantity_over_remaining(self):
        _, issue = self._make_issued_drill(stock_qty=10, issue_qty=4)
        resp = self._post_issue_outcome(issue_id=issue.id, returned_qty=3, writeoff_qty=3, comment="слишком много")
        self.assertTrue(any("осталось обработать" in m for m in self._messages(resp)))
        self.assertEqual(
            StockMovement.objects.filter(parent_issue=issue).count(),
            0,
        )

    def test_requires_comment(self):
        _, issue = self._make_issued_drill()
        resp = self._post_issue_outcome(issue_id=issue.id, returned_qty=1, comment="")
        self.assertTrue(any("Комментарий обязателен" in m for m in self._messages(resp)))

    def test_requires_positive_quantities(self):
        _, issue = self._make_issued_drill()
        resp = self._post_issue_outcome(issue_id=issue.id, returned_qty=0, writeoff_qty=0, comment="пусто")
        self.assertTrue(any("количество" in m.lower() for m in self._messages(resp)))

    def test_second_outcome_respects_remaining(self):
        tool, issue = self._make_issued_drill(stock_qty=10, issue_qty=6)
        self._post_issue_outcome(issue_id=issue.id, returned_qty=2, writeoff_qty=1, comment="первая операция")
        resp = self._post_issue_outcome(issue_id=issue.id, returned_qty=4, comment="вторая — превышение")
        self.assertTrue(any("осталось обработать" in m for m in self._messages(resp)))

        tool.refresh_from_db()
        self.assertEqual(
            StockMovement.objects.filter(parent_issue=issue, movement_type="restock").aggregate(
                t=Sum("quantity")
            ).get("t"),
            2,
        )
