"""Справочник адресов склада и подсказка по наименованиям."""

import json

from django.test import Client, TestCase
from django.urls import reverse

from shifts.models import ToolItem, VisualCabinet, VisualContainer, WarehouseAddress
from shifts.visual_warehouse_address import (
    build_address_hint_rows,
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
