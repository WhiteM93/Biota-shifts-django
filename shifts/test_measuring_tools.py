from django.test import Client, TestCase
from django.urls import reverse

from shifts.measuring_constants import (
    MEASURING_CATEGORIES,
    build_measuring_display_name,
    measuring_category_needs_kind,
    normalize_measuring_kind,
    normalize_measuring_pitch,
    normalize_thread_gauge_go_nogo,
)
from shifts.models import MeasuringToolSpec, SiteNotebookTask, ToolItem, stock_category_grouped_choices


class MeasuringToolTests(TestCase):
    def test_group_in_filter_choices(self):
        groups = stock_category_grouped_choices()
        titles = [t for _, t, _ in groups]
        self.assertIn("Измерительный инструмент", titles)
        measuring = next(items for code, _, items in groups if code == "measuring")
        keys = [k for k, _ in measuring]
        for k in MEASURING_CATEGORIES:
            self.assertIn(k, keys)

    def test_kind_rules(self):
        self.assertFalse(measuring_category_needs_kind("gauge_smooth"))
        self.assertTrue(measuring_category_needs_kind("gauge_thread"))
        self.assertTrue(measuring_category_needs_kind("measure_univ"))
        self.assertEqual(normalize_measuring_kind("gauge_thread", "plug"), "plug")
        self.assertEqual(normalize_measuring_kind("measure_univ", "caliper"), "caliper")
        self.assertEqual(normalize_measuring_kind("measure_univ", "nope"), "")
        self.assertEqual(normalize_thread_gauge_go_nogo("go"), "go")
        self.assertEqual(normalize_thread_gauge_go_nogo("ПР"), "go")
        self.assertEqual(normalize_thread_gauge_go_nogo("не"), "nogo")
        self.assertEqual(normalize_thread_gauge_go_nogo("пр-не"), "set")
        self.assertEqual(normalize_measuring_pitch("1,5"), normalize_measuring_pitch("1.5"))

    def test_create_thread_gauge(self):
        tool = ToolItem.objects.create(
            category="gauge_thread",
            name="Пробка M10",
            quantity=1,
        )
        MeasuringToolSpec.objects.create(
            tool=tool,
            brand="ГОСТ",
            kind="plug",
            thread_size_label="M10",
            pitch_mm=normalize_measuring_pitch("1.5"),
            go_nogo="go",
            thread_tolerance="6H",
        )
        tool.refresh_from_db()
        self.assertEqual(tool.measuring_tool_spec.go_nogo, "go")
        self.assertEqual(tool.measuring_tool_spec.thread_tolerance, "6H")
        self.assertIn(
            "6H",
            build_measuring_display_name(
                category="gauge_thread",
                brand="ГОСТ",
                kind="plug",
                thread_size_label="M10",
                pitch_mm=normalize_measuring_pitch("1.5"),
                go_nogo="go",
                thread_tolerance="6H",
            ),
        )
        self.assertIn(
            "ПР",
            build_measuring_display_name(
                category="gauge_thread",
                brand="ГОСТ",
                kind="plug",
                thread_size_label="M10",
                pitch_mm=normalize_measuring_pitch("1.5"),
                go_nogo="go",
                thread_tolerance="6H",
            ),
        )

    def test_notebook_verification_reminder_exists_after_migrate(self):
        self.assertTrue(
            SiteNotebookTask.objects.filter(title="Измерительный: даты поверки").exists()
        )


class MeasuringStockFilterTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.keep = ToolItem.objects.create(
            category="measure_univ",
            name="Штангенциркуль A",
            quantity=2,
        )
        MeasuringToolSpec.objects.create(
            tool=self.keep,
            brand="MITUTOYO",
            kind="caliper",
            measure_range="0–150 мм",
            accuracy="0,01 мм",
            ip_rating="IP54",
        )
        other = ToolItem.objects.create(
            category="measure_univ",
            name="Микрометр B",
            quantity=1,
        )
        MeasuringToolSpec.objects.create(
            tool=other,
            brand="HOLEX",
            kind="micrometer",
            measure_range="0–25 мм",
            accuracy="0,001 мм",
        )

    def test_stock_filter_shows_measuring_fields(self):
        res = self.client.get(
            reverse("inventory"),
            {"panel": "stock", "category": "measure_univ", "show_all": "1"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'name="ms_kind"')
        self.assertContains(res, 'name="ms_brand"')
        self.assertContains(res, 'name="ms_range"')
        self.assertContains(res, "MITUTOYO")

    def test_stock_filter_by_kind(self):
        res = self.client.get(
            reverse("inventory"),
            {
                "panel": "stock",
                "category": "measure_univ",
                "show_all": "1",
                "ms_kind": "caliper",
            },
        )
        self.assertEqual(res.status_code, 200)
        items = list(res.context["tool_items"])
        self.assertEqual([t.id for t in items], [self.keep.id])
        self.assertEqual(res.context["filters"]["ms_kind"], "caliper")
