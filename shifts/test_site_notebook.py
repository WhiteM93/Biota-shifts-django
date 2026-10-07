from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from shifts.inventory_chat import ask_inventory_chat, forced_tool_call, is_notebook_chat_question
from shifts.inventory_chat_tools import add_site_note, run_tool
from shifts.models import SiteNotebookTask


class SiteNotebookToolTests(TestCase):
    def test_add_site_note_creates_open_task(self):
        result = add_site_note(
            title="Добавь фильтр по сверлу",
            body="В корпусном инструменте нужен вид сверло",
            username="worker1",
            source_question="запиши в блокнот: добавь вид сверло",
            page="inventory",
            panel="stock",
        )
        self.assertTrue(result["ok"])
        row = SiteNotebookTask.objects.get(author_username="worker1", title="Добавь фильтр по сверлу")
        self.assertEqual(row.status, SiteNotebookTask.STATUS_OPEN)
        self.assertIn("сверло", row.body.lower())

    def test_run_tool_injects_username(self):
        result = run_tool(
            "add_site_note",
            {"title": "Кнопка экспорта", "body": "Нужна кнопка Excel на истории"},
            context={"username": "ivan", "source_question": "добавь на сайт кнопку Excel"},
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(
            SiteNotebookTask.objects.get(title="Кнопка экспорта").author_username,
            "ivan",
        )

    def test_forced_notebook_intent(self):
        call = forced_tool_call("запиши в блокнот: добавь фильтр по диаметру на складе")
        self.assertIsNotNone(call)
        self.assertEqual(call["tool"], "add_site_note")
        self.assertIn("фильтр по диаметру", (call["args"].get("body") or "").lower())
        self.assertNotIn("блокнот", (call["args"].get("title") or "").lower())

    def test_forced_notebook_typos(self):
        for phrase, needle in (
            ("запиши в блокот: добавь кнопку экспорта", "кнопку экспорта"),
            ("добавь в блокнт задачу про фильтр", "задачу про фильтр"),
            ("запиши в блокнод: нужен вид сверло", "вид сверло"),
        ):
            call = forced_tool_call(phrase)
            self.assertIsNotNone(call, phrase)
            self.assertEqual(call["tool"], "add_site_note", phrase)
            self.assertIn(needle, (call["args"].get("body") or "").lower())

    def test_notebook_chat_skips_gpt(self):
        self.assertTrue(is_notebook_chat_question("Добавь в блокнот: фильтр по сверлу"))
        with (
            patch("shifts.inventory_chat.yandex_gpt_configured", return_value=False) as cfg,
            patch("shifts.inventory_chat.build_warehouse_context") as snap,
            patch("shifts.inventory_chat.complete") as gpt,
        ):
            result = ask_inventory_chat(
                "Добавь в блокнот: фильтр по сверлу на остатках",
                username="worker1",
                page_context={"page": "inventory", "panel": "stock"},
            )
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("used_tools"), ["add_site_note"])
        cfg.assert_not_called()
        snap.assert_not_called()
        gpt.assert_not_called()
        row = SiteNotebookTask.objects.get(author_username="worker1")
        self.assertIn("фильтр по сверлу", row.body.lower())
        self.assertNotIn("добавь в блокнот", row.title.lower())


class SiteNotebookViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.task = SiteNotebookTask.objects.create(
            author_username="worker1",
            title="Добавить вид сверло",
            body="В корпусном инструменте добавить вид сверло",
            status=SiteNotebookTask.STATUS_OPEN,
        )

    def test_admin_sees_notebook(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        res = self.client.get(reverse("site_notebook"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Добавить вид сверло")

    def test_non_admin_forbidden(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        with patch("shifts.site_notebook_views._is_admin", return_value=False):
            res = self.client.get(reverse("site_notebook"))
        self.assertEqual(res.status_code, 403)

    def test_admin_marks_done(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        res = self.client.post(
            reverse("site_notebook"),
            {"action": "done", "id": str(self.task.id), "status": "open"},
        )
        self.assertEqual(res.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, SiteNotebookTask.STATUS_DONE)
        self.assertEqual(self.task.done_by, "admin")
        self.assertIsNotNone(self.task.done_at)

    def test_admin_rejects_with_reason(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        res = self.client.post(
            reverse("site_notebook"),
            {
                "action": "reject",
                "id": str(self.task.id),
                "status": "open",
                "reject_reason": "Уже есть на вкладке фильтров",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, SiteNotebookTask.STATUS_REJECTED)
        self.assertEqual(self.task.reject_reason, "Уже есть на вкладке фильтров")
        self.assertEqual(self.task.done_by, "admin")
        self.assertIsNotNone(self.task.done_at)

    def test_reject_without_reason_keeps_open(self):
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        res = self.client.post(
            reverse("site_notebook"),
            {"action": "reject", "id": str(self.task.id), "status": "open", "reject_reason": "  "},
        )
        self.assertEqual(res.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, SiteNotebookTask.STATUS_OPEN)
        self.assertEqual(self.task.reject_reason, "")

    def test_reopen_rejected(self):
        self.task.status = SiteNotebookTask.STATUS_REJECTED
        self.task.reject_reason = "не нужно"
        self.task.done_by = "admin"
        self.task.save(update_fields=["status", "reject_reason", "done_by"])
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        res = self.client.post(
            reverse("site_notebook"),
            {"action": "reopen", "id": str(self.task.id), "status": "rejected"},
        )
        self.assertEqual(res.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, SiteNotebookTask.STATUS_OPEN)
        self.assertEqual(self.task.reject_reason, "")
        self.assertEqual(self.task.done_by, "")
