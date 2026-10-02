"""Справочник адресов склада и подсказка по наименованиям."""

import json

from django.test import Client, TestCase
from django.urls import reverse

from shifts.models import ToolItem, VisualCabinet, VisualContainer, WarehouseAddress
from shifts.visual_warehouse_address import (
    address_container_titles,
    build_address_hint_rows,
    ensure_cabinet_layout,
    ensure_warehouse_address,
    set_warehouse_address_label,
)


class WarehouseAddressRegistryTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.label_url = reverse("inventory_api_warehouse_address_label")

    def _post_json(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_ensure_creates_address_row(self):
        row = ensure_warehouse_address("z-01-02")
        self.assertIsNotNone(row)
        self.assertEqual(row.address, "Z-01-02")
        self.assertEqual(row.label, "")
        again = ensure_warehouse_address("Z-01-02", label="Метчики")
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(again.label, "Метчики")

    def test_hint_row_editable_without_container(self):
        ToolItem.objects.create(
            category="drill",
            name="Сверло 5",
            quantity=2,
            warehouse_address="D-02-03",
        )
        ensure_warehouse_address("D-02-03")
        rows = build_address_hint_rows(include_stock=True)
        hit = next(r for r in rows if r["address"] == "D-02-03")
        self.assertEqual(hit["container_id"], 0)
        self.assertEqual(hit["editable_label"], "")
        self.assertNotIn("Нет ячейки", hit["name"])

        set_warehouse_address_label("D-02-03", "Сверла 5")
        rows2 = build_address_hint_rows(include_stock=True)
        hit2 = next(r for r in rows2 if r["address"] == "D-02-03")
        self.assertEqual(hit2["editable_label"], "Сверла 5")
        self.assertEqual(hit2["name"], "Сверла 5")

    def test_label_api_by_address_without_container(self):
        ensure_warehouse_address("E-01-01")
        res = self._post_json(self.label_url, {"address": "E-01-01", "label": "Фрезы"})
        self.assertEqual(res.status_code, 200, res.content[:400])
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["label"], "Фрезы")
        self.assertEqual(data["container_id"], 0)
        self.assertEqual(WarehouseAddress.objects.get(address="E-01-01").label, "Фрезы")

    def test_label_syncs_to_existing_container(self):
        cab = VisualCabinet.objects.create(name="Шкаф E", kind="rack", shelves=2, columns=2, code="E")
        cont = VisualContainer.objects.create(
            cabinet=cab,
            kind=VisualContainer.KIND_SHELF_SLOT,
            shelf=2,
            stack=1,
            column=1,
            address="E-01-01",
            label="E-01-01",
        )
        res = self._post_json(self.label_url, {"address": "E-01-01", "label": "Головки"})
        self.assertEqual(res.status_code, 200, res.content[:400])
        cont.refresh_from_db()
        # На этикетке остаётся адрес; наименование — в справочнике
        self.assertEqual(cont.label, "E-01-01")
        self.assertEqual(WarehouseAddress.objects.get(address="E-01-01").label, "Головки")

    def test_rack_hover_title_not_shelf_slot_kind(self):
        cab = VisualCabinet.objects.create(
            name="Стеллаж R",
            kind=VisualCabinet.KIND_RACK,
            shelves=2,
            columns=2,
            code="R",
        )
        ensure_cabinet_layout(cab, sections=1, shelves_per_section=2, columns=2)
        level = cab.sections.get().levels.get(index=2)  # низ → display 02
        VisualContainer.objects.create(
            cabinet=cab,
            level=level,
            kind=VisualContainer.KIND_SHELF_SLOT,
            shelf=2,
            stack=1,
            column=1,
            address="R-02-01",
            label="R-02-01",
            notes="Коробка метчиков",
        )
        titles = address_container_titles()
        tip = titles.get("R-02-01") or ""
        self.assertNotEqual(tip, "На полке")
        self.assertNotEqual(tip.upper(), "R-02-01")
        self.assertIn("полка", tip.lower())
        self.assertIn("Коробка метчиков", tip)

        set_warehouse_address_label("R-02-01", "Метчики M6")
        titles2 = address_container_titles()
        self.assertEqual(titles2.get("R-02-01"), "Метчики M6")

    def test_ensure_places_from_addresses_creates_only_known(self):
        from shifts.visual_warehouse_address import (
            ensure_cabinet_layout,
            ensure_places_from_warehouse_addresses,
            place_to_stack_column,
        )

        cab = VisualCabinet.objects.create(
            name="Стеллаж F",
            kind=VisualCabinet.KIND_RACK,
            shelves=2,
            columns=2,
            code="F",
        )
        ensure_cabinet_layout(cab, sections=1, shelves_per_section=2, columns=2)
        level = cab.sections.get().levels.get(index=2)  # низ → display 02
        level.rows = 2
        level.save(update_fields=["rows"])

        ToolItem.objects.create(
            category="drill",
            name="Сверло",
            quantity=1,
            warehouse_address="F-02-01",
        )
        ensure_warehouse_address("F-02-03", label="Коробка 3")
        # F-02-02 нет — слот должен остаться пустым

        n = ensure_places_from_warehouse_addresses(cab)
        self.assertEqual(n, 2)
        addrs = set(
            VisualContainer.objects.filter(cabinet=cab).values_list("address", flat=True)
        )
        self.assertEqual(addrs, {"F-02-01", "F-02-03"})
        self.assertFalse(
            VisualContainer.objects.filter(cabinet=cab, address="F-02-02").exists()
        )

        st, col, _ = place_to_stack_column(3, columns=2, rows=2)
        cont3 = VisualContainer.objects.get(cabinet=cab, address="F-02-03")
        self.assertEqual(cont3.stack, st)
        self.assertEqual(cont3.column, col)
        self.assertEqual(cont3.level_id, level.id)

        # повторный вызов не дублирует
        self.assertEqual(ensure_places_from_warehouse_addresses(cab), 0)

    def test_place_to_stack_column_two_rows(self):
        from shifts.visual_warehouse_address import place_num_from_position, place_to_stack_column

        self.assertEqual(place_to_stack_column(1, columns=2, rows=2), (2, 1, 2))
        self.assertEqual(place_to_stack_column(2, columns=2, rows=2), (2, 2, 2))
        self.assertEqual(place_to_stack_column(3, columns=2, rows=2), (1, 1, 2))
        self.assertEqual(place_to_stack_column(4, columns=2, rows=2), (1, 2, 2))
        self.assertEqual(place_num_from_position(stack=2, column=1, columns=2, rows=2), 1)
        self.assertEqual(place_num_from_position(stack=1, column=2, columns=2, rows=2), 4)
