"""Тесты статистики сайта и версий статики по содержимому."""

import json
import re
from unittest.mock import patch

from django.http import HttpResponse, HttpResponseServerError
from django.template import Context, Template
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from shifts.middleware import SiteStatsMiddleware
from shifts.models import SiteErrorLog, SiteRequestLog
from shifts.site_stats import _pct, build_dashboard, fmt_ms


class AssetTagTests(SimpleTestCase):
    def test_existing_file_gets_content_hash(self):
        html = Template("{% asset 'shifts/js/site-stats.js' %}").render(Context())
        self.assertRegex(html, r"^/static/shifts/js/site-stats\.js\?v=[0-9a-f]{10}$")

    @override_settings(STATIC_ASSET_VERSION="777")
    def test_missing_file_falls_back(self):
        html = Template("{% asset 'shifts/js/no-such-file.js' %}").render(Context())
        self.assertEqual(html, "/static/shifts/js/no-such-file.js?v=777")


class HelpersTests(SimpleTestCase):
    def test_percentile(self):
        self.assertEqual(_pct([5, 1, 3, 2, 4], 0.5), 3)
        self.assertEqual(_pct(list(range(1, 11)), 0.9), 9)
        self.assertIsNone(_pct([], 0.5))

    def test_fmt_ms(self):
        self.assertEqual(fmt_ms(350), "350 мс")
        self.assertEqual(fmt_ms(1250), "1,2 с")
        self.assertEqual(fmt_ms(None), "—")


def _login(client, username="admin"):
    session = client.session
    session["biota_username"] = username
    session.save()


@override_settings(BIOTA_SITE_STATS=True)
@patch("shifts.site_stats_views._admin_only", return_value=True)
class SiteStatsFlowTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_page_view_recorded_and_metrics_attached(self, _mock):
        _login(self.client)
        resp = self.client.get("/cabinet/site-stats/")
        self.assertEqual(resp.status_code, 200)
        row = SiteRequestLog.objects.get(is_page=True)
        self.assertEqual(row.username, "admin")
        self.assertEqual(row.route, "/cabinet/site-stats/")
        self.assertTrue(row.req_id)
        self.assertIn(row.req_id, resp.content.decode("utf-8"))

        resp = self.client.post(
            "/site-stats/ingest/",
            data=json.dumps(
                {"events": [{"kind": "page", "req_id": row.req_id, "ttfb_ms": 300, "load_ms": 4200, "net": "4g"}]}
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.json().get("saved"), 1)
        row.refresh_from_db()
        self.assertEqual(row.load_ms, 4200)
        self.assertEqual(row.net, "4g")
        self.assertEqual(SiteRequestLog.objects.filter(route__startswith="/site-stats/").count(), 0)

    def test_js_error_saved(self, _mock):
        _login(self.client)
        resp = self.client.post(
            "/site-stats/ingest/",
            data=json.dumps(
                {"events": [{"kind": "js_error", "message": "TypeError: x is null", "source": "/static/a.js", "line": 5}]}
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.json().get("saved"), 1)
        err = SiteErrorLog.objects.get()
        self.assertEqual(err.source, SiteErrorLog.SOURCE_JS)
        self.assertIn("/static/a.js:5", err.detail)

    def test_ingest_requires_login(self, _mock):
        resp = self.client.post("/site-stats/ingest/", data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 302)

    def test_anonymous_not_found_ignored(self, _mock):
        self.client.get("/wp-admin/setup-config.php")
        self.assertEqual(SiteRequestLog.objects.count(), 0)

    def test_dashboard_aggregates(self, _mock):
        SiteRequestLog.objects.create(username="u1", path="/a/", route="/a/", is_page=True, status=200, server_ms=100, load_ms=900)
        SiteRequestLog.objects.create(username="u2", path="/a/", route="/a/", is_page=True, status=200, server_ms=300, load_ms=2500)
        SiteRequestLog.objects.create(username="u1", method="POST", path="/b/", route="/b/", status=500, server_ms=50)
        data = build_dashboard(7)
        self.assertEqual(data["summary"]["views"], 2)
        self.assertEqual(data["summary"]["users"], 2)
        self.assertEqual(data["summary"]["err5xx"], 1)
        self.assertEqual(data["popular"][0]["route"], "/a/")
        self.assertEqual(data["bad_responses"][0]["status"], 500)
        _login(self.client)
        resp = self.client.get("/cabinet/site-stats/?days=30")
        self.assertContains(resp, "Статистика сайта")


@override_settings(BIOTA_SITE_STATS=True)
class ServerExceptionTests(TestCase):
    def test_exception_logged_with_traceback(self):
        request = RequestFactory().get("/boom/")
        request.session = {"biota_username": "admin"}
        mw = SiteStatsMiddleware(lambda r: HttpResponseServerError("err"))
        try:
            raise ValueError("boom happened")
        except ValueError as exc:
            mw.process_exception(request, exc)
        resp = mw(request)
        self.assertEqual(resp.status_code, 500)
        err = SiteErrorLog.objects.get()
        self.assertEqual(err.source, SiteErrorLog.SOURCE_SERVER)
        self.assertIn("boom happened", err.message)
        self.assertTrue(re.search(r"Traceback", err.detail))
        self.assertEqual(SiteRequestLog.objects.get().status, 500)

    def test_ok_ajax_not_recorded(self):
        request = RequestFactory().get("/api/x/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        request.session = {"biota_username": "admin"}
        mw = SiteStatsMiddleware(lambda r: HttpResponse("{}", content_type="application/json"))
        mw(request)
        self.assertEqual(SiteRequestLog.objects.count(), 0)
