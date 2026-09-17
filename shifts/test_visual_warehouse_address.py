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

        # shelf top=3 (bottom) → display 01; единственный контейнер на полке → место 01 → B-01-01
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
        self.assertEqual(cont["place_label"], "01")
        self.assertEqual(cont["address"], "B-01-01")
        self.assertEqual(cont["suggested_address"], "B-01-01")

        obj = VisualContainer.objects.get(pk=cont["id"])
        self.assertEqual(obj.address, "B-01-01")

        # change furniture code → auto address refreshes
        detail = reverse("visual_warehouse_api_cabinet_detail", args=[cab_id])
        res3 = self._patch_json(detail, {"code": "A"})
        self.assertEqual(res3.status_code, 200, res3.content[:400])
        self.assertEqual(res3.json()["cabinet"]["code"], "A")
        obj.refresh_from_db()
        self.assertEqual(obj.address, "A-01-01")

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

    def test_stale_auto_address_follows_shelf_place(self):
        """В UI полка/место из геометрии; устаревший A-03-02 не должен перебивать A-02-01."""
        from shifts.visual_warehouse_address import (
            build_location_catalog,
            repair_container_address_if_stale,
            resolve_container_address,
        )

        cab = VisualCabinet.objects.create(
            name="Фрезерный",
            kind=VisualCabinet.KIND_CABINET,
            shelves=4,
            columns=4,
            code="A",
        )
        # shelf_top1=3 → display 02, column=1 → 01 → A-02-01
        cont = VisualContainer.objects.create(
            cabinet=cab,
            kind=VisualContainer.KIND_BIN,
            shelf=3,
            column=1,
            label="Метчик М2 глухой",
            address="A-03-02",
        )
        self.assertEqual(shelf_display_num(shelves=4, shelf_top1=3), "02")
        self.assertEqual(suggested_address(cab, shelf=3, column=1), "A-02-01")
        self.assertEqual(resolve_container_address(cont), "A-02-01")
        self.assertEqual(repair_container_address_if_stale(cont), "A-02-01")
        cont.refresh_from_db()
        self.assertEqual(cont.address, "A-02-01")

        places = [
            p
            for p in build_location_catalog()["places"]
            if p["container_id"] == cont.id
        ]
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["shelf_label"], "02")
        self.assertEqual(places[0]["place_label"], "01")
        self.assertEqual(places[0]["address"], "A-02-01")

    def test_stacked_containers_sequential_place_numbers(self):
        """На одной полке стопки: номера мест сверху вниз, слева направо."""
        from shifts.visual_warehouse_address import (
            place_index_on_shelf,
            place_labels_by_container_id,
            suggested_address_for_container,
        )

        cab = VisualCabinet.objects.create(
            name="Фрезерный",
            kind=VisualCabinet.KIND_CABINET,
            shelves=5,
            columns=5,
            code="A",
        )
        # shelf top=1 (верхняя, display 05)
        top_l = VisualContainer.objects.create(
            cabinet=cab, kind=VisualContainer.KIND_BIN, shelf=1, stack=2, column=1, label="T1", address="A-05-01"
        )
        top_m = VisualContainer.objects.create(
            cabinet=cab, kind=VisualContainer.KIND_BIN, shelf=1, stack=2, column=2, label="T2", address="A-05-02"
        )
        bot_l = VisualContainer.objects.create(
            cabinet=cab, kind=VisualContainer.KIND_BIN, shelf=1, stack=1, column=1, label="B1", address="A-05-01"
        )
        bot_m = VisualContainer.objects.create(
            cabinet=cab, kind=VisualContainer.KIND_BIN, shelf=1, stack=1, column=2, label="B2", address="A-05-02"
        )
        peers = [top_l, top_m, bot_l, bot_m]
        self.assertEqual(place_index_on_shelf(top_l, peers=peers), 1)
        self.assertEqual(place_index_on_shelf(top_m, peers=peers), 2)
        self.assertEqual(place_index_on_shelf(bot_l, peers=peers), 3)
        self.assertEqual(place_index_on_shelf(bot_m, peers=peers), 4)
        labels = place_labels_by_container_id(peers)
        self.assertEqual(labels[top_l.id], "01")
        self.assertEqual(labels[top_m.id], "02")
        self.assertEqual(labels[bot_l.id], "03")
        self.assertEqual(labels[bot_m.id], "04")
        self.assertEqual(suggested_address_for_container(bot_l, cab=cab, peers=peers), "A-05-03")

    def test_move_container_to_another_cabinet(self):
        cab_a = VisualCabinet.objects.create(
            name="Стеллаж A",
            kind=VisualCabinet.KIND_RACK,
            shelves=4,
            columns=3,
            code="A",
        )
        cab_b = VisualCabinet.objects.create(
            name="Стеллаж B",
            kind=VisualCabinet.KIND_RACK,
            shelves=4,
            columns=3,
            code="B",
        )
        cont = VisualContainer.objects.create(
            cabinet=cab_a,
            kind=VisualContainer.KIND_SHELF_SLOT,
            shelf=2,
            column=1,
            label="Коробка",
            address="A-03-01",
        )
        res = self._post_json(
            self.upsert_url,
            {
                "id": cont.pk,
                "cabinet_id": cab_b.pk,
                "kind": "shelf_slot",
                "shelf": 2,
                "stack": 1,
                "column": 1,
                "label": "Коробка",
                "color": "#5dade2",
                "address": "A-03-01",
            },
        )
        self.assertEqual(res.status_code, 200, res.content[:400])
        data = res.json()["container"]
        self.assertEqual(data["cabinet_id"], cab_b.pk)
        cont.refresh_from_db()
        self.assertEqual(cont.cabinet_id, cab_b.pk)
        self.assertEqual(cont.address, "B-03-01")
