from django.test import Client, TestCase
from django.urls import reverse

from shifts.site_updates import latest_site_update_id, load_site_updates


class SiteUpdatesTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()

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
