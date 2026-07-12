"""Контроль размеров в карточке наладки (по установке)."""

import json

from django.test import Client, TestCase

from shifts.models import Product, ProductInspectionDimension, ProductInspectionSession
from shifts.product_inspection import evaluate_measurement
from shifts.product_views import create_product_with_defaults


class ProductInspectionTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.product = create_product_with_defaults()
        self.setup = self.product.setups.first()

    def _inspection_url(self):
        return f"/products/{self.product.pk}/setups/{self.setup.pk}/inspection/"

    def test_evaluate_measurement_in_tolerance(self):
        self.assertTrue(evaluate_measurement("50", "", "", "±0.1", "50.05"))
        self.assertFalse(evaluate_measurement("50", "", "", "±0.1", "50.2"))

    def test_product_detail_shows_inspection_button_on_setup(self):
        res = self.client.get(f"/products/{self.product.pk}/?tab=setup-{self.setup.pk}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f"/products/{self.product.pk}/setups/{self.setup.pk}/inspection/")
        self.assertContains(res, "Замер")

    def test_inspection_page_loads_for_setup(self):
        res = self.client.get(self._inspection_url())
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="insp-page"')
        self.assertContains(res, "insp-pdf-canvas")

    def test_save_plan_and_create_session_per_setup(self):
        dims = [
            {
                "label": "Длина L",
                "nominal": "50",
                "tolerance_display": "±0.1",
                "criticality": "critical",
                "frequency": "always",
                "frequency_n": 5,
            }
        ]
        save = self.client.post(
            self._inspection_url(),
            {
                "action": "save_inspection_plan",
                "dimensions_json": json.dumps(dims),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(save.status_code, 200, save.content[:500])
        self.assertTrue(save.json().get("ok"))
        dim = ProductInspectionDimension.objects.get(product=self.product, setup=self.setup, label="Длина L")

        create = self.client.post(
            self._inspection_url(),
            {
                "action": "create_inspection_session",
                "inspector_emp_code": "2001",
                "inspector_label": "Иванов И.",
                "part_label": "001",
                "first_piece": "1",
                "measurements_json": json.dumps(
                    [{"dimension_id": dim.pk, "actual_value": "50.02", "from_drawing": True}]
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(create.status_code, 200, create.content[:500])
        body = create.json()
        self.assertTrue(body.get("ok"), body)
        session = ProductInspectionSession.objects.get(product=self.product, setup=self.setup)
        self.assertEqual(session.inspector_label, "Иванов И.")
        self.assertEqual(session.values.count(), 1)
        self.assertTrue(session.values.first().is_ok)

    def test_setups_have_isolated_sessions(self):
        second = create_product_with_defaults()
        setup2 = second.setups.first()
        ProductInspectionSession.objects.create(
            product=self.product,
            setup=self.setup,
            session_no=1,
            inspector_label="A",
            author_username="admin",
        )
        ProductInspectionSession.objects.create(
            product=second,
            setup=setup2,
            session_no=1,
            inspector_label="B",
            author_username="admin",
        )
        res = self.client.get(self._inspection_url())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(ProductInspectionSession.objects.filter(setup=self.setup).count(), 1)
        res2 = self.client.get(f"/products/{second.pk}/setups/{setup2.pk}/inspection/")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(ProductInspectionSession.objects.filter(setup=setup2).count(), 1)

    def test_create_session_requires_inspector(self):
        res = self.client.post(
            self._inspection_url(),
            {
                "action": "create_inspection_session",
                "measurements_json": "[]",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 400)

    def test_inspection_requires_valid_setup(self):
        res = self.client.get(f"/products/{self.product.pk}/setups/999999/inspection/")
        self.assertEqual(res.status_code, 404)
