"""Коды мебели визуального склада и адрес B-01-02."""

import json

from django.test import Client, TestCase
from django.urls import reverse

from shifts.models import VisualCabinet, VisualContainer
from shifts.visual_warehouse_address import suggested_address, shelf_display_num


class VisualWarehouseFurnitureCodeAddressTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.cabinets_url = reverse("visual_warehouse_api_cabinets")
        self.upsert_url = reverse("visual_warehouse_api_container_upsert")

    def _post_json(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def _patch_json(self, url, payload):
        return self.client.generic(
            "PATCH",
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_shelf_display_bottom_up(self):
        self.assertEqual(shelf_display_num(shelves=5, shelf_top1=1), "05")
        self.assertEqual(shelf_display_num(shelves=5, shelf_top1=5), "01")

    def test_create_cabinet_with_code_and_address(self):
        res = self._post_json(
            self.cabinets_url,
            {
                "name": "Стеллаж B1",
                "kind": "rack",
                "shelves": 3,
                "columns": 2,
                "code": "B",
            },
        )
        self.assertEqual(res.status_code, 201, res.content[:400])
        cab = res.json()["cabinet"]
        self.assertEqual(cab["code"], "B")
        cab_id = cab["id"]

        # shelf top=3 (bottom) → display 01, column 2 → 02 → B-01-02
        res2 = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab_id,
                "kind": "shelf_slot",
                "shelf": 3,
                "stack": 1,
                "column": 2,
                "label": "Коробка",
                "color": "#5dade2",
            },
        )
        self.assertEqual(res2.status_code, 200, res2.content[:400])
        cont = res2.json()["container"]
        self.assertEqual(cont["shelf_label"], "01")
        self.assertEqual(cont["place_label"], "02")
        self.assertEqual(cont["address"], "B-01-02")
        self.assertEqual(cont["suggested_address"], "B-01-02")

        obj = VisualContainer.objects.get(pk=cont["id"])
        self.assertEqual(obj.address, "B-01-02")

        # change furniture code → auto address refreshes
        detail = reverse("visual_warehouse_api_cabinet_detail", args=[cab_id])
        res3 = self._patch_json(detail, {"code": "A"})
        self.assertEqual(res3.status_code, 200, res3.content[:400])
        self.assertEqual(res3.json()["cabinet"]["code"], "A")
        obj.refresh_from_db()
        self.assertEqual(obj.address, "A-01-02")

    def test_custom_address_kept_on_code_change(self):
        cab = VisualCabinet.objects.create(
            name="Шкаф",
            kind=VisualCabinet.KIND_CABINET,
            shelves=2,
            columns=2,
            code="A",
        )
        cont = VisualContainer.objects.create(
            cabinet=cab,
            kind=VisualContainer.KIND_BIN,
            shelf=1,
            column=1,
            label="X",
            address="CUSTOM-99",
        )
        detail = reverse("visual_warehouse_api_cabinet_detail", args=[cab.pk])
        res = self._patch_json(detail, {"code": "B"})
        self.assertEqual(res.status_code, 200, res.content[:400])
        cont.refresh_from_db()
        self.assertEqual(cont.address, "CUSTOM-99")
        cab.refresh_from_db()
        self.assertEqual(suggested_address(cab, shelf=1, column=1), "B-02-01")
