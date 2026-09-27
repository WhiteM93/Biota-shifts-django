from django.test import TestCase

from shifts.models import Product, ProductSetup, ProductSetupToolRow
from shifts.product_views import (
    DEFAULT_SETUP_MAGAZINE_SLOTS,
    DEFAULT_SETUP_PROBE_DIAMETER,
    DEFAULT_SETUP_PROBE_SLOT,
    DEFAULT_SETUP_PROBE_TYPE,
    create_product_with_defaults,
    seed_setup_tool_magazine,
)


class SetupMagazineSeedTests(TestCase):
    def test_create_product_seeds_full_magazine(self):
        product = create_product_with_defaults()
        setup = ProductSetup.objects.filter(product=product).first()
        self.assertIsNotNone(setup)
        numbers = list(
            ProductSetupToolRow.objects.filter(setup=setup)
            .order_by("sort_order", "id")
            .values_list("tool_number", flat=True)
        )
        self.assertEqual(numbers, list(DEFAULT_SETUP_MAGAZINE_SLOTS))
        probe = ProductSetupToolRow.objects.get(setup=setup, tool_number=DEFAULT_SETUP_PROBE_SLOT)
        self.assertEqual(probe.tool_type, DEFAULT_SETUP_PROBE_TYPE)
        self.assertEqual(probe.diameter, DEFAULT_SETUP_PROBE_DIAMETER)
        empty = ProductSetupToolRow.objects.filter(setup=setup).exclude(tool_number=DEFAULT_SETUP_PROBE_SLOT)
        self.assertTrue(empty.exists())
        self.assertEqual(empty.exclude(tool_type="").count(), 0)
        self.assertEqual(empty.exclude(diameter="").count(), 0)

    def test_seed_is_idempotent(self):
        product = Product.objects.create(name="TEST.MAGAZINE.IDEM")
        setup = ProductSetup.objects.create(product=product, name="Уст", sort_order=0)
        self.assertEqual(seed_setup_tool_magazine(setup), len(DEFAULT_SETUP_MAGAZINE_SLOTS))
        self.assertEqual(seed_setup_tool_magazine(setup), 0)
        self.assertEqual(setup.tools.count(), len(DEFAULT_SETUP_MAGAZINE_SLOTS))
