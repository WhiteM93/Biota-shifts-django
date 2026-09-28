from django.test import Client, TestCase
from django.urls import reverse

from shifts.inventory_ai_log import record_ai_turn
from shifts.models import InventoryAiTurn


class InventoryAiLogTests(TestCase):
    def test_record_turn(self):
        row = record_ai_turn(
            username="tester",
            kind=InventoryAiTurn.KIND_INV_CHAT,
            question="топ выдач",
            result={"ok": True, "reply": "Сверло D3 — 12 шт.", "used_tools": ["top_issued_tools"]},
            session_key="sess-1",
        )
        self.assertIsNotNone(row)
        self.assertEqual(InventoryAiTurn.objects.count(), 1)
        self.assertEqual(row.username, "tester")
        self.assertIn("Сверло", row.reply)
        self.assertEqual(row.used_tools, ["top_issued_tools"])

    def test_empty_question_skipped(self):
        self.assertIsNone(record_ai_turn(username="x", kind="inv_chat", question="  "))
        self.assertEqual(InventoryAiTurn.objects.count(), 0)


class InventoryAiArchiveViewTests(TestCase):
    def setUp(self):
        record_ai_turn(
            username="worker1",
            kind=InventoryAiTurn.KIND_INV_CHAT,
            question="кто брал M3",
            result={"ok": True, "reply": "Иванов"},
            session_key="abc-sess",
        )
        self.client = Client()

    def test_admin_sees_archive(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        res = self.client.get(reverse("inventory_ai_archive"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "кто брал M3")
        self.assertContains(res, "Иванов")
        sess = self.client.get(reverse("inventory_ai_archive_session", kwargs={"session_key": "abc-sess"}))
        self.assertEqual(sess.status_code, 200)
        self.assertContains(sess, "Иванов")

    def test_non_admin_forbidden(self):
        from unittest.mock import patch

        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        with patch("shifts.inventory_ai_archive_views._is_admin", return_value=False):
            res = self.client.get(reverse("inventory_ai_archive"))
        self.assertEqual(res.status_code, 403)
