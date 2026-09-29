import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from shifts import site_updates as site_updates_module
from shifts.site_updates import latest_site_update_id, load_site_updates


class SiteUpdatesTests(TestCase):
    def setUp(self):
        self._prefs_dir = tempfile.TemporaryDirectory()
        self._prefs_path = Path(self._prefs_dir.name) / ".biota_account_prefs.json"
        self._env_patch = patch.dict(os.environ, {"BIOTA_ACCOUNT_PREFS": str(self._prefs_path)})
        self._env_patch.start()
        site_updates_module._prefs_ready = False
        site_updates_module._prefs_mtime = None
        site_updates_module._prefs_seen = {}
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()

    def tearDown(self):
        self._env_patch.stop()
        self._prefs_dir.cleanup()

    def test_page_reads_git_json_not_form(self):
        rows = load_site_updates(force=True)
        self.assertTrue(rows)
        page = self.client.get(reverse("site_updates"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, rows[0].title)
        self.assertContains(page, "как этим пользоваться")
        self.assertNotContains(page, "git")
        self.assertNotContains(page, "Опубликовать")

    def test_post_is_not_allowed(self):
        res = self.client.post(reverse("site_updates"), {"action": "create", "title": "X", "body": "Y"})
        self.assertEqual(res.status_code, 405)

    def test_nav_shows_unread_then_clears(self):
        latest = latest_site_update_id()
        self.assertGreater(latest, 0)
        home = self.client.get(reverse("graph"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "nav-updates-badge")
        self.client.get(reverse("site_updates"))
        home2 = self.client.get(reverse("graph"))
        self.assertNotContains(home2, "nav-updates-badge")

    def test_seen_persisted_for_account_after_new_session(self):
        latest = latest_site_update_id()
        self.assertGreater(latest, 0)
        self.client.get(reverse("site_updates"))
        other = Client()
        session = other.session
        session["biota_username"] = "admin"
        session.save()
        home = other.get(reverse("graph"))
        self.assertEqual(home.status_code, 200)
        self.assertNotContains(home, "nav-updates-badge")

    def test_updates_page_hides_badge_while_reading(self):
        page = self.client.get(reverse("site_updates"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "nav-updates-badge")

    def test_ack_once_and_list_users(self):
        from shifts.models import SiteUpdateAck

        latest = latest_site_update_id()
        self.assertGreater(latest, 0)
        page = self.client.get(reverse("site_updates"))
        self.assertContains(page, "js-su-ack")
        self.assertContains(page, "js-su-ack-chip")

        url = reverse("site_update_ack", kwargs={"update_id": latest})
        first = self.client.post(url)
        self.assertEqual(first.status_code, 200)
        data = first.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["created"])
        self.assertEqual(data["ack_count"], 1)
        self.assertIn("admin", data["ack_users"])
        self.assertEqual(SiteUpdateAck.objects.filter(update_id=latest, username="admin").count(), 1)

        second = self.client.post(url)
        self.assertEqual(second.status_code, 200)
        data2 = second.json()
        self.assertTrue(data2["ok"])
        self.assertFalse(data2["created"])
        self.assertEqual(data2["ack_count"], 1)
        self.assertEqual(SiteUpdateAck.objects.filter(update_id=latest).count(), 1)

        SiteUpdateAck.objects.create(update_id=latest, username="ivan")
        page2 = self.client.get(reverse("site_updates"))
        self.assertContains(page2, 'data-acked="1"')
        self.assertContains(page2, "admin|ivan")
        self.assertContains(page2, ">2</span>")

    def test_ack_unknown_update_404(self):
        res = self.client.post(reverse("site_update_ack", kwargs={"update_id": 999999}))
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.json().get("ok"))
