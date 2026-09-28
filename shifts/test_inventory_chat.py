from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from shifts.inventory_chat import _extract_tool_call, forced_tool_call
from shifts.inventory_chat_tools import (
    build_warehouse_context,
    issues_by_employee,
    recent_movements,
    run_tool,
    search_issues,
    tool_stock_search,
    top_issued_tools,
    top_stock_tools,
)
from shifts.models import DrillSpec, InsertSpec, StockMovement, TapSpec, ToolItem


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


class ForcedToolCallTests(SimpleTestCase):
    def test_usage_question_uses_issued_not_stock(self):
        call = forced_tool_call("какие позиции чаще всего используются?")
        self.assertEqual(call["tool"], "top_issued_tools")

    def test_followup_conduct_uses_history(self):
        hist = [
            {"role": "user", "text": "какие позиции чаще всего используются?"},
            {"role": "assistant", "text": "По снимку часто сверла…"},
        ]
        call = forced_tool_call("проводи", hist)
        self.assertEqual(call["tool"], "top_issued_tools")

    def test_stock_top_question(self):
        call = forced_tool_call("какой позиции на складе больше всего по остатку?")
        self.assertEqual(call["tool"], "top_stock_tools")

    def test_who_took_drill_uses_search_issues(self):
        call = forced_tool_call("кто брал сверла 2.5")
        self.assertEqual(call["tool"], "search_issues")
        self.assertIn("сверл", (call["args"].get("query") or "").lower())
        self.assertNotIn("метчик", (call["args"].get("query") or "").lower())

    def test_overdue_question(self):
        self.assertEqual(forced_tool_call("какие выдачи просрочены?")["tool"], "overdue_open_issues")

    def test_hold_question_extracts_employee(self):
        call = forced_tool_call("что у Иванова на руках")
        self.assertEqual(call["tool"], "open_issues")
        self.assertIn("Иванов", call["args"].get("employee") or "")
        self.assertFalse(call["args"].get("query"))

    def test_hold_generic_has_no_junk_query(self):
        call = forced_tool_call("Кто держит инструмент на руках и не вернул?")
        self.assertEqual(call["tool"], "open_issues")
        self.assertFalse(call["args"].get("query"))

    def test_locate_question(self):
        call = forced_tool_call("где лежит сверло 2.5")
        self.assertEqual(call["tool"], "locate_tool")
        self.assertIn("сверл", (call["args"].get("query") or "").lower())

    def test_watch_question(self):
        self.assertEqual(
            forced_tool_call("что в контроле остатков ниже минимума?")["tool"],
            "watch_alerts",
        )

    def test_no_address_question(self):
        self.assertEqual(
            forced_tool_call("какие позиции без адреса ячейки?")["tool"],
            "tools_without_address",
        )

    def test_dead_stock_question(self):
        self.assertEqual(forced_tool_call("какой инструмент давно не двигался?")["tool"], "dead_stock")

    def test_summary_on_analysis_uses_overdue(self):
        call = forced_tool_call(
            "сводка",
            page_context={"page": "inventory", "panel": "analysis"},
        )
        self.assertEqual(call["tool"], "overdue_open_issues")


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

    def test_search_issues_tap_m3_through(self):
        tap = ToolItem.objects.create(category="tap", name="Метчик M3 сквозной", quantity=5)
        TapSpec.objects.create(
            tool=tap,
            size_label="M3",
            hole_type="through",
            tap_type="cutting",
        )
        StockMovement.objects.create(
            movement_type="issue",
            tool=tap,
            quantity=1,
            employee_name="Чумак Р.",
            movement_date=timezone.localdate(),
        )
        data = search_issues(query="метчик M3 сквозной")
        self.assertGreaterEqual(data["count"], 1)
        self.assertIn("Чумак", data["rows"][0]["employee"])
        data_blind = search_issues(query="метчик M3 глухой")
        self.assertEqual(data_blind["count"], 0)

    def test_search_issues_drill_25_does_not_match_tap(self):
        tap = ToolItem.objects.create(category="tap", name="Метчик M5 режущий", quantity=3)
        TapSpec.objects.create(
            tool=tap,
            size_label="M5",
            hole_type="through",
            tap_type="cutting",
        )
        tap_m25 = ToolItem.objects.create(category="tap", name="Метчик M2.5", quantity=2)
        TapSpec.objects.create(
            tool=tap_m25,
            size_label="M2.5",
            hole_type="through",
            tap_type="cutting",
        )
        drill = ToolItem.objects.create(category="drill", name="Сверло 2.5", quantity=4)
        DrillSpec.objects.create(tool=drill, diameter_mm="2.50")
        StockMovement.objects.create(
            movement_type="issue",
            tool=tap,
            quantity=1,
            employee_name="Сидоров",
            movement_date=timezone.localdate(),
        )
        StockMovement.objects.create(
            movement_type="issue",
            tool=tap_m25,
            quantity=1,
            employee_name="Петров",
            movement_date=timezone.localdate(),
        )
        StockMovement.objects.create(
            movement_type="issue",
            tool=drill,
            quantity=1,
            employee_name="Иванов сверло",
            movement_date=timezone.localdate(),
        )
        data = search_issues(query="сверла 2.5")
        self.assertGreaterEqual(data["count"], 1)
        joined = " ".join(r["tool"] + r["employee"] for r in data["rows"])
        self.assertIn("Иванов сверло", joined)
        self.assertNotIn("Сидоров", joined)
        self.assertNotIn("Петров", joined)
        self.assertNotIn("метчик", joined.lower())

        StockMovement.objects.filter(tool=drill).delete()
        empty = search_issues(query="сверла 2.5")
        self.assertEqual(empty["count"], 0)
        self.assertIn("сверл", (empty.get("hint") or "").lower())

    def test_warehouse_context_contains_stock_and_issues(self):
        text = build_warehouse_context()
        self.assertIn("ОСТАТКИ НА СКЛАДЕ", text)
        self.assertIn("ПОСЛЕДНИЕ ВЫДАЧИ", text)
        self.assertIn("APKT1135", text)
        self.assertIn("Иванов", text)
        self.assertIn("КОНТРОЛЬ", text)


class InventoryChatOpsToolsTests(TestCase):
    def setUp(self):
        import os

        os.environ["BIOTA_INVENTORY_NOTIFY"] = "0"
        self.today = timezone.localdate()
        self.drill = ToolItem.objects.create(
            category="drill",
            name="Сверло 2.5",
            quantity=4,
            warehouse_address="A-01-02",
        )
        DrillSpec.objects.create(tool=self.drill, diameter_mm="2.50")
        self.tap = ToolItem.objects.create(
            category="tap",
            name="Метчик M5 режущий",
            quantity=3,
            warehouse_address="B-02-01",
        )
        TapSpec.objects.create(tool=self.tap, size_label="M5", hole_type="through", tap_type="cutting")
        self.orphan = ToolItem.objects.create(
            category="insert",
            name="ORPHAN INSERT",
            quantity=7,
            warehouse_address="",
        )

    def test_overdue_ignores_fresh_and_closed(self):
        from datetime import timedelta

        from shifts.inventory_chat_tools import open_issues, overdue_open_issues

        old = StockMovement.objects.create(
            movement_type="issue",
            tool=self.drill,
            quantity=5,
            employee_name="Долгов Д.",
            movement_date=self.today - timedelta(days=20),
        )
        StockMovement.objects.create(
            movement_type="restock",
            tool=self.drill,
            parent_issue=old,
            quantity=2,
            employee_name="Долгов Д.",
            movement_date=self.today,
        )
        StockMovement.objects.create(
            movement_type="issue",
            tool=self.tap,
            quantity=1,
            employee_name="Свежий С.",
            movement_date=self.today,
        )
        closed = StockMovement.objects.create(
            movement_type="issue",
            tool=self.tap,
            quantity=1,
            employee_name="Закрыт З.",
            movement_date=self.today - timedelta(days=40),
        )
        StockMovement.objects.create(
            movement_type="writeoff",
            tool=self.tap,
            parent_issue=closed,
            quantity=1,
            employee_name="Закрыт З.",
            movement_date=self.today,
        )
        overdue = overdue_open_issues(min_days=14)
        people = " ".join(r["employee"] for r in overdue["rows"])
        self.assertIn("Долгов", people)
        self.assertNotIn("Свежий", people)
        self.assertNotIn("Закрыт", people)
        self.assertEqual(overdue["rows"][0]["remaining"], 3)

        held = open_issues(employee="Долгов")
        self.assertEqual(held["count"], 1)
        self.assertEqual(held["rows"][0]["remaining"], 3)

    def test_locate_drill_not_tap(self):
        from shifts.inventory_chat_tools import locate_tool, tools_without_address

        found = locate_tool(query="сверло 2.5")
        self.assertGreaterEqual(found["count"], 1)
        blob = " ".join(r["tool"] + r["address"] for r in found["rows"])
        self.assertIn("A-01-02", blob)
        self.assertNotIn("метчик", blob.lower())
        by_addr = locate_tool(query="A-01-02")
        self.assertGreaterEqual(by_addr["count"], 1)
        none_addr = tools_without_address()
        self.assertTrue(any("ORPHAN" in r["tool"] for r in none_addr["rows"]))
        self.assertFalse(any("A-01-02" in (r.get("address") or "") for r in none_addr["rows"]))

    def test_watch_alerts_are_personal(self):
        from shifts.inventory_chat_tools import watch_alerts
        from shifts.models import EndMillSpec, InventoryWatchTemplate

        mill = ToolItem.objects.create(category="end_mill", name="F D2", quantity=1)
        EndMillSpec.objects.create(tool=mill, diameter_mm="2", mill_type="end", flutes_count=2)
        InventoryWatchTemplate.objects.create(
            username="storeman",
            name="Фрезы D2",
            category="end_mill",
            group_field="diameter_mm",
            group_value="2",
            min_qty=5,
        )
        mine = watch_alerts(username="storeman", only_problems=True)
        self.assertGreaterEqual(mine["count"], 1)
        self.assertEqual(mine["rows"][0]["status"], "warn")
        other = watch_alerts(username="other-user", only_problems=True)
        self.assertEqual(other["count"], 0)

    def test_forced_overdue_skips_first_llm(self):
        from datetime import timedelta
        from unittest.mock import patch

        from shifts.inventory_chat import ask_inventory_chat

        StockMovement.objects.create(
            movement_type="issue",
            tool=self.drill,
            quantity=1,
            employee_name="Долгов Д.",
            movement_date=self.today - timedelta(days=21),
        )
        with (
            patch("shifts.inventory_chat.yandex_gpt_configured", return_value=True),
            patch("shifts.inventory_chat.complete", return_value="Просрочено у Долгова.") as complete_mock,
        ):
            result = ask_inventory_chat("какие выдачи просрочены?")
        self.assertTrue(result["ok"])
        self.assertEqual(result["used_tools"], ["overdue_open_issues"])
        self.assertEqual(complete_mock.call_count, 1)
        self.assertIn("Долгов", result["reply"])