"""Тесты API ручного вызова сводки."""
import json
from datetime import date, datetime
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

from biota_shifts.attendance_summary import AttendanceSummary, SLOT_MORNING
from biota_shifts.constants import MSK
from biota_shifts.notify_trigger import (
    chat_id_allowed,
    resolve_slot_from_request,
    verify_notify_api_bearer,
)


class NotifyTriggerUnitTests(SimpleTestCase):
    def test_resolve_slot_auto_morning(self):
        with patch("biota_shifts.notify_trigger.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 18, 10, 0, tzinfo=MSK)
            self.assertEqual(resolve_slot_from_request("auto"), "morning")

    def test_resolve_slot_auto_evening(self):
        with patch("biota_shifts.notify_trigger.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 18, 16, 0, tzinfo=MSK)
            self.assertEqual(resolve_slot_from_request("auto"), "evening")

    def test_chat_id_allowed_whitelist(self):
        settings = {"telegram_chat_ids": ["111", "222"]}
        self.assertTrue(chat_id_allowed("111", settings))
        self.assertFalse(chat_id_allowed("999", settings))


class NotifyTriggerApiTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_unauthorized_without_secret(self):
        resp = self.client.post(
            "/api/notify/attendance/",
            data=json.dumps({"chat_id": "1"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    @patch("shifts.notify_api_views.trigger_attendance_summary")
    def test_ok_with_bearer(self, mock_trigger):
        mock_trigger.return_value = {"ok": True, "delivered": True, "absent_count": 0, "text": "x", "slot": "morning"}
        with patch("shifts.notify_api_views.verify_notify_api_bearer", return_value=True):
            with patch("shifts.notify_api_views.chat_id_allowed", return_value=True):
                resp = self.client.post(
                    "/api/notify/attendance/",
                    data=json.dumps({"chat_id": "577292537", "slot": "morning"}),
                    content_type="application/json",
                    HTTP_AUTHORIZATION="Bearer sekret",
                )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        mock_trigger.assert_called_once()

    @patch("biota_shifts.notify_trigger.resolve_notify_relay_secret", return_value="sekret")
    def test_verify_bearer(self, _mock_secret):
        class Req:
            headers = {"Authorization": "Bearer sekret"}

        self.assertTrue(verify_notify_api_bearer(Req()))

    @patch("biota_shifts.notify_trigger.load_attendance_summary_from_db")
    @patch("biota_shifts.notify_trigger.send_summary_telegram")
    @patch("biota_shifts.notify_trigger.notify_delivery_configured", return_value=True)
    def test_trigger_sends_to_chat(self, _cfg, mock_send, mock_load):
        from biota_shifts.notify_trigger import trigger_attendance_summary

        summary = AttendanceSummary(
            slot=SLOT_MORNING,
            shift_date=date(2026, 6, 18),
            check_at=datetime(2026, 6, 18, 9, 0, tzinfo=MSK),
            shift_label="д",
            absent=[],
        )
        mock_load.return_value = summary
        out = trigger_attendance_summary("morning", chat_id="123", settings={"telegram_chat_ids": []})
        self.assertTrue(out["delivered"])
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs.get("chat_ids"), ["123"])
