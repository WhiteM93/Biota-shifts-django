"""Сохранение карточки изделия: параметры (каскад) и наладка."""

from django.test import Client, TestCase

from shifts.models import Product, ProductSetup
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

    def test_inline_update_setup_persists_card_specs(self):
        self._post_inline()
        self.product.refresh_from_db()
        self.assertEqual(self.product.card_product_type, "made")
        self.assertEqual(self.product.card_workpiece_type, "laser")
        self.assertEqual(self.product.card_material, "Ст3")

    def test_inline_update_product_name_does_not_500(self):
        res = self._post_inline({"product_name": "Наладка после переименования"})
        self.assertEqual(res.status_code, 200, res.content[:500])
        self.assertTrue(res.json().get("ok"), res.json())
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Наладка после переименования")

    def test_toggle_setup_in_work_reorders_list(self):
        second = ProductSetup.objects.create(
            product=self.product,
            name="Установка 2",
            sort_order=1,
        )
        res = self.client.post(
            f"/products/{self.product.pk}/",
            {
                "action": "inline_toggle_setup_in_work",
                "setup_id": str(second.pk),
                "in_work": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertTrue(body.get("in_work"))
        order = [row["pk"] for row in body.get("setup_order") or []]
        self.assertEqual(order[0], second.pk)
        second.refresh_from_db()
        self.assertTrue(second.in_work)

    def test_product_detail_renders_in_work_setups_first(self):
        second = ProductSetup.objects.create(
            product=self.product,
            name="Установка 2",
            sort_order=1,
            in_work=True,
        )
        res = self.client.get(f"/products/{self.product.pk}/")
        self.assertEqual(res.status_code, 200, res.content[:500])
        html = res.content.decode()
        first_setup_opt = html.split('option value="setup-')[1].split('"')[0]
        self.assertEqual(first_setup_opt, str(second.pk))

    def test_products_list_puts_in_work_products_first(self):
        other = create_product_with_defaults()
        ProductSetup.objects.filter(product=other).update(in_work=True)
        self.product.name = "ZZZ без работы"
        self.product.save(update_fields=["name"])
        other.name = "AAA в работе"
        other.save(update_fields=["name"])
        res = self.client.get("/products/")
        self.assertEqual(res.status_code, 200, res.content[:500])
        html = res.content.decode()
        pos_other = html.find("AAA в работе")
        pos_self = html.find("ZZZ без работы")
        self.assertNotEqual(pos_other, -1)
        self.assertNotEqual(pos_self, -1)
        self.assertLess(pos_other, pos_self)

    def test_empty_product_type_returns_clear_error(self):
        res = self.client.post(
            f"/products/{self.product.pk}/",
            {
                "action": "inline_save_product_specs",
                "product_type": "",
                "workpiece_type": "",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 400)
        err = res.json().get("error", "").lower()
        self.assertIn("тип изделия", err)

    def test_inline_save_product_specs_action(self):
        res = self.client.post(
            f"/products/{self.product.pk}/",
            {
                "action": "inline_save_product_specs",
                "product_type": "made",
                "workpiece_type": "preparatory",
                "material": "40Х",
                "workpiece_size": "50x50",
                "workpiece_type_enum": "rod",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.product.refresh_from_db()
        self.assertEqual(self.product.card_workpiece_type, "preparatory")
        self.assertEqual(self.product.card_workpiece_type_enum, "rod")
        self.assertEqual(self.product.card_material, "40Х")

    def test_inline_preparatory_specs_persist_after_reload(self):
        res = self._post_inline(
            {
                "workpiece_type": "preparatory",
                "material": "40Х",
                "plan_material": "40Х",
                "workpiece_size": "120x80x20",
                "workpiece_type_enum": "plate",
            }
        )
        self.assertEqual(res.status_code, 200, res.content[:500])
        self.assertTrue(res.json().get("ok"), res.json())
        self.product.refresh_from_db()
        self.assertEqual(self.product.card_workpiece_type, "preparatory")
        self.assertEqual(self.product.card_workpiece_size, "120x80x20")
        self.assertEqual(self.product.card_workpiece_type_enum, "plate")
        self.assertEqual(self.product.card_material, "40Х")
        self.setup.refresh_from_db()
        self.assertEqual(self.setup.material, "40Х")
