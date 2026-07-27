"""Инвентаризация контейнеров визуального склада."""

import json

from django.test import Client, TestCase
from django.urls import reverse

from shifts.models import (
    InventoryStockEvent,
    StockMovement,
    ToolItem,
    VisualCabinet,
    VisualContainer,
    VisualContainerAudit,
    VisualContainerItem,
)


class VisualWarehouseAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()

        self.cab = VisualCabinet.objects.create(name="Шкаф тест", shelves=3, columns=3)
        self.cont = VisualContainer.objects.create(
            cabinet=self.cab,
            shelf=1,
            stack=1,
            column=1,
            label="Фрезы концевые 0-1",
            color="#3d6b8c",
        )
        VisualContainerItem.objects.create(
            container=self.cont,
            title="Фрезы 0-1",
            tool_category="end_mill",
            diameter_from_mm="0",
            diameter_to_mm="1",
        )
        self.tool_a = ToolItem.objects.create(
            category="end_mill",
            name="Фреза A Ø0.5",
            main_diameter_mm="0.5",
            quantity=10,
        )
        self.tool_b = ToolItem.objects.create(
            category="end_mill",
            name="Фреза B Ø0.8",
            main_diameter_mm="0.8",
            quantity=5,
        )
        # вне диапазона — не должна попасть в ящик
        ToolItem.objects.create(
            category="end_mill",
            name="Фреза C Ø2",
            main_diameter_mm="2",
            quantity=7,
        )
        self.audits_url = reverse("visual_warehouse_api_container_audits", kwargs={"pk": self.cont.pk})

    def _post_audit(self, lines, notes=""):
        return self.client.post(
            self.audits_url,
            data=json.dumps({"notes": notes, "lines": lines}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_audit_no_changes(self):
        res = self._post_audit(
            [
                {"tool_id": self.tool_a.pk, "counted_qty": 10, "note": ""},
                {"tool_id": self.tool_b.pk, "counted_qty": 5, "note": ""},
            ],
            notes="всё ок",
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body["audit"]["changes_count"], 0)
        self.cont.refresh_from_db()
        self.assertIsNotNone(self.cont.last_audited_at)
        self.assertEqual(self.cont.last_audited_by, "admin")
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(VisualContainerAudit.objects.filter(container=self.cont).count(), 1)
        ev = InventoryStockEvent.objects.filter(event_type=InventoryStockEvent.EVENT_CONTAINER_AUDIT).first()
        self.assertIsNotNone(ev)
        self.assertIn("без расхождений", ev.summary)

    def test_audit_shortage_writeoff(self):
        res = self._post_audit(
            [
                {"tool_id": self.tool_a.pk, "counted_qty": 7, "note": "не хватает 3"},
                {"tool_id": self.tool_b.pk, "counted_qty": 5, "note": ""},
            ]
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body["audit"]["changes_count"], 1)
        self.tool_a.refresh_from_db()
        self.assertEqual(self.tool_a.quantity, 7)
        mv = StockMovement.objects.get(tool=self.tool_a)
        self.assertEqual(mv.movement_type, "writeoff")
        self.assertEqual(mv.quantity, 3)
        self.assertIn("Инвентаризация", mv.comment)
        self.assertIn("не хватает 3", mv.comment)

    def test_audit_surplus_restock(self):
        res = self._post_audit(
            [
                {"tool_id": self.tool_a.pk, "counted_qty": 10, "note": ""},
                {"tool_id": self.tool_b.pk, "counted_qty": 8, "note": "нашли ещё"},
            ]
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body["audit"]["changes_count"], 1)
        self.tool_b.refresh_from_db()
        self.assertEqual(self.tool_b.quantity, 8)
        mv = StockMovement.objects.get(tool=self.tool_b)
        self.assertEqual(mv.movement_type, "restock")
        self.assertEqual(mv.quantity, 3)

    def test_audits_history_get(self):
        self._post_audit(
            [
                {"tool_id": self.tool_a.pk, "counted_qty": 9, "note": "минус 1"},
                {"tool_id": self.tool_b.pk, "counted_qty": 5, "note": ""},
            ]
        )
        res = self.client.get(self.audits_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(len(body["audits"]), 1)
        audit = body["audits"][0]
        self.assertEqual(audit["changes_count"], 1)
        self.assertEqual(len(audit["lines"]), 2)
        adjusted = [ln for ln in audit["lines"] if ln["status"] == "adjusted"]
        self.assertEqual(len(adjusted), 1)
        self.assertEqual(adjusted[0]["expected_qty"], 10)
        self.assertEqual(adjusted[0]["counted_qty"], 9)
        self.assertEqual(body["container"]["last_audited_by"], "admin")
        self.assertTrue(body["container"]["last_audited_at"])

    def test_audit_add_new_tool(self):
        res = self.client.post(
            self.audits_url,
            data=json.dumps(
                {
                    "notes": "нашли ещё одну",
                    "lines": [
                        {"tool_id": self.tool_a.pk, "counted_qty": 10, "note": ""},
                        {"tool_id": self.tool_b.pk, "counted_qty": 5, "note": ""},
                    ],
                    "new_tools": [
                        {
                            "category": "end_mill",
                            "mill_type": "end",
                            "diameter_mm": "0.6",
                            "quantity": 3,
                            "flutes_count": 2,
                            "note": "лежит в ящике",
                        }
                    ],
                }
            ),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertGreaterEqual(body["audit"]["changes_count"], 1)
        new_tool = ToolItem.objects.filter(name__icontains="0.6").order_by("-id").first()
        self.assertIsNotNone(new_tool)
        self.assertEqual(new_tool.quantity, 3)
        self.assertEqual(new_tool.category, "end_mill")
        self.assertTrue(
            VisualContainerItem.objects.filter(container=self.cont, tool_item=new_tool).exists()
        )
        mv = StockMovement.objects.get(tool=new_tool)
        self.assertEqual(mv.movement_type, "restock")
        self.assertEqual(mv.quantity, 3)
        stock_ids = {t["id"] for t in body["container"]["stock_tools"]}
        self.assertIn(new_tool.pk, stock_ids)

    def test_audit_only_new_tool_empty_box(self):
        empty = VisualContainer.objects.create(
            cabinet=self.cab,
            shelf=2,
            stack=1,
            column=1,
            label="Пустой",
            color="#333333",
        )
        url = reverse("visual_warehouse_api_container_audits", kwargs={"pk": empty.pk})
        res = self.client.post(
            url,
            data=json.dumps(
                {
                    "lines": [],
                    "new_tools": [
                        {
                            "category": "drill",
                            "diameter_mm": "5",
                            "quantity": 2,
                            "name": "Сверло тестовое Ø5",
                        }
                    ],
                }
            ),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        tool = ToolItem.objects.get(name="Сверло тестовое Ø5")
        self.assertEqual(tool.quantity, 2)
        self.assertEqual(tool.category, "drill")
