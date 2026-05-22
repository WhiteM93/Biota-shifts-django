"""Тесты фильтра «Мало на складе» на главной."""
from django.test import TestCase, RequestFactory

from shifts.home_low_stock import (
    HomeLowStockPrefs,
    apply_home_low_stock_context,
    fetch_low_stock_items,
    resolve_home_low_stock_prefs,
    save_home_low_stock_prefs,
)
from shifts.models import ToolItem, UserHomeLowStockPrefs


class HomeLowStockPrefsTests(TestCase):
    def test_save_and_load_prefs(self):
        save_home_low_stock_prefs("alice", HomeLowStockPrefs(category="drill", max_qty=5))
        prefs = resolve_home_low_stock_prefs("alice", {})
        self.assertEqual(prefs.category, "drill")
        self.assertEqual(prefs.max_qty, 5)

    def test_get_overrides_saved(self):
        save_home_low_stock_prefs("bob", HomeLowStockPrefs(category="", max_qty=10))
        from django.http import QueryDict

        q = QueryDict("stock_category=tap&stock_max_qty=3&stock_apply=1")
        prefs = resolve_home_low_stock_prefs("bob", q)
        self.assertEqual(prefs.category, "tap")
        self.assertEqual(prefs.max_qty, 3)

    def test_all_category_via_apply(self):
        from django.http import QueryDict

        q = QueryDict("stock_category=all&stock_max_qty=10&stock_apply=1")
        prefs = resolve_home_low_stock_prefs("x", q)
        self.assertEqual(prefs.category, "")

    def test_fetch_filters_category_and_qty(self):
        ToolItem.objects.create(category="drill", name="A", quantity=2)
        ToolItem.objects.create(category="tap", name="B", quantity=2)
        ToolItem.objects.create(category="drill", name="C", quantity=8)
        items = fetch_low_stock_items(HomeLowStockPrefs(category="drill", max_qty=5))
        names = {t.name for t in items}
        self.assertEqual(names, {"A"})


class HomeLowStockContextTests(TestCase):
    def test_apply_persists_on_get(self):
        factory = RequestFactory()
        request = factory.get("/home/?stock_category=end_mill&stock_max_qty=7&stock_apply=1")
        ctx = {"low_stock_items": []}
        apply_home_low_stock_context(ctx, username="carol", query=request.GET, can_inventory=True)
        row = UserHomeLowStockPrefs.objects.get(username="carol")
        self.assertEqual(row.category, "end_mill")
        self.assertEqual(row.max_qty, 7)
