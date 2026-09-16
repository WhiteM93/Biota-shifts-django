from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from shifts.models import (
    CenterDrillSpec,
    DrillSpec,
    EndMillSpec,
    Product,
    ProductSetup,
    ProductSetupToolRow,
    ToolItem,
)
from shifts.setup_stock_match import match_setup_tools, parse_diameter_spec


class ParseDiameterSpecTests(SimpleTestCase):
    def test_plain_and_prefix(self):
        self.assertEqual(parse_diameter_spec("50").diameter, Decimal("50"))
        self.assertEqual(parse_diameter_spec("Ø50.0").diameter, Decimal("50.0"))
        self.assertEqual(parse_diameter_spec("ф6").diameter, Decimal("6"))

    def test_radius(self):
        d = parse_diameter_spec("3R1.5")
        self.assertEqual(d.diameter, Decimal("3"))
        self.assertEqual(d.corner_radius, Decimal("1.5"))

    def test_range(self):
        d = parse_diameter_spec("2.7-2.8")
        self.assertEqual(d.diameter, Decimal("2.7"))
        self.assertEqual(d.diameter_max, Decimal("2.8"))

    def test_metric_size(self):
        self.assertEqual(parse_diameter_spec("M5").size_label, "M5")
        self.assertEqual(parse_diameter_spec("М2,5").size_label, "M2.5")


class SetupStockMatchTests(TestCase):
    def test_match_end_mill_and_drill_range(self):
        product = Product.objects.create(name="TEST.SETUP.STOCK")
        setup = ProductSetup.objects.create(product=product, name="Уст 1")
        ProductSetupToolRow.objects.create(
            setup=setup, sort_order=1, tool_number="T09", tool_type="Фреза чистовая", diameter="16"
        )
        ProductSetupToolRow.objects.create(
            setup=setup, sort_order=2, tool_number="T10", tool_type="Сверло", diameter="2.7-2.8"
        )
        ProductSetupToolRow.objects.create(
            setup=setup, sort_order=3, tool_number="T02", tool_type="Центровка", diameter="6"
        )

        mill = ToolItem.objects.create(category="end_mill", name="Фреза 16", quantity=3, warehouse_address="A-01-01")
        EndMillSpec.objects.create(tool=mill, mill_type="end", diameter_mm=Decimal("16"))

        drill_ok = ToolItem.objects.create(category="drill", name="Св 2.75", quantity=5, warehouse_address="B-02-01")
        DrillSpec.objects.create(tool=drill_ok, diameter_mm=Decimal("2.75"))
        drill_out = ToolItem.objects.create(category="drill", name="Св 3", quantity=1)
        DrillSpec.objects.create(tool=drill_out, diameter_mm=Decimal("3"))

        center = ToolItem.objects.create(category="center_drill", name="Центр 6", quantity=2, warehouse_address="C-01-01")
        CenterDrillSpec.objects.create(tool=center, diameter_mm=Decimal("6"))

        rows = match_setup_tools(setup.tools.all().order_by("sort_order", "id"))
        self.assertEqual(len(rows), 3)
        by_num = {r.tool_number: r for r in rows}

        self.assertEqual(by_num["T09"].status, "ok")
        self.assertEqual(by_num["T09"].total_qty, 3)
        self.assertEqual(by_num["T09"].candidates[0].id, mill.pk)
        self.assertIn("tool_id=", by_num["T09"].candidates[0].inventory_url)

        self.assertEqual(by_num["T10"].status, "ok")
        self.assertEqual(by_num["T10"].total_qty, 5)
        self.assertEqual([c.id for c in by_num["T10"].candidates], [drill_ok.pk])

        self.assertEqual(by_num["T02"].status, "ok")
        self.assertEqual(by_num["T02"].candidates[0].address, "C-01-01")

    def test_stock_page_url_resolves(self):
        product = Product.objects.create(name="TEST.SETUP.STOCK.URL")
        setup = ProductSetup.objects.create(product=product, name="Уст")
        url = reverse("product_setup_stock", kwargs={"pk": product.pk, "setup_pk": setup.pk})
        self.assertTrue(url.endswith(f"/products/{product.pk}/setups/{setup.pk}/stock/"))
