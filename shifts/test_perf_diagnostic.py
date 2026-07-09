"""Тесты диагностики медленных загрузок."""

import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase, override_settings

from shifts.models import PageLoadDiagnostic
from shifts.perf_diagnostic import build_diagnosis


class BuildDiagnosisTests(SimpleTestCase):
    def test_slow_ttfb_network_hint(self):
        text = build_diagnosis("client", ttfb_ms=4000, load_ms=6000, connection={"effectiveType": "3g"})
        self.assertIn("первого байта", text)
        self.assertIn("3g", text)

    def test_server_slow_hint(self):
        text = build_diagnosis("server", server_ms=3500)
        self.assertIn("3500", text)


@override_settings(
    BIOTA_PERF_DIAGNOSTICS=True,
    BIOTA_PERF_DIAG_TTFB_MS=1000,
    BIOTA_PERF_DIAG_LOAD_MS=2000,
)
class PerfDiagnosticIngestTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_ingest_requires_login(self):
        resp = self.client.post(
            "/perf-diagnostic/ingest/",
            data=json.dumps({"ttfb_ms": 5000, "load_ms": 8000}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 302)

    def test_ingest_skips_fast_page(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        resp = self.client.post(
            "/perf-diagnostic/ingest/",
            data=json.dumps({"ttfb_ms": 100, "load_ms": 200, "path": "/home/"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("skipped"))
        self.assertEqual(PageLoadDiagnostic.objects.count(), 0)

    def test_ingest_saves_slow_report(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        resp = self.client.post(
            "/perf-diagnostic/ingest/",
            data=json.dumps(
                {
                    "ttfb_ms": 3200,
                    "load_ms": 7100,
                    "dom_ms": 4500,
                    "path": "/home/",
                    "connection": {"effectiveType": "4g"},
                    "slow_resources": [{"name": "inventory.js", "dur_ms": 1500}],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PageLoadDiagnostic.objects.count(), 1)
        row = PageLoadDiagnostic.objects.get()
        self.assertEqual(row.source, PageLoadDiagnostic.SOURCE_CLIENT)
        self.assertEqual(row.ttfb_ms, 3200)
        self.assertIn("admin", row.actor_username)

    @patch("shifts.perf_diagnostic_views._admin_only", return_value=False)
    def test_admin_page_forbidden(self, _mock):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        resp = self.client.get("/cabinet/perf-diagnostics/")
        self.assertEqual(resp.status_code, 403)
