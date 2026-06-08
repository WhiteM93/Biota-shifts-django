"""Тесты источника графика: Google Sheets и переключатель на /graph/."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, SimpleTestCase, TestCase

from datetime import datetime

from biota_shifts.constants import MSK
from biota_shifts.schedule_google import (
    SCHEDULE_SOURCE_GOOGLE,
    SCHEDULE_SOURCE_LOCAL,
    google_cell_to_schedule_code,
    google_mv_values_to_schedule_df,
    month_sheet_title,
    parse_schedule_source,
    worksheet_name_candidates,
)
from biota_shifts.schedule_google_cache import needs_scheduled_refresh
from shifts.graph_schedule_source import (
    SESSION_KEY,
    append_schedule_source,
    get_graph_schedule_source,
)


class ParseScheduleSourceTests(SimpleTestCase):
    def test_local_default(self):
        self.assertEqual(parse_schedule_source(None), SCHEDULE_SOURCE_LOCAL)
        self.assertEqual(parse_schedule_source(""), SCHEDULE_SOURCE_LOCAL)
        self.assertEqual(parse_schedule_source("local"), SCHEDULE_SOURCE_LOCAL)

    def test_google_aliases(self):
        self.assertEqual(parse_schedule_source("google"), SCHEDULE_SOURCE_GOOGLE)
        self.assertEqual(parse_schedule_source("GOOGLE"), SCHEDULE_SOURCE_GOOGLE)


class WorksheetNameCandidatesTests(SimpleTestCase):
    def test_month_sheet_title(self):
        self.assertEqual(month_sheet_title(2026, 7), "Июль 2026")

    @patch("biota_shifts.schedule_google.google_schedule_sheet_template", return_value="")
    def test_default_russian_month_sheet(self, _tpl):
        names = worksheet_name_candidates(2026, 7)
        self.assertEqual(names[0], "Июль 2026")
        self.assertIn("июль 2026", names)

    @patch("biota_shifts.schedule_google.google_schedule_sheet_template", return_value="{month_title}")
    def test_template_month_title(self, _tpl):
        names = worksheet_name_candidates(2026, 5)
        self.assertEqual(names[0], "Май 2026")


class GoogleCacheRefreshTests(SimpleTestCase):
    def test_no_refresh_before_21_msk(self):
        fetched = datetime(2026, 6, 8, 20, 0, tzinfo=MSK)
        now = datetime(2026, 6, 8, 20, 30, tzinfo=MSK)
        self.assertFalse(needs_scheduled_refresh(fetched, now=now))

    def test_refresh_after_21_if_cache_older(self):
        fetched = datetime(2026, 6, 8, 18, 0, tzinfo=MSK)
        now = datetime(2026, 6, 8, 21, 5, tzinfo=MSK)
        self.assertTrue(needs_scheduled_refresh(fetched, now=now))

    def test_no_refresh_after_21_if_already_updated(self):
        fetched = datetime(2026, 6, 8, 21, 10, tzinfo=MSK)
        now = datetime(2026, 6, 8, 22, 0, tzinfo=MSK)
        self.assertFalse(needs_scheduled_refresh(fetched, now=now))


class GoogleMvParseTests(SimpleTestCase):
    def _sample_values(self):
        header = ["", "", "01", "02", "03", "04", "05"]
        row1 = ["19", "Иванов М.С.", "Д", "", "от", "Д", "н"]
        row2 = ["3", "Успенский А.", "", "Д", "Д", "", ""]
        return [header, header, row1, row2]

    def test_parses_mv_layout(self):
        df = google_mv_values_to_schedule_df(self._sample_values(), 2026, 7)
        self.assertEqual(len(df), 2)
        self.assertEqual(str(df.iloc[0]["Код"]), "19")
        self.assertEqual(str(df.iloc[0]["Сотрудник"]), "Иванов М.С.")
        self.assertEqual(str(df.iloc[0]["1"]).strip(), "д")
        self.assertEqual(str(df.iloc[0]["3"]).strip(), "от")
        self.assertEqual(str(df.iloc[0]["5"]).strip(), "н")

    def test_google_cell_aliases(self):
        self.assertEqual(google_cell_to_schedule_code("Д"), "д")
        self.assertEqual(google_cell_to_schedule_code("ОТ"), "от")
        self.assertEqual(google_cell_to_schedule_code("у"), "")


class GraphScheduleSourceSessionTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _request(self, method="get", **kwargs):
        if method == "post":
            req = self.rf.post("/graph/", kwargs)
        else:
            req = self.rf.get("/graph/", kwargs)
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(req)
        req.session.save()
        return req

    @patch("shifts.graph_schedule_source.google_schedule_configured", return_value=True)
    def test_defaults_to_google_when_configured(self, _cfg):
        req = self._request()
        self.assertEqual(get_graph_schedule_source(req), SCHEDULE_SOURCE_GOOGLE)
        self.assertEqual(req.session[SESSION_KEY], SCHEDULE_SOURCE_GOOGLE)

    @patch("shifts.graph_schedule_source.google_schedule_configured", return_value=True)
    def test_local_param_ignored_when_google_configured(self, _cfg):
        req = self._request(schedule_source="local")
        self.assertEqual(get_graph_schedule_source(req), SCHEDULE_SOURCE_GOOGLE)

    @patch("shifts.graph_schedule_source.google_schedule_configured", return_value=False)
    def test_without_config_uses_local(self, _cfg):
        req = self._request(schedule_source="google")
        self.assertEqual(get_graph_schedule_source(req), SCHEDULE_SOURCE_LOCAL)
        self.assertEqual(req.session[SESSION_KEY], SCHEDULE_SOURCE_LOCAL)


class AppendScheduleSourceTests(SimpleTestCase):
    def test_appends_query_param(self):
        url = append_schedule_source("/graph/?year=2026&month=5", SCHEDULE_SOURCE_GOOGLE)
        self.assertIn("schedule_source=google", url)

    def test_local_unchanged(self):
        url = append_schedule_source("/graph/?year=2026&month=5", SCHEDULE_SOURCE_LOCAL)
        self.assertNotIn("schedule_source", url)


class ScheduleGoogleIntegrationTests(TestCase):
    def test_save_with_google_source_calls_google(self):
        from biota_shifts import schedule as biota_schedule
        from biota_shifts.db import _demo_employees

        with tempfile.TemporaryDirectory() as tmp:
            with patch("biota_shifts.schedule.SCHEDULE_DIR", Path(tmp)):
                with patch(
                    "biota_shifts.schedule_google.google_schedule_configured",
                    return_value=True,
                ):
                    with patch(
                        "biota_shifts.schedule_google.google_schedule_read_only",
                        return_value=False,
                    ):
                        with patch(
                            "biota_shifts.schedule_google.save_schedule_dataframe_to_google"
                        ) as save_google_mock:
                            employees = _demo_employees()
                            df = biota_schedule.empty_schedule_from_db(employees, 2026, 5)
                            biota_schedule.save_schedule_table(df, 2026, 5, source="google")
                            save_google_mock.assert_called_once()

    @patch("biota_shifts.schedule_google_cache.load_google_schedule_cached")
    def test_load_from_google(self, fetch_mock):
        from biota_shifts import schedule as biota_schedule
        from biota_shifts.db import _demo_employees

        fetch_mock.return_value = pd.DataFrame(
            {
                "Порядок": [1],
                "Код": ["1001"],
                "Сотрудник": ["Иванов И."],
                "p1": [""],
                "p2": [""],
                "p3": [""],
                **{str(d): [""] for d in range(1, 32)},
            }
        )
        employees = _demo_employees()
        with patch(
            "biota_shifts.schedule_google.google_schedule_configured",
            return_value=True,
        ):
            df = biota_schedule.load_schedule_table(
                employees, 2026, 5, source="google"
            )
        self.assertFalse(df.empty)
        fetch_mock.assert_called()


class HoursScheduleSourceTests(SimpleTestCase):
    @patch("shifts.hours_views.load_schedule_table_resolved")
    @patch("shifts.hours_views.get_skud_schedule_source", return_value=SCHEDULE_SOURCE_GOOGLE)
    def test_hours_loads_google_schedule_when_configured(self, _src_mock, load_mock):
        from biota_shifts.db import _demo_employees
        from shifts.hours_views import _load_schedule_for_hours

        load_mock.return_value = pd.DataFrame({"Код": ["1001"]})
        df = _load_schedule_for_hours(_demo_employees(), 2026, 5)
        load_mock.assert_called_once()
        self.assertEqual(load_mock.call_args.kwargs["source"], SCHEDULE_SOURCE_GOOGLE)
        self.assertFalse(df.empty)
