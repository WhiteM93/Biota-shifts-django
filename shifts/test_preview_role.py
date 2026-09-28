from django.test import Client, TestCase

from shifts.auth_utils import PREVIEW_ROLE_SESSION_KEY
from shifts.models import ProductSetup
from shifts.product_views import create_product_with_defaults


class AdminPreviewRoleTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.product = create_product_with_defaults()
        self.setup = ProductSetup.objects.filter(product=self.product).order_by("id").first()

    def test_admin_can_switch_to_executor_preview(self):
        res = self.client.post(
            "/accounts/preview-role/",
            {"role": "executor", "next": f"/products/{self.product.pk}/"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.client.session.get(PREVIEW_ROLE_SESSION_KEY), "executor")
        page = self.client.get(f"/products/{self.product.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-biota-can-edit="0"')
        self.assertContains(page, "nav-role-preview")
        self.assertContains(page, 'id="setup-export-tools-btn"')
        self.assertContains(page, 'id="setup-load-to-machine-btn"')
        self.assertContains(page, 'id="setup-export-specs-btn"')
        self.assertContains(page, 'id="setup-export-photos-btn"')
        self.assertNotContains(page, 'id="setup-inline-edit-btn"')

    def test_executor_preview_blocks_inline_save(self):
        self.client.post("/accounts/preview-role/", {"role": "executor", "next": "/"})
        res = self.client.post(
            f"/products/{self.product.pk}/",
            {
                "action": "inline_update_setup",
                "setup_id": str(self.setup.pk),
                "name": "Не должно сохраниться",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 403)
        self.setup.refresh_from_db()
        self.assertNotEqual(self.setup.name, "Не должно сохраниться")

    def test_executor_preview_cannot_toggle_setup_status(self):
        self.client.post("/accounts/preview-role/", {"role": "executor", "next": "/"})
        res = self.client.post(
            f"/products/{self.product.pk}/",
            {
                "action": "inline_toggle_setup_in_work",
                "setup_id": str(self.setup.pk),
                "status": "in_work",
                "value": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res.status_code, 403)
        self.setup.refresh_from_db()
        self.assertFalse(self.setup.in_work)
        page = self.client.get(f"/products/{self.product.pk}/")
        self.assertContains(page, "is-readonly")

    def test_switch_back_to_manager_restores_edit(self):
        self.client.post("/accounts/preview-role/", {"role": "executor", "next": "/"})
        self.client.post("/accounts/preview-role/", {"role": "manager", "next": "/"})
        page = self.client.get(f"/products/{self.product.pk}/")
        self.assertContains(page, 'data-biota-can-edit="1"')

    def test_non_admin_cannot_switch_role(self):
        session = self.client.session
        session["biota_username"] = "not-admin"
        session.save()
        res = self.client.post("/accounts/preview-role/", {"role": "executor", "next": "/"})
        self.assertEqual(res.status_code, 302)
        self.assertNotEqual(self.client.session.get(PREVIEW_ROLE_SESSION_KEY), "executor")
        page = self.client.get("/accounts/login/")
        self.assertNotContains(page, "nav-role-preview")
