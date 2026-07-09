"""Тесты вкладки «Анализ» склада."""

from decimal import Decimal

from django.test import TestCase

from shifts.inventory_analysis import aggregate_by_group, group_total_qty, watch_status
from shifts.models import EndMillSpec, InventoryWatchTemplate, ToolItem


class InventoryAnalysisTests(TestCase):
    def _end_mill(self, name: str, diameter: str, qty: int) -> ToolItem:
        tool = ToolItem.objects.create(
            category="end_mill",
            name=name,
            quantity=qty,
        )
        EndMillSpec.objects.create(tool=tool, diameter_mm=Decimal(diameter), mill_type="end", flutes_count=2)
        return tool

    def test_aggregate_by_diameter(self):
        self._end_mill("F1", "2", 3)
        self._end_mill("F2", "2", 5)
        self._end_mill("F3", "3", 10)
        rows = aggregate_by_group("end_mill", "diameter_mm")
        by_val = {r["group_value"]: r["total_qty"] for r in rows}
        self.assertEqual(by_val.get("2"), 8)
        self.assertEqual(by_val.get("3"), 10)

    def test_group_total_qty(self):
        self._end_mill("F1", "2", 4)
        self._end_mill("F2", "2", 1)
        self.assertEqual(group_total_qty("end_mill", "diameter_mm", "2"), 5)

    def test_watch_status(self):
        self.assertEqual(watch_status(10, 5), "ok")
        self.assertEqual(watch_status(2, 5), "warn")
        self.assertEqual(watch_status(0, 5), "critical")

    def test_watch_template_model(self):
        InventoryWatchTemplate.objects.create(
            username="admin",
            name="Фрезы D2",
            category="end_mill",
            group_field="diameter_mm",
            group_value="2",
            min_qty=5,
        )
        self.assertEqual(InventoryWatchTemplate.objects.count(), 1)
