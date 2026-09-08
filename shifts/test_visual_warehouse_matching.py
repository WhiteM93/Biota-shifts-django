"""Подбор инструментов для места визуального склада по warehouse_address."""

from decimal import Decimal

from django.test import TestCase

from shifts.models import (
    EndMillSpec,
    ToolItem,
    VisualCabinet,
    VisualContainer,
)
from shifts.visual_warehouse_views import _matching_tools_for_container


class VisualWarehouseMatchingTests(TestCase):
    def setUp(self):
        cab = VisualCabinet.objects.create(code="A", name="Шкаф", shelves=2, columns=2)
        self.cont = VisualContainer.objects.create(
            cabinet=cab,
            shelf=1,
            stack=1,
            column=1,
            label="Ячейка",
            color="#3d6b8c",
            address="A-02-01",
        )
        self.here = ToolItem.objects.create(
            category="end_mill",
            name="Фреза здесь",
            main_diameter_mm=Decimal("6"),
            quantity=4,
            warehouse_address="A-02-01",
        )
        EndMillSpec.objects.create(
            tool=self.here,
            diameter_mm=Decimal("1"),
            mill_type="end",
            flutes_count=2,
        )
        other = ToolItem.objects.create(
            category="end_mill",
            name="Фреза в другом месте",
            main_diameter_mm=Decimal("6"),
            quantity=2,
            warehouse_address="A-01-02",
        )
        EndMillSpec.objects.create(
            tool=other,
            diameter_mm=Decimal("2"),
            mill_type="end",
            flutes_count=2,
        )
        self.unassigned = ToolItem.objects.create(
            category="end_mill",
            name="Без адреса",
            main_diameter_mm=Decimal("6"),
            quantity=3,
            warehouse_address="",
        )
        EndMillSpec.objects.create(
            tool=self.unassigned,
            diameter_mm=Decimal("1"),
            mill_type="ball",
            flutes_count=2,
        )

    def test_matches_by_warehouse_address(self):
        tools = _matching_tools_for_container(self.cont)
        ids = {t["id"] for t in tools}
        self.assertEqual(ids, {self.here.pk})

    def test_case_insensitive_address(self):
        self.here.warehouse_address = "a-02-01"
        self.here.save(update_fields=["warehouse_address"])
        tools = _matching_tools_for_container(self.cont)
        ids = {t["id"] for t in tools}
        self.assertIn(self.here.pk, ids)

    def test_empty_when_no_address_on_container(self):
        self.cont.address = ""
        self.cont.save(update_fields=["address"])
        # suggested from cabinet still works via resolve
        tools = _matching_tools_for_container(self.cont)
        ids = {t["id"] for t in tools}
        # suggested A-02-01 (shelf 1 of 2 from top = display 02)
        self.assertIn(self.here.pk, ids)
