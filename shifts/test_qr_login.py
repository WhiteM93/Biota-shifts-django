"""Вход по QR: компьютер ждёт, телефон подтверждает."""

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from shifts.qr_login import approve_qr_login, create_qr_login_token, get_qr_login


@override_settings(
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "qr-test-def"},
        "ratelimit": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "qr-test-rl"},
        "qrlogin": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "qr-test-qr"},
    }
)
class QrLoginTests(TestCase):
    def test_login_page_shows_qr(self):
        res = self.client.get(reverse("login"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "js-auth-qr")
        self.assertContains(res, "auth_qr_login.js")

    def test_phone_confirm_then_desktop_claim(self):
        desktop = Client()
        desktop.get(reverse("login"))

        rf = RequestFactory()
        req = rf.get("/accounts/login/")
        req.session = desktop.session
        qr = create_qr_login_token(req, next_url="/home/")
        token = qr["token"]
        desktop.session.save()

        data = get_qr_login(token)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "pending")

        phone = Client()
        session = phone.session
        session["biota_username"] = "admin"
        session.save()

        res = phone.post(reverse("qr_login_confirm", kwargs={"token": token}), {"action": "confirm"})
        self.assertEqual(res.status_code, 200, res.content[:400])
        self.assertContains(res, "Готово")

        data2 = get_qr_login(token)
        self.assertEqual(data2["status"], "approved")
        self.assertEqual(data2["username"], "admin")

        poll = desktop.get(reverse("qr_login_status") + f"?token={token}")
        self.assertEqual(poll.status_code, 200)
        body = poll.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("status"), "ready")
        self.assertTrue(body.get("redirect"))
        self.assertEqual(desktop.session.get("biota_username"), "admin")

    def test_wrong_desktop_session_cannot_claim(self):
        desktop_a = Client()
        desktop_a.get(reverse("login"))
        rf = RequestFactory()
        req = rf.get("/accounts/login/")
        req.session = desktop_a.session
        token = create_qr_login_token(req)["token"]
        desktop_a.session.save()
        ok, _ = approve_qr_login(token, "admin")
        self.assertTrue(ok)

        desktop_b = Client()
        desktop_b.get(reverse("login"))
        poll = desktop_b.get(reverse("qr_login_status") + f"?token={token}")
        body = poll.json()
        self.assertEqual(body.get("status"), "error")
        self.assertFalse(desktop_b.session.get("biota_username"))
