"""Тесты нормализации размера резьбы (M8 / М8 / 8)."""

from django.test import TestCase

from shifts.size_label_normalize import normalize_cutting_size_label, size_label_match_variants


class MetricSizeLabelNormalizeTests(TestCase):
    def test_latin_m(self):
        self.assertEqual(normalize_cutting_size_label("M8"), "M8")
        self.assertEqual(normalize_cutting_size_label("m8"), "M8")

    def test_cyrillic_m(self):
        self.assertEqual(normalize_cutting_size_label("М8"), "M8")
        self.assertEqual(normalize_cutting_size_label("м8"), "M8")

    def test_bare_number(self):
        self.assertEqual(normalize_cutting_size_label("8"), "M8")
        self.assertEqual(normalize_cutting_size_label("2,5"), "M2.5")
        self.assertEqual(normalize_cutting_size_label("2.5"), "M2.5")

    def test_leading_zeros(self):
        self.assertEqual(normalize_cutting_size_label("M08"), "M8")
        self.assertEqual(normalize_cutting_size_label("08"), "M8")

    def test_imperial_untouched(self):
        self.assertEqual(normalize_cutting_size_label("1/4-20"), "1/4-20")

    def test_match_variants_include_bare(self):
        variants = size_label_match_variants("M8")
        self.assertIn("M8", variants)
        self.assertIn("8", variants)
        self.assertIn("М8", variants)
