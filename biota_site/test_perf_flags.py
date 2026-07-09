"""Тесты env-флагов производительности."""

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from biota_site.perf_flags import load_perf_settings


class PerfFlagsTests(SimpleTestCase):
    def test_package_a_off_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            s = load_perf_settings()
        self.assertFalse(s["BIOTA_PERF_PACKAGE_A"])
        self.assertFalse(s["BIOTA_PERF_MOBILE_GRAPH"])
        self.assertFalse(s["BIOTA_PERF_DEFER_SCRIPTS"])
        self.assertEqual(s["BIOTA_PERF_USERS_STORE_CACHE_SEC"], 0)

    def test_package_a_enables_all(self):
        with patch.dict(os.environ, {"BIOTA_PERF_PACKAGE_A": "1"}, clear=True):
            s = load_perf_settings()
        self.assertTrue(s["BIOTA_PERF_PACKAGE_A"])
        self.assertTrue(s["BIOTA_PERF_MOBILE_GRAPH"])
        self.assertTrue(s["BIOTA_PERF_DEFER_SCRIPTS"])
        self.assertEqual(s["BIOTA_PERF_USERS_STORE_CACHE_SEC"], 60)

    def test_individual_override(self):
        env = {"BIOTA_PERF_PACKAGE_A": "1", "BIOTA_PERF_MOBILE_GRAPH": "0"}
        with patch.dict(os.environ, env, clear=True):
            s = load_perf_settings()
        self.assertTrue(s["BIOTA_PERF_PACKAGE_A"])
        self.assertFalse(s["BIOTA_PERF_MOBILE_GRAPH"])
