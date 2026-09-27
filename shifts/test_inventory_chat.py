from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from shifts.inventory_chat import _extract_tool_call
from shifts.inventory_chat_tools import (
    issues_by_employee,
    recent_movements,
    run_tool,
    tool_stock_search,
    top_issued_tools,
    top_stock_tools,
)
from shifts.models import InsertSpec, StockMovement, ToolItem


class ExtractToolCallTests(SimpleTestCase):
    def test_plain_json(self):
        call = _extract_tool_call('{"tool":"top_issued_tools","args":{"limit":5}}')
        self.assertEqual(call["tool"], "top_issued_tools")
        self.assertEqual(call["args"]["limit"], 5)

    def test_fenced_json(self):
        text = 'Вот вызов:\n```json\n{"tool":"tool_stock_search","args":{"query":"APKT"}}\n```'
        call = _extract_tool_call(text)
        self.assertEqual(call["tool"], "tool_stock_search")
        self.assertEqual(call["args"]["query"], "APKT")

    def test_text_is_not_tool(self):
        self.assertIsNone(_extract_tool_call("На складе 3 позиции APKT."))


class InventoryChatToolsTests(TestCase):
    def setUp(self):
        import os

        os.environ["BIOTA_INVENTORY_NOTIFY"] = "0"
        self.tool = ToolItem.objects.create(
            category="insert",
            name="TEST INSERT",
            quantity=10,
        )
        InsertSpec.objects.create(
            tool=self.tool,
            item_name="APKT1135",
            brand="YG",
        )
        today = timezone.localdate()
        StockMovement.objects.create(
            movement_type="issue",
            tool=self.tool,
            quantity=2,
            employee_name="Иванов Иван",
            movement_date=today,
        )

    def test_tool_stock_search(self):
        data = tool_stock_search(query="APKT")
        self.assertGreaterEqual(data["count"], 1)
        self.assertTrue(any("APKT" in r["tool"] for r in data["rows"]))

    def test_issues_by_employee(self):
        data = issues_by_employee(name="Иванов")
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(data["rows"][0]["qty"], 2)

    def test_top_and_recent(self):
        top = top_issued_tools(limit=5)
        self.assertTrue(top["rows"])
        recent = recent_movements(movement_type="issue", limit=5)
        self.assertTrue(recent["rows"])

    def test_top_stock_tools(self):
        data = top_stock_tools(limit=5)
        self.assertEqual(data["metric"], "текущий остаток на складе")
        self.assertTrue(data["rows"])
        self.assertEqual(data["rows"][0]["qty"], 10)

    def test_run_tool_unknown(self):
        self.assertIn("error", run_tool("nope", {}))
