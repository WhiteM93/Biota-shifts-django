"""Антибот регистрации: invite, honeypot, тайминг, disposable, purge."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from django.core.cache import caches
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from biota_shifts import auth as biota_auth
from shifts.register_guard import (
    DISPOSABLE_FAIL,
    GENERIC_FAIL,
    INVITE_FAIL,
    SESSION_ISSUED_AT,
    check_bot_traps,
    invite_code_ok,
    is_disposable_email,
    registration_is_open,
    validate_register_post,
)
from shifts.rate_limit import registration_rate_limits


@override_settings(BIOTA_REGISTER_INVITE_CODE="secret-invite")
class RegisterGuardUnitTests(SimpleTestCase):
    def test_registration_open_when_invite_set(self):
        self.assertTrue(registration_is_open())
        self.assertTrue(invite_code_ok("secret-invite"))
        self.assertFalse(invite_code_ok("wrong"))

    @override_settings(BIOTA_REGISTER_INVITE_CODE="")
    def test_registration_closed_without_invite(self):
        self.assertFalse(registration_is_open())
        self.assertFalse(invite_code_ok(""))

    def test_disposable_email(self):
        self.assertTrue(is_disposable_email("a@mailinator.com"))
        self.assertTrue(is_disposable_email("x@sub.yopmail.com"))
        self.assertFalse(is_disposable_email("user@company.ru"))

    @override_settings(BIOTA_DISPOSABLE_EMAIL_DOMAINS="evil.test,spam.local")
    def test_extra_disposable_domains(self):
        self.assertTrue(is_disposable_email("a@evil.test"))
        self.assertTrue(is_disposable_email("b@spam.local"))

    def test_honeypot_blocks(self):
        rf = RequestFactory()
        req = rf.post("/accounts/register/", {"website": "http://spam"})
        req.session = {SESSION_ISSUED_AT: time.time() - 10}
        msg, reason = check_bot_traps(req)
        self.assertEqual(msg, GENERIC_FAIL)
        self.assertEqual(reason, "honeypot")

    def test_too_fast_blocks(self):
        rf = RequestFactory()
        req = rf.post("/accounts/register/", {})
        req.session = {SESSION_ISSUED_AT: time.time()}
        msg, reason = check_bot_traps(req)
        self.assertEqual(msg, GENERIC_FAIL)
        self.assertEqual(reason, "timing")

    def test_valid_timing_ok(self):
        rf = RequestFactory()
        req = rf.post("/accounts/register/", {})
        req.session = {SESSION_ISSUED_AT: time.time() - 5}
        self.assertEqual(check_bot_traps(req), (None, None))

    def test_validate_register_post_invite_and_disposable(self):
        rf = RequestFactory()
        req = rf.post("/accounts/register/", {})
        req.session = {SESSION_ISSUED_AT: time.time() - 5}
        self.assertEqual(
            validate_register_post(req, invite_posted="wrong", email="a@company.ru"),
            INVITE_FAIL,
        )
        self.assertEqual(
            validate_register_post(req, invite_posted="secret-invite", email="a@mailinator.com"),
            DISPOSABLE_FAIL,
        )
        self.assertIsNone(
            validate_register_post(req, invite_posted="secret-invite", email="a@company.ru")
        )


@override_settings(
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "rg-def"},
        "ratelimit": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "rg-rl"},
    }
)
class RegisterGlobalDayLimitTests(SimpleTestCase):
    def setUp(self):
        caches["ratelimit"].clear()

    def test_global_day_cap(self):
        for i in range(3):
            r = registration_rate_limits(
                client_id=f"1.1.1.{i}",
                method="POST",
                burst_max=100,
                burst_window=300,
                post_max=100,
                post_window=3600,
                global_day_max=3,
                global_day_window=86400,
            )
            self.assertFalse(r.exceeded, i)
        blocked = registration_rate_limits(
            client_id="9.9.9.9",
            method="POST",
            burst_max=100,
            burst_window=300,
            post_max=100,
            post_window=3600,
            global_day_max=3,
            global_day_window=86400,
        )
        self.assertTrue(blocked.exceeded)
        self.assertEqual(blocked.limit_key, "register_global_day")


class PurgePendingTests(SimpleTestCase):
    def test_purge_all_and_by_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "users.json"
            path.write_text(
                json.dumps(
                    {
                        "users": {
                            "freshbot": {
                                "approved": False,
                                "created_at": "2026-10-08 12:00",
                                "email": "a@x.ru",
                            },
                            "oldbot": {
                                "approved": False,
                                "created_at": "2020-01-01 12:00",
                                "email": "b@x.ru",
                            },
                            "okuser": {
                                "approved": True,
                                "created_at": "2020-01-01 12:00",
                                "email": "c@x.ru",
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(biota_auth, "USERS_STORE_PATH", path):
                biota_auth.invalidate_users_store_cache()
                n, names = biota_auth._purge_pending_registrations(all_pending=False, max_age_days=7)
                self.assertEqual(n, 1)
                self.assertEqual(names, ["oldbot"])
                store = biota_auth._load_users_store()
                self.assertIn("freshbot", store)
                self.assertIn("okuser", store)
                self.assertNotIn("oldbot", store)

                n2, names2 = biota_auth._purge_pending_registrations(all_pending=True)
                self.assertEqual(n2, 1)
                self.assertEqual(names2, ["freshbot"])
                store2 = biota_auth._load_users_store()
                self.assertNotIn("freshbot", store2)
                self.assertIn("okuser", store2)

    def test_delete_registered_users_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "users.json"
            path.write_text(
                json.dumps(
                    {
                        "users": {
                            "a1": {"approved": False},
                            "a2": {"approved": False},
                            "keep": {"approved": True},
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(biota_auth, "USERS_STORE_PATH", path):
                biota_auth.invalidate_users_store_cache()
                n, removed, errs = biota_auth._delete_registered_users(["a1", "a2", "missing"])
                self.assertEqual(n, 2)
                self.assertEqual(sorted(removed), ["a1", "a2"])
                self.assertTrue(any("missing" in e for e in errs))
                store = biota_auth._load_users_store()
                self.assertEqual(set(store.keys()), {"keep"})


@override_settings(
    BIOTA_REGISTER_INVITE_CODE="",
    BIOTA_REGISTER_RATELIMIT_ENABLED=False,
    ALLOWED_HOSTS=["*"],
)
class RegisterViewClosedTests(TestCase):
    def test_closed_without_invite_code(self):
        c = Client()
        res = c.get(reverse("register"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "временно закрыта")
        self.assertNotContains(res, 'name="invite_code"')


@override_settings(
    BIOTA_REGISTER_INVITE_CODE="team-code",
    BIOTA_REGISTER_RATELIMIT_ENABLED=False,
    ALLOWED_HOSTS=["*"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class RegisterViewOpenTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "users.json"
        self.path.write_text(json.dumps({"users": {}}), encoding="utf-8")
        self.patcher = patch.object(biota_auth, "USERS_STORE_PATH", self.path)
        self.patcher.start()
        biota_auth.invalidate_users_store_cache()
        self.client = Client()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_form_shows_invite_and_honeypot(self):
        res = self.client.get(reverse("register"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'name="invite_code"')
        self.assertContains(res, 'name="website"')
        self.assertIn(SESSION_ISSUED_AT, self.client.session)

    def test_honeypot_rejects(self):
        self.client.get(reverse("register"))
        session = self.client.session
        session[SESSION_ISSUED_AT] = time.time() - 10
        session.save()
        res = self.client.post(
            reverse("register"),
            {
                "invite_code": "team-code",
                "username": "gooduser",
                "email": "good@company.ru",
                "password": "password12",
                "password2": "password12",
                "website": "http://bot",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Не удалось зарегистрироваться")
        self.assertEqual(biota_auth._load_users_store(), {})

    def test_success_with_invite(self):
        self.client.get(reverse("register"))
        session = self.client.session
        session[SESSION_ISSUED_AT] = time.time() - 10
        session.save()
        res = self.client.post(
            reverse("register"),
            {
                "invite_code": "team-code",
                "username": "gooduser",
                "email": "good@company.ru",
                "password": "password12",
                "password2": "password12",
                "website": "",
            },
        )
        self.assertEqual(res.status_code, 302)
        store = biota_auth._load_users_store()
        self.assertIn("gooduser", store)
        self.assertFalse(store["gooduser"].get("approved"))
