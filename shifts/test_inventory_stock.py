"""Тесты склада: мультивыбор материала обработки, пластинки, приход, отображение."""
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from shifts.insert_constants import normalize_insert_machining_apps
from shifts.inventory_views import _arrival_bulk_row_validation_errors, _insert_spec_fields_from_mapping
from shifts.models import (
    DrillSpec,
    EndMillSpec,
    InsertSpec,
    ToolItem,
    normalize_work_material_codes,
    work_material_display_text,
)


class WorkMaterialNormalizeTests(TestCase):
    def test_single_code(self):
        self.assertEqual(normalize_work_material_codes("p"), "P")

    def test_multi_sorted(self):
        self.assertEqual(normalize_work_material_codes("K,P,M"), "P,M,K")

    def test_invalid_skipped(self):
        self.assertEqual(normalize_work_material_codes("P,X,M"), "P,M")

    def test_display_text(self):
        self.assertIn("P", work_material_display_text("P,M"))

    def test_codes_list_on_tool(self):
        tool = ToolItem.objects.create(category="drill", name="t", work_material="P,M,K", quantity=1)
        self.assertEqual(tool.work_material_codes_list(), ["P", "M", "K"])


class InsertMachiningAppsTests(TestCase):
    def test_multi_apps(self):
        self.assertEqual(normalize_insert_machining_apps("3,1,2"), "1,2,3")

    def test_insert_spec_save(self):
        tool = ToolItem.objects.create(
            category="insert",
            name="ins",
            tool_material="carbide",
            work_material="P,M",
            quantity=2,
        )
        spec = InsertSpec(
            tool=tool,
            insert_shape="C",
            relief_angle="N",
            tolerance_class="M",
            mounting_chip="G",
            cutting_edge_length_code="12",
            thickness_code="04",
            nose_radius_code="08",
            machining_application="1,3",
        )
        spec.save()
        spec.refresh_from_db()
        self.assertEqual(spec.machining_application, "1,3")


class ArrivalBulkValidationTests(TestCase):
    def test_insert_requires_wm_and_machining(self):
        row = {
            "category": "insert",
            "ins_shape": "C",
            "ins_edge_code": "12",
            "ins_thickness_code": "04",
            "ins_nose_code": "08",
            "ins_machining_app": "",
            "work_material": "",
        }
        errs = _arrival_bulk_row_validation_errors(row, 1)
        self.assertTrue(any("материала обработки" in e for e in errs))
        self.assertTrue(any("вид обработки" in e for e in errs))

    def test_end_mill_requires_wm(self):
        row = {"category": "end_mill", "em_diameter_mm": "6", "work_material": ""}
        errs = _arrival_bulk_row_validation_errors(row, 1)
        self.assertTrue(any("материала обработки" in e for e in errs))

    def test_insert_spec_mapping_multi_machining(self):
        fields = _insert_spec_fields_from_mapping({"ins_machining_app": "2,1", "ins_shape": "C"})
        self.assertEqual(fields["machining_application"], "1,2")


class InventoryViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()

    def _create_minimal_per_category(self):
        d = Decimal("6")
        em = ToolItem.objects.create(
            category="end_mill",
            name="Фреза тест",
            tool_material="carbide",
            work_material="P,M",
            quantity=5,
        )
        EndMillSpec.objects.create(
            tool=em,
            mill_type="end",
            diameter_mm=d,
            overall_length_mm=Decimal("50"),
            cutting_length_mm=Decimal("20"),
            flutes_count=4,
        )
        ins_tool = ToolItem.objects.create(
            category="insert",
            name="Пластина тест",
            tool_material="carbide",
            work_material="P,K",
            quantity=3,
        )
        InsertSpec.objects.create(
            tool=ins_tool,
            insert_shape="C",
            relief_angle="N",
            tolerance_class="M",
            mounting_chip="G",
            cutting_edge_length_code="12",
            thickness_code="04",
            nose_radius_code="08",
            machining_application="1,2",
            chipbreaker_grade="YG501",
        )

    def test_stock_page_loads(self):
        self._create_minimal_per_category()
        for cat in ("end_mill", "insert", "drill"):
            url = reverse("inventory") + f"?panel=stock&category={cat}"
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, msg=f"category={cat}")
            content = resp.content.decode("utf-8", errors="replace")
            if cat == "end_mill":
                self.assertIn("wm-square", content)
                self.assertIn("wm-p", content)
            if cat == "insert":
                self.assertIn("wm-square", content)

    def test_arrival_page_has_inv_options(self):
        resp = self.client.get(reverse("inventory") + "?panel=arrival")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("insert_chipbreaker_grades", resp.content.decode("utf-8", errors="replace"))
        self.assertIn("work_material_types", resp.content.decode("utf-8", errors="replace"))

    def test_filter_work_material_multi_match(self):
        d = Decimal("8")
        t1 = ToolItem.objects.create(category="drill", name="d1", work_material="P,M", quantity=1)
        DrillSpec.objects.create(
            tool=t1,
            diameter_mm=d,
            overall_length_mm=Decimal("80"),
            cutting_length_mm=Decimal("40"),
            angle_deg=Decimal("118"),
        )
        t2 = ToolItem.objects.create(category="drill", name="d2", work_material="K", quantity=1)
        DrillSpec.objects.create(
            tool=t2,
            diameter_mm=d,
            overall_length_mm=Decimal("80"),
            cutting_length_mm=Decimal("40"),
            angle_deg=Decimal("118"),
        )
        resp = self.client.get(reverse("inventory") + "?panel=stock&category=drill&work_material=P")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8", errors="replace")
        self.assertIn(f'value="{t1.id}"', content)
        self.assertNotIn(f'value="{t2.id}"', content)
        self.assertIn("wm-p", content)
