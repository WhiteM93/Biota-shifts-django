"""Журнал атак на регистрацию."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from shifts import register_security_log as rsl


class RegisterSecurityLogTests(SimpleTestCase):
    def test_append_and_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sec.jsonl"
            with patch.object(rsl, "LOG_PATH", path):
                rsl.append_register_event(reason="invite", ip="1.2.3.4", username="bot1", email="a@x.ru")
                rsl.append_register_event(reason="honeypot", ip="1.2.3.4", username="bot2")
                rsl.append_register_event(reason="success", ip="8.8.8.8", username="human", email="h@co.ru")
                dash = rsl.build_register_attack_dashboard()
                self.assertGreaterEqual(dash["stats_24h"]["blocked"], 2)
                self.assertEqual(dash["stats_24h"]["success"], 1)
                self.assertTrue(any(r["reason"] == "invite" for r in dash["stats_24h"]["by_reason"]))
                self.assertTrue(any(r["ip"] == "1.2.3.4" for r in dash["stats_24h"]["top_ips"]))
                self.assertTrue(dash["recent"])
                self.assertTrue(rsl.clear_register_security_log())
                self.assertFalse(path.exists())
                dash2 = rsl.build_register_attack_dashboard()
                self.assertEqual(dash2["stats_24h"]["total"], 0)
