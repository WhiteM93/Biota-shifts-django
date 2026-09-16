"""Остаточные проверки логики допуска (страница «Замер» снята)."""

from django.test import Client, TestCase

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

    def test_evaluate_measurement_in_tolerance(self):
        self.assertTrue(evaluate_measurement("50", "", "", "±0.1", "50.05"))
        self.assertFalse(evaluate_measurement("50", "", "", "±0.1", "50.2"))

    def test_product_detail_has_no_inspection_entry(self):
        res = self.client.get(f"/products/{self.product.pk}/?tab=setup-{self.setup.pk}")
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "/inspection/")
        self.assertNotContains(res, ">Замер<")

    def test_inspection_url_removed(self):
        res = self.client.get(f"/products/{self.product.pk}/setups/{self.setup.pk}/inspection/")
        self.assertEqual(res.status_code, 404)
