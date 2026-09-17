"""Гибкий шкаф: секции, уровни shelf/drawer, адреса 3/4 части."""

import json

from django.test import Client, TestCase
from django.urls import reverse

from shifts.models import (
    VisualCabinet,
    VisualCabinetLevel,
    VisualCabinetSection,
    VisualContainer,
)
from shifts.visual_warehouse_address import (
    apply_cabinet_sections_layout,
    ensure_cabinet_layout,
    suggested_address,
    suggested_address_for_container,
)


class FlexibleCabinetLayoutTests(TestCase):
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

    def test_create_cabinet_seeds_one_section(self):
        res = self._post_json(
            self.cabinets_url,
            {
                "name": "Шкаф A",
                "kind": "cabinet",
                "shelves": 3,
                "columns": 2,
                "code": "A",
            },
        )
        self.assertEqual(res.status_code, 201, res.content[:500])
        cab = res.json()["cabinet"]
        self.assertEqual(cab["sections_count"], 1)
        self.assertEqual(len(cab["sections"]), 1)
        self.assertEqual(len(cab["sections"][0]["levels"]), 3)
        self.assertTrue(all(lv["kind"] == "shelf" for lv in cab["sections"][0]["levels"]))
        obj = VisualCabinet.objects.get(pk=cab["id"])
        self.assertEqual(obj.sections.count(), 1)
        self.assertEqual(obj.sections.first().levels.count(), 3)

    def test_single_section_address_three_parts(self):
        cab = VisualCabinet.objects.create(
            name="Шкаф",
            kind=VisualCabinet.KIND_CABINET,
            shelves=3,
            columns=2,
            code="A",
        )
        ensure_cabinet_layout(cab, sections=1, shelves_per_section=3, columns=2)
        level = cab.sections.first().levels.get(index=3)  # bottom → display 01
        cont = VisualContainer.objects.create(
            cabinet=cab,
            level=level,
            kind=VisualContainer.KIND_BIN,
            shelf=3,
            stack=1,
            column=1,
            label="Короб",
            color="#e74c3c",
        )
        addr = suggested_address_for_container(cont, cab=cab)
        self.assertEqual(addr, "A-01-01")

    def test_multi_section_address_four_parts(self):
        cab = VisualCabinet.objects.create(
            name="Шкаф 2с",
            kind=VisualCabinet.KIND_CABINET,
            shelves=2,
            columns=2,
            code="A",
        )
        _, err = apply_cabinet_sections_layout(
            cab,
            [
                {
                    "levels": [
                        {"kind": "shelf", "columns": 2},
                        {"kind": "drawer", "columns": 3},
                    ]
                },
                {
                    "levels": [
                        {"kind": "shelf", "columns": 2},
                        {"kind": "shelf", "columns": 2},
                    ]
                },
            ],
            default_columns=2,
        )
        self.assertIsNone(err)
        sec2 = cab.sections.get(index=2)
        level = sec2.levels.get(index=2)  # bottom of sec2 → display 01
        cont = VisualContainer.objects.create(
            cabinet=cab,
            level=level,
            kind=VisualContainer.KIND_BIN,
            shelf=2,
            stack=1,
            column=1,
            label="Справа низ",
            color="#e74c3c",
        )
        addr = suggested_address_for_container(cont, cab=cab)
        self.assertEqual(addr, "A-2-01-01")
        # legacy helper without section stays 3-part
        self.assertEqual(
            suggested_address(cab, shelf=2, column=1, place_num=1),
            "A-01-01",
        )

    def test_upsert_layout_and_container_by_level_id(self):
        res = self._post_json(
            self.cabinets_url,
            {
                "name": "Гибкий",
                "kind": "cabinet",
                "code": "G",
                "sections": [
                    {
                        "levels": [
                            {"kind": "shelf", "columns": 2},
                            {"kind": "drawer", "columns": 3},
                        ]
                    },
                    {
                        "levels": [
                            {"kind": "shelf", "columns": 2},
                        ]
                    },
                ],
            },
        )
        self.assertEqual(res.status_code, 201, res.content[:600])
        cab = res.json()["cabinet"]
        self.assertEqual(len(cab["sections"]), 2)
        self.assertEqual(cab["sections"][0]["levels"][1]["kind"], "drawer")
        drawer_level_id = cab["sections"][0]["levels"][1]["id"]

        res2 = self._post_json(
            self.upsert_url,
            {
                "cabinet_id": cab["id"],
                "level_id": drawer_level_id,
                "kind": "drawer_cell",
                "column": 2,
                "stack": 1,
                "label": "Ячейка",
                "color": "#3498db",
            },
        )
        self.assertEqual(res2.status_code, 200, res2.content[:500])
        cont = res2.json()["container"]
        self.assertEqual(cont["level_id"], drawer_level_id)
        self.assertEqual(cont["level_kind"], "drawer")
        self.assertEqual(cont["section_index"], 1)
        self.assertEqual(cont["address"], "G-1-01-01")
        obj = VisualContainer.objects.get(pk=cont["id"])
        self.assertEqual(obj.level_id, drawer_level_id)
        self.assertEqual(obj.shelf, 2)

        # serialize sections → levels → containers
        detail = reverse("visual_warehouse_api_cabinet_detail", args=[cab["id"]])
        res3 = self.client.get(detail, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res3.status_code, 200)
        sections = res3.json()["cabinet"]["sections"]
        drawer_conts = sections[0]["levels"][1]["containers"]
        self.assertEqual(len(drawer_conts), 1)
        self.assertEqual(drawer_conts[0]["id"], cont["id"])

    def test_patch_sections_layout(self):
        res = self._post_json(
            self.cabinets_url,
            {
                "name": "Патч",
                "kind": "cabinet",
                "code": "P",
                "shelves": 2,
                "columns": 2,
            },
        )
        self.assertEqual(res.status_code, 201, res.content[:400])
        cab_id = res.json()["cabinet"]["id"]
        sec_id = res.json()["cabinet"]["sections"][0]["id"]
        lvl_ids = [lv["id"] for lv in res.json()["cabinet"]["sections"][0]["levels"]]

        detail = reverse("visual_warehouse_api_cabinet_detail", args=[cab_id])
        res2 = self._patch_json(
            detail,
            {
                "sections": [
                    {
                        "id": sec_id,
                        "levels": [
                            {"id": lvl_ids[0], "kind": "shelf", "columns": 3},
                            {"id": lvl_ids[1], "kind": "drawer", "columns": 4},
                            {"kind": "shelf", "columns": 2},
                        ],
                    }
                ]
            },
        )
        self.assertEqual(res2.status_code, 200, res2.content[:500])
        levels = res2.json()["cabinet"]["sections"][0]["levels"]
        self.assertEqual(len(levels), 3)
        self.assertEqual(levels[1]["kind"], "drawer")
        self.assertEqual(levels[1]["columns"], 4)
        self.assertEqual(VisualCabinetLevel.objects.filter(section_id=sec_id).count(), 3)
