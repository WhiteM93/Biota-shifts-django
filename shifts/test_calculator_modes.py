"""Базовые режимы фрез / свёрл / резьбы в калькуляторе."""

from django.test import SimpleTestCase

from shifts.calculator_modes import (
    CUTTING_MODE_MATERIALS,
    DRILL_BASELINE_DIAMETERS,
    DRILL_BASELINES,
    END_MILL_BASELINE_DIAMETERS,
    END_MILL_BASELINES,
    THREAD_BASELINE_SIZES,
    THREAD_BASELINES,
    build_drill_baselines,
    build_end_mill_baselines,
    build_thread_baselines,
)


class CalculatorMillBaselinesTests(SimpleTestCase):
    def test_material_grades(self):
        ids = [mid for mid, _lbl in CUTTING_MODE_MATERIALS]
        self.assertEqual(ids, ["d16", "ls59", "amg6", "st30", "st45", "x18h9t"])
        labels = [lbl for _mid, lbl in CUTTING_MODE_MATERIALS]
        self.assertEqual(labels, ["Д16", "ЛС59", "Амг6", "Ст30", "Ст45", "12Х18Н9Т"])

    def test_baseline_diameters_and_ops(self):
        self.assertEqual(
            list(END_MILL_BASELINE_DIAMETERS),
            [16, 12, 10, 8, 6, 4, 3, 2.5, 2, 1.5, 1],
        )
        st45 = END_MILL_BASELINES["st45"]
        self.assertIn("16", st45)
        self.assertIn("2.5", st45)
        self.assertIn("1", st45)
        for d in ("16", "8", "2.5", "1"):
            for op in ("rough", "helical_rad", "helical_ax", "spiral", "adaptive", "finish"):
                row = st45[d][op]
                for key in ("n", "feed", "ae", "ap", "allowance", "flutes", "vc", "fz"):
                    self.assertTrue(str(row.get(key, "")), f"missing {key} for {d}/{op}")

    def test_finish_allowance_zero_rough_positive(self):
        rough = END_MILL_BASELINES["d16"]["10"]["rough"]
        finish = END_MILL_BASELINES["d16"]["10"]["finish"]
        helical_rad = END_MILL_BASELINES["d16"]["10"]["helical_rad"]
        helical_ax = END_MILL_BASELINES["d16"]["10"]["helical_ax"]
        spiral = END_MILL_BASELINES["d16"]["10"]["spiral"]
        self.assertGreater(float(rough["allowance"]), 0)
        self.assertEqual(float(finish["allowance"]), 0)
        self.assertGreater(float(rough["ae"]), float(finish["ae"]))
        self.assertGreater(float(helical_rad["ae"]), float(helical_ax["ae"]))
        self.assertGreater(float(helical_ax["ap"]), float(helical_rad["ap"]))
        self.assertLess(float(helical_rad["ap"]), float(rough["ap"]))
        self.assertGreater(float(spiral["ae"]), float(helical_ax["ae"]))

    def test_payload_includes_baselines(self):
        baselines = build_end_mill_baselines()
        self.assertEqual(baselines["st45"]["6"]["rough"]["flutes"], "3")
        self.assertEqual(baselines["st45"]["12"]["rough"]["flutes"], "4")
        self.assertEqual(baselines["st45"]["1"]["finish"]["flutes"], "2")
        # Нержавейка медленнее дюрали
        self.assertLess(
            float(baselines["x18h9t"]["8"]["rough"]["vc"]),
            float(baselines["d16"]["8"]["rough"]["vc"]),
        )


class CalculatorDrillBaselinesTests(SimpleTestCase):
    def test_diameters(self):
        self.assertEqual(
            list(DRILL_BASELINE_DIAMETERS),
            [16, 12, 10, 8, 6, 5, 4, 3, 2.5, 2, 1.5, 1],
        )

    def test_row_fields(self):
        row = DRILL_BASELINES["st45"]["6"]
        for key in ("n", "feed", "angle", "depth", "pass", "vc", "f"):
            self.assertTrue(str(row.get(key, "")), f"missing {key}")
        self.assertAlmostEqual(float(row["depth"]), 18.0, places=2)
        self.assertEqual(float(row["angle"]), 118.0)

    def test_aluminum_faster_than_steel(self):
        self.assertGreater(
            float(DRILL_BASELINES["d16"]["8"]["vc"]),
            float(DRILL_BASELINES["st45"]["8"]["vc"]),
        )
        self.assertGreater(
            float(DRILL_BASELINES["d16"]["8"]["n"]),
            float(DRILL_BASELINES["st45"]["8"]["n"]),
        )

    def test_build_matches_module(self):
        built = build_drill_baselines()
        self.assertEqual(built["amg6"]["4"]["angle"], DRILL_BASELINES["amg6"]["4"]["angle"])


class CalculatorThreadBaselinesTests(SimpleTestCase):
    def test_sizes(self):
        labels = [m for m, _d, _p in THREAD_BASELINE_SIZES]
        self.assertEqual(labels, ["M3", "M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"])

    def test_tool_types_and_pitch(self):
        m6 = THREAD_BASELINES["st45"]["M6"]
        self.assertIn("Метчик", m6)
        self.assertIn("Раскатник", m6)
        self.assertIn("Резьбофреза", m6)
        self.assertEqual(float(m6["Метчик"]["pitch"]), 1.0)
        self.assertEqual(m6["Метчик"]["m"], "M6")
        for key in ("pitch", "n", "vc"):
            self.assertTrue(str(m6["Метчик"].get(key, "")), f"missing {key}")

    def test_form_and_mill_faster_than_tap(self):
        m8 = THREAD_BASELINES["d16"]["M8"]
        self.assertGreater(float(m8["Раскатник"]["n"]), float(m8["Метчик"]["n"]))
        self.assertGreater(float(m8["Резьбофреза"]["n"]), float(m8["Раскатник"]["n"]))

    def test_build_matches_module(self):
        built = build_thread_baselines()
        self.assertEqual(built["st30"]["M10"]["Метчик"]["pitch"], "1.5")
