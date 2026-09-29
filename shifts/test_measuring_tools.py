from django.test import TestCase

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
        )
        tool.refresh_from_db()
        self.assertEqual(tool.measuring_tool_spec.go_nogo, "go")
        self.assertIn(
            "M10×1.5",
            build_measuring_display_name(
                category="gauge_thread",
                brand="ГОСТ",
                kind="plug",
                thread_size_label="M10",
                pitch_mm=normalize_measuring_pitch("1.5"),
                go_nogo="go",
            ),
        )

    def test_notebook_verification_reminder_exists_after_migrate(self):
        self.assertTrue(
            SiteNotebookTask.objects.filter(title="Измерительный: даты поверки").exists()
        )
