"""Типы мебели визуального склада: шкаф / стеллаж, bin / shelf_slot."""

import json

from django.test import Client, TestCase
from django.urls import reverse

from shifts.models import VisualCabinet, VisualContainer


class VisualWarehouseKindsTests(TestCase):
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

    def test_create_rack_and_shelf_slot_ok(self):
        res = self._post_json(
            self.cabinets_url,
            {"name": "Стеллаж А", "kind": "rack", "shelves": 3, "columns": 3},
        )
        self.assertEqual(res.status_code, 201, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body["cabinet"]["kind"], "rack")
        cab_id = body["cabinet"]["id"]

        res2 = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab_id,
                "kind": "shelf_slot",
                "shelf": 1,
                "stack": 1,
                "column": 1,
                "col_span": 1,
                "label": "Корпусной",
                "color": "#5dade2",
            },
        )
        self.assertEqual(res2.status_code, 200, res2.content[:500])
        data = res2.json()
        self.assertTrue(data.get("ok"), data)
        self.assertEqual(data["container"]["kind"], "shelf_slot")
        self.assertEqual(VisualContainer.objects.get(pk=data["container"]["id"]).kind, "shelf_slot")

    def test_shelf_slot_rejected_on_cabinet(self):
        cab = VisualCabinet.objects.create(name="Шкаф", kind=VisualCabinet.KIND_CABINET, shelves=2, columns=2)
        res = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab.pk,
                "kind": "shelf_slot",
                "shelf": 1,
                "stack": 1,
                "column": 1,
                "label": "Нельзя",
            },
        )
        self.assertEqual(res.status_code, 400, res.content[:500])
        body = res.json()
        self.assertFalse(body.get("ok", True))
        self.assertIn("стеллаж", (body.get("error") or "").lower())
        self.assertEqual(VisualContainer.objects.filter(cabinet=cab).count(), 0)

    def test_cannot_convert_rack_with_slots_to_cabinet(self):
        cab = VisualCabinet.objects.create(name="Стеллаж", kind=VisualCabinet.KIND_RACK, shelves=2, columns=2)
        VisualContainer.objects.create(
            cabinet=cab,
            kind=VisualContainer.KIND_SHELF_SLOT,
            shelf=1,
            stack=1,
            column=1,
            label="Зона",
        )
        detail = reverse("visual_warehouse_api_cabinet_detail", kwargs={"pk": cab.pk})
        res = self._patch_json(detail, {"kind": "cabinet"})
        self.assertEqual(res.status_code, 400, res.content[:500])
        cab.refresh_from_db()
        self.assertEqual(cab.kind, VisualCabinet.KIND_RACK)

    def test_create_cabinet_default_kind(self):
        res = self._post_json(self.cabinets_url, {"name": "Шкаф Б", "shelves": 4, "columns": 3})
        self.assertEqual(res.status_code, 201, res.content[:500])
        self.assertEqual(res.json()["cabinet"]["kind"], "cabinet")

    def test_create_drawer_chest_and_cells(self):
        res = self._post_json(
            self.cabinets_url,
            {"name": "Тумба инструментов", "kind": "drawer_chest", "shelves": 5, "columns": 4},
        )
        self.assertEqual(res.status_code, 201, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body["cabinet"]["kind"], "drawer_chest")
        cab_id = body["cabinet"]["id"]

        res2 = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab_id,
                "kind": "drawer_cell",
                "shelf": 1,
                "stack": 1,
                "column": 1,
                "col_span": 1,
                "label": "Фрезы Ø1",
                "color": "#5dade2",
            },
        )
        self.assertEqual(res2.status_code, 200, res2.content[:500])
        data = res2.json()
        self.assertTrue(data.get("ok"), data)
        self.assertEqual(data["container"]["kind"], "drawer_cell")

        res3 = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab_id,
                "kind": "drawer_cell",
                "shelf": 1,
                "stack": 1,
                "column": 2,
                "col_span": 2,
                "label": "Сверла",
                "color": "#82e0aa",
            },
        )
        self.assertEqual(res3.status_code, 200, res3.content[:500])
        self.assertEqual(VisualContainer.objects.filter(cabinet_id=cab_id).count(), 2)

    def test_drawer_cell_rejected_on_cabinet(self):
        cab = VisualCabinet.objects.create(name="Шкаф", kind=VisualCabinet.KIND_CABINET, shelves=2, columns=2)
        res = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab.pk,
                "kind": "drawer_cell",
                "shelf": 1,
                "stack": 1,
                "column": 1,
                "label": "Нельзя",
            },
        )
        self.assertEqual(res.status_code, 400, res.content[:500])
        body = res.json()
        self.assertFalse(body.get("ok", True))
        self.assertIn("тумб", (body.get("error") or "").lower())

    def test_cannot_convert_drawer_chest_with_cells(self):
        cab = VisualCabinet.objects.create(
            name="Тумба",
            kind=VisualCabinet.KIND_DRAWER_CHEST,
            shelves=3,
            columns=3,
        )
        VisualContainer.objects.create(
            cabinet=cab,
            kind=VisualContainer.KIND_DRAWER_CELL,
            shelf=1,
            stack=1,
            column=1,
            label="Ячейка",
        )
        detail = reverse("visual_warehouse_api_cabinet_detail", kwargs={"pk": cab.pk})
        res = self._patch_json(detail, {"kind": "cabinet"})
        self.assertEqual(res.status_code, 400, res.content[:500])
        cab.refresh_from_db()
        self.assertEqual(cab.kind, VisualCabinet.KIND_DRAWER_CHEST)

    def test_create_organizer_in_cabinet(self):
        cab = VisualCabinet.objects.create(name="Шкаф", kind=VisualCabinet.KIND_CABINET, shelves=3, columns=3)
        res = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab.pk,
                "kind": "organizer",
                "shelf": 1,
                "stack": 1,
                "column": 1,
                "col_span": 1,
                "label": "Метчики",
                "inner_tiers": 3,
                "inner_columns": 2,
                "color": "#5dade2",
            },
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body["container"]["kind"], "organizer")
        self.assertEqual(body["container"]["inner_tiers"], 3)
        self.assertEqual(body["container"]["inner_columns"], 2)
        self.assertEqual(len(body["container"]["children"]), 6)
        org = VisualContainer.objects.get(pk=body["container"]["id"])
        self.assertEqual(org.children.count(), 6)
        labels = set(org.children.values_list("label", flat=True))
        self.assertIn("Ярус 1 СК", labels)
        self.assertIn("Ярус 1 ГЛ", labels)
        # дочерние не на верхнем уровне шкафа
        tops = [c for c in body["cabinet"]["containers"] if not c.get("parent_id")]
        self.assertEqual(len(tops), 1)
        self.assertEqual(tops[0]["kind"], "organizer")
