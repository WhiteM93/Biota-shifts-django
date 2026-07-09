"""Тесты авто-перехода на мобильный график."""

from django.http import HttpRequest, QueryDict
from django.test import SimpleTestCase, override_settings

from shifts.graph_device import (
    GRAPH_DESKTOP_COOKIE,
    apply_desktop_graph_query_redirect,
    is_mobile_user_agent,
    mobile_graph_url,
    prefers_desktop_graph,
    redirect_to_mobile_graph,
    should_auto_redirect_mobile_graph,
)


def _req(ua: str = "", get: dict | None = None, cookies: dict | None = None) -> HttpRequest:
    r = HttpRequest()
    r.META["HTTP_USER_AGENT"] = ua
    r.GET = QueryDict(mutable=True)
    if get:
        for k, v in get.items():
            r.GET[k] = v
    if cookies:
        for k, v in cookies.items():
            r.COOKIES[k] = v
    return r


class GraphDeviceTests(SimpleTestCase):
    def test_detects_iphone(self):
        self.assertTrue(
            is_mobile_user_agent(_req("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"))
        )

    def test_desktop_windows_not_mobile(self):
        self.assertFalse(
            is_mobile_user_agent(_req("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"))
        )

    def test_mobile_redirect_preserves_query(self):
        r = _req("iPhone", {"year": "2026", "month": "5"})
        resp = redirect_to_mobile_graph(r)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/graph/mobile/", resp.url)
        self.assertIn("year=2026", resp.url)
        self.assertIn("month=5", resp.url)

    def test_desktop_query_sets_cookie(self):
        r = _req(get={"year": "2026", "month": "5", "desktop": "1"})
        resp = apply_desktop_graph_query_redirect(r)
        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertEqual(resp.status_code, 302)
        self.assertIn("year=2026", resp.url)
        self.assertNotIn("desktop=1", resp.url)
        self.assertEqual(resp.cookies[GRAPH_DESKTOP_COOKIE].value, "1")

    def test_cookie_prefers_desktop(self):
        r = _req(cookies={GRAPH_DESKTOP_COOKIE: "1"})
        self.assertTrue(prefers_desktop_graph(r))

    def test_prefer_mobile_clears_cookie_on_redirect(self):
        r = _req("iPhone", {"prefer_mobile": "1", "year": "2026"})
        resp = redirect_to_mobile_graph(r)
        self.assertEqual(resp.cookies[GRAPH_DESKTOP_COOKIE].value, "")

    def test_mobile_graph_url(self):
        r = _req(get={"year": "2026", "date": "2026-05-15", "desktop": "1"})
        self.assertIn("graph/mobile", mobile_graph_url(r))
        self.assertIn("year=2026", mobile_graph_url(r))
        self.assertNotIn("desktop", mobile_graph_url(r))

    @override_settings(BIOTA_PERF_MOBILE_GRAPH=False)
    def test_auto_redirect_off_by_default(self):
        r = _req("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
        self.assertFalse(should_auto_redirect_mobile_graph(r))

    @override_settings(BIOTA_PERF_MOBILE_GRAPH=True)
    def test_auto_redirect_iphone_when_enabled(self):
        r = _req("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
        self.assertTrue(should_auto_redirect_mobile_graph(r))

    @override_settings(BIOTA_PERF_MOBILE_GRAPH=True)
    def test_auto_redirect_respects_desktop_cookie(self):
        r = _req("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", cookies={GRAPH_DESKTOP_COOKIE: "1"})
        self.assertFalse(should_auto_redirect_mobile_graph(r))

    @override_settings(BIOTA_PERF_MOBILE_GRAPH=True)
    def test_auto_redirect_skips_desktop_windows(self):
        r = _req("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0")
        self.assertFalse(should_auto_redirect_mobile_graph(r))
