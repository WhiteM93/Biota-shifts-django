"""Подбор инструментов для правил контейнера: режущий Ø и тип фрезы."""

from decimal import Decimal

from django.test import TestCase

from shifts.models import (
    EndMillSpec,
    ToolItem,
    VisualCabinet,
    VisualContainer,
    VisualContainerItem,
)
from shifts.visual_warehouse_views import _matching_tools_for_container, _tool_qs_for_filter


class VisualWarehouseMatchingTests(TestCase):
    def setUp(self):
        cab = VisualCabinet.objects.create(name="Шкаф", shelves=2, columns=2)
        self.cont = VisualContainer.objects.create(
            cabinet=cab,
            shelf=1,
            stack=1,
            column=1,
            label="Фрезы 1-1",
            color="#3d6b8c",
        )
        # Хвостовик 6, режущий Ø 1 — должна попадать в правило Ø1–1
        self.ok = ToolItem.objects.create(
            category="end_mill",
            name="Фреза Ø1 концевая",
            main_diameter_mm=Decimal("6"),
            quantity=4,
        )
        EndMillSpec.objects.create(
            tool=self.ok,
            diameter_mm=Decimal("1"),
            mill_type="end",
            flutes_count=2,
        )
        # Режущий Ø 2 — не должна
        other = ToolItem.objects.create(
            category="end_mill",
            name="Фреза Ø2",
            main_diameter_mm=Decimal("6"),
            quantity=2,
        )
        EndMillSpec.objects.create(
            tool=other,
            diameter_mm=Decimal("2"),
            mill_type="end",
            flutes_count=2,
        )
        # Ø1, но сферическая
        self.ball = ToolItem.objects.create(
            category="end_mill",
            name="Фреза Ø1 сферическая",
            main_diameter_mm=Decimal("6"),
            quantity=3,
        )
        EndMillSpec.objects.create(
            tool=self.ball,
            diameter_mm=Decimal("1"),
            mill_type="ball",
            flutes_count=2,
        )

    def test_matches_cutting_diameter_not_shank(self):
        VisualContainerItem.objects.create(
            container=self.cont,
            title="Фрезы Ø1",
            tool_category="end_mill",
            diameter_from_mm=Decimal("1"),
            diameter_to_mm=Decimal("1"),
        )
        tools = _matching_tools_for_container(self.cont)
        ids = {t["id"] for t in tools}
        self.assertIn(self.ok.pk, ids)
        self.assertIn(self.ball.pk, ids)
        self.assertEqual(len(ids), 2)

    def test_mill_type_filter(self):
        VisualContainerItem.objects.create(
            container=self.cont,
            title="Концевые Ø1",
            tool_category="end_mill",
            mill_type="end",
            diameter_from_mm=Decimal("1"),
            diameter_to_mm=Decimal("1"),
        )
        tools = _matching_tools_for_container(self.cont)
        ids = {t["id"] for t in tools}
        self.assertEqual(ids, {self.ok.pk})

    def test_fallback_to_main_diameter_without_spec(self):
        bare = ToolItem.objects.create(
            category="end_mill",
            name="Без спеки Ø0.5",
            main_diameter_mm=Decimal("0.5"),
            quantity=1,
        )
        qs = _tool_qs_for_filter(
            category="end_mill",
            d_from=Decimal("0"),
            d_to=Decimal("1"),
        )
        self.assertTrue(qs.filter(pk=bare.pk).exists())

    def test_exclude_rule_removes_matched_tools(self):
        VisualContainerItem.objects.create(
            container=self.cont,
            title="Все Ø1",
            tool_category="end_mill",
            diameter_from_mm=Decimal("1"),
            diameter_to_mm=Decimal("1"),
            rule_kind=VisualContainerItem.RULE_INCLUDE,
        )
        VisualContainerItem.objects.create(
            container=self.cont,
            title="Без сферических",
            tool_category="end_mill",
            mill_type="ball",
            rule_kind=VisualContainerItem.RULE_EXCLUDE,
        )
        tools = _matching_tools_for_container(self.cont)
        ids = {t["id"] for t in tools}
        self.assertEqual(ids, {self.ok.pk})

    def test_exclude_specific_tool_item(self):
        VisualContainerItem.objects.create(
            container=self.cont,
            title="Все Ø1",
            tool_category="end_mill",
            diameter_from_mm=Decimal("1"),
            diameter_to_mm=Decimal("1"),
        )
        VisualContainerItem.objects.create(
            container=self.cont,
            title="Исключить одну",
            tool_item=self.ball,
            rule_kind=VisualContainerItem.RULE_EXCLUDE,
        )
        tools = _matching_tools_for_container(self.cont)
        ids = {t["id"] for t in tools}
        self.assertEqual(ids, {self.ok.pk})
