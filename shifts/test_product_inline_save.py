"""Сохранение наладки при выходе из быстрого редактирования (inline_update_setup + план)."""

from django.test import Client, TestCase

from shifts.models import PlannedProduct, ProductSetup
from shifts.product_views import create_product_with_defaults


class ProductInlineSaveTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.product = create_product_with_defaults()
        self.setup = ProductSetup.objects.filter(product=self.product).order_by("sort_order", "id").first()
        self.assertIsNotNone(self.setup)

    def _post_inline(self, extra=None):
        data = {
            "action": "inline_update_setup",
            "setup_id": str(self.setup.pk),
            "name": "Тест установка",
            "workpiece": "заготовка",
            "size": "10",
            "material": "Сталь",
            "binding_x": "1",
            "binding_y": "2",
            "binding_z": "3",
            "gcode_system": "G54",
            "binding_extra_blocks_json": "[]",
            "setup_notes": "",
            "rows_json": "[]",
            "sync_plan_from_inline": "1",
            "product_type": "made",
            "plan_product_type": "made",
            "workpiece_type": "laser",
            "laser_thickness": "2",
            "laser_sheet_thickness_mm": "2",
            "material": "Ст3",
            "plan_material": "Ст3",
        }
        if extra:
            data.update(extra)
        return self.client.post(
            f"/products/{self.product.pk}/",
            data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_inline_update_setup_returns_json_ok(self):
        res = self._post_inline()
        self.assertEqual(res.status_code, 200, res.content[:500])
        self.assertEqual(res["Content-Type"], "application/json")
        body = res.json()
        self.assertTrue(body.get("ok"), body)

    def test_inline_update_setup_creates_plan_link(self):
        self._post_inline()
        pp = PlannedProduct.objects.filter(naladki_product_id=self.product.pk).first()
        self.assertIsNotNone(pp)
        self.assertEqual(pp.workpiece_type, "laser")

    def test_inline_update_product_name_does_not_500(self):
        """Смена названия наладки синхронизирует план (select_for_update только в atomic)."""
        res = self._post_inline({"product_name": "Наладка после переименования"})
        self.assertEqual(res.status_code, 200, res.content[:500])
        self.assertTrue(res.json().get("ok"), res.json())
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Наладка после переименования")
