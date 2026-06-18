"""Тесты relay-уведомлений."""
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from biota_shifts.attendance_summary import (
    SLOT_MORNING,
    AttendanceSummary,
    send_summary_telegram,
)
from biota_shifts.constants import MSK
from biota_shifts.notify_relay import (
    attendance_summary_relay_payload,
    notify_delivery_configured,
    notify_relay_configured,
    post_notify_relay,
    send_notify_test,
)


class NotifyRelayTests(SimpleTestCase):
    def test_notify_relay_configured_from_settings(self):
        self.assertTrue(notify_relay_configured({"relay_url": "https://bot.test/notify"}))
        self.assertFalse(notify_relay_configured({"relay_url": ""}))

    def test_notify_delivery_configured_relay_only(self):
        self.assertTrue(notify_delivery_configured({"relay_url": "https://bot.test/notify"}))

    def test_attendance_summary_relay_payload(self):
        summary = AttendanceSummary(
            slot=SLOT_MORNING,
            shift_date=date(2026, 6, 18),
            check_at=datetime(2026, 6, 18, 9, 0, tzinfo=MSK),
            shift_label="дневная смена (д)",
            absent=[],
        )
        payload = attendance_summary_relay_payload(summary, {"telegram_chat_ids": ["123"]})
        self.assertEqual(payload["kind"], "attendance_summary")
        self.assertIn("Утренняя сводка", payload["text"])
        self.assertEqual(payload["chat_ids"], ["123"])
        self.assertEqual(payload["meta"]["slot"], SLOT_MORNING)

    @patch("biota_shifts.notify_relay.urllib.request.urlopen")
    def test_post_notify_relay_ok(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b'{"ok": true}'
        resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = resp
        out = post_notify_relay({"kind": "test", "text": "hi"}, {"relay_url": "https://bot.test/notify"})
        self.assertTrue(out["ok"])

    @patch("biota_shifts.notify_relay.post_notify_relay")
    def test_send_notify_test_via_relay(self, mock_post):
        send_notify_test({"relay_url": "https://bot.test/notify"})
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[0][0]["kind"], "test")

    @patch("biota_shifts.notify_relay.send_summary_relay")
    def test_send_summary_telegram_uses_relay(self, mock_relay):
        summary = AttendanceSummary(
            slot=SLOT_MORNING,
            shift_date=date(2026, 6, 18),
            check_at=datetime(2026, 6, 18, 9, 0, tzinfo=MSK),
            shift_label="дневная смена (д)",
            absent=[],
        )
        send_summary_telegram(summary, {"relay_url": "https://bot.test/notify", "telegram_chat_ids": ["1"]})
        mock_relay.assert_called_once()
