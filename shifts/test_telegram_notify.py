"""Тесты Telegram-уведомлений."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from biota_shifts.notification_settings import parse_chat_ids_text
from biota_shifts.telegram_notify import (
    split_telegram_text,
    send_telegram_broadcast,
    send_telegram_message,
)


class TelegramNotifyTests(SimpleTestCase):
    def test_parse_chat_ids_text(self):
        ids = parse_chat_ids_text("123\n@chan, -10099\n123")
        self.assertEqual(ids, ["123", "@chan", "-10099"])

    def test_split_telegram_text_short(self):
        self.assertEqual(split_telegram_text("hi"), ["hi"])

    def test_split_telegram_text_chunks(self):
        text = "a" * 5000
        parts = split_telegram_text(text, limit=4096)
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(parts[0]), 4096)
        self.assertEqual(len(parts[1]), 904)

    @patch("biota_shifts.telegram_notify.urllib.request.urlopen")
    def test_send_telegram_message_ok(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b'{"ok": true, "result": {}}'
        mock_urlopen.return_value.__enter__.return_value = resp
        out = send_telegram_message("tok", "123", "test")
        self.assertTrue(out["ok"])

    @patch("biota_shifts.telegram_notify.send_telegram_message")
    def test_send_telegram_broadcast_multiple(self, mock_send):
        n = send_telegram_broadcast("tok", ["1", "2"], "hello")
        self.assertEqual(n, 2)
        self.assertEqual(mock_send.call_count, 2)
