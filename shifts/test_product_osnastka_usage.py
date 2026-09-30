"""Связь наладки с оснасткой в боковой панели карточки."""

from django.test import Client, TestCase

from shifts.models import Product, ProductOsnastkaUsage
from shifts.product_views import create_product_with_defaults


class ProductOsnastkaUsageTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.naladka = create_product_with_defaults()
        self.osnastka = create_product_with_defaults(catalog_section=Product.CATALOG_OSNASTKA)

    def test_product_detail_shows_osnastka_block_for_naladka(self):
        res = self.client.get(f"/products/{self.naladka.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="product-osnastka-block"')
        self.assertContains(res, 'id="product-osnastka-search"')

    def test_osnastka_detail_hides_osnastka_block(self):
        res = self.client.get(f"/osnastki/{self.osnastka.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, 'id="product-osnastka-block"')

    def test_add_and_remove_osnastka_link(self):
        add = self.client.post(
            f"/products/{self.naladka.pk}/",
            {"action": "product_add_osnastka", "osnastka_id": str(self.osnastka.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(add.status_code, 200, add.content[:500])
        body = add.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(len(body.get("osnastka_links") or []), 1)
        link = ProductOsnastkaUsage.objects.get(product=self.naladka, osnastka=self.osnastka)

        dup = self.client.post(
            f"/products/{self.naladka.pk}/",
            {"action": "product_add_osnastka", "osnastka_id": str(self.osnastka.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(dup.status_code, 400)

        remove = self.client.post(
            f"/products/{self.naladka.pk}/",
            {"action": "product_remove_osnastka", "link_id": str(link.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(remove.status_code, 200, remove.content[:500])
        self.assertTrue(remove.json().get("ok"))
        self.assertFalse(ProductOsnastkaUsage.objects.filter(pk=link.pk).exists())

    def test_cannot_add_naladka_as_osnastka(self):
        other = create_product_with_defaults()
        res = self.client.post(
            f"/products/{self.naladka.pk}/",
            {"action": "product_add_osnastka", "osnastka_id": str(other.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 404)

    def test_change_catalog_section_naladka_to_osnastka(self):
        ProductOsnastkaUsage.objects.create(product=self.naladka, osnastka=self.osnastka)
        res = self.client.post(
            f"/products/{self.naladka.pk}/",
            {"action": "change_product_catalog_section", "catalog_section": "osnastka"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 200, res.content[:400])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body.get("catalog_section"), "osnastka")
        self.assertIn("/osnastki/", body.get("redirect_url") or "")
        self.naladka.refresh_from_db()
        self.assertTrue(self.naladka.is_osnastka)
        self.assertFalse(
            ProductOsnastkaUsage.objects.filter(product=self.naladka).exists()
        )

    def test_change_catalog_section_osnastka_to_naladka(self):
        ProductOsnastkaUsage.objects.create(product=self.naladka, osnastka=self.osnastka)
        res = self.client.post(
            f"/osnastki/{self.osnastka.pk}/",
            {"action": "change_product_catalog_section", "catalog_section": "naladki"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 200, res.content[:400])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertIn("/products/", body.get("redirect_url") or "")
        self.osnastka.refresh_from_db()
        self.assertFalse(self.osnastka.is_osnastka)
        self.assertFalse(
            ProductOsnastkaUsage.objects.filter(osnastka=self.osnastka).exists()
        )
