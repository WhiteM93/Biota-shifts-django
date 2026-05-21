"""Тесты сохранения графика: привязка ячеек к коду сотрудника, не к индексу фильтра."""
import re
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from biota_shifts import schedule as biota_schedule
from biota_shifts.db import _demo_employees
from shifts.graph_views import (
    _parse_schedule_cell_post_key,
    _schedule_with_department,
    _sort_graph_rows,
    _dept_rank_map,
    _pos_rank_map,
    apply_schedule_cells_from_post,
)


class ParseCellKeyTests(SimpleTestCase):
    def test_parses_code_and_day(self):
        keys = ["p1", "p2", "p3", "4", "05", "12"]
        self.assertEqual(_parse_schedule_cell_post_key("cell_1001_4", keys), ("1001", "4"))
        self.assertEqual(_parse_schedule_cell_post_key("cell_1003_p2", keys), ("1003", "p2"))
        self.assertEqual(_parse_schedule_cell_post_key("cell_1010_05", keys), ("1010", "05"))

    def test_legacy_index_keys_do_not_match_real_employees(self):
        """cell_0_4 / cell_1_5 — не коды сотрудников, в БД не найдутся."""
        keys = ["4", "5"]
        self.assertEqual(_parse_schedule_cell_post_key("cell_1_5", keys), ("1", "5"))
        self.assertEqual(_parse_schedule_cell_post_key("cell_0_4", keys), ("0", "4"))


class GraphSaveByEmpCodeTests(TestCase):
    def setUp(self):
        self.employees_df = _demo_employees()
        self.year, self.month = 2026, 5
        self.rf = RequestFactory()
        self._schedule_tmp = tempfile.TemporaryDirectory()
        self._schedule_patch = patch(
            "biota_shifts.schedule.SCHEDULE_DIR",
            Path(self._schedule_tmp.name),
        )
        self._schedule_patch.start()
        biota_schedule.save_schedule_table(
            biota_schedule.empty_schedule_from_db(self.employees_df, self.year, self.month),
            self.year,
            self.month,
        )

    def tearDown(self):
        self._schedule_patch.stop()
        self._schedule_tmp.cleanup()

    def _full_schedule(self):
        return biota_schedule.load_schedule_table(self.employees_df, self.year, self.month)

    def _sorted_all(self, sched):
        dep_rank = _dept_rank_map(sorted(sched["Отдел"].unique().tolist()))
        pos_rank = _pos_rank_map(sorted(sched["Должность"].unique().tolist()))
        return _sort_graph_rows(sched, dep_rank, pos_rank).reset_index(drop=True)

    def _sorted_mech(self, sched):
        mech = sched[sched["Отдел"] == "Механический цех"].copy()
        dep_rank = _dept_rank_map(sorted(sched["Отдел"].unique().tolist()))
        pos_rank = _pos_rank_map(sorted(sched["Должность"].unique().tolist()))
        return _sort_graph_rows(mech, dep_rank, pos_rank).reset_index(drop=True)

    def test_mech_row1_is_ivanov_all_row1_is_not(self):
        """На экране мехцеха строка 1 — Иванов; в общем списке строка 1 — другой человек."""
        sched = _schedule_with_department(self._full_schedule(), self.employees_df)
        mech = self._sorted_mech(sched)
        all_rows = self._sorted_all(sched)
        self.assertEqual(str(mech.iloc[1]["Код"]), "1001")
        self.assertNotEqual(str(all_rows.iloc[1]["Код"]), "1001")

    def test_save_by_emp_code_hits_ivanov_not_all_list_row1(self):
        sched = _schedule_with_department(self._full_schedule(), self.employees_df)
        all_rows = self._sorted_all(sched)
        wrong_code = str(all_rows.iloc[1]["Код"])

        full = self._full_schedule()
        request = self.rf.post(
            "/graph/",
            {"cell_1001_5": "н", "dep_mode": "all", "pos_mode": "all"},
        )
        out = apply_schedule_cells_from_post(full.copy(), request, year=self.year, month=self.month)

        ivanov_val = str(out.loc[out["Код"].astype(str) == "1001", "5"].iloc[0]).strip().lower()
        wrong_val = str(out.loc[out["Код"].astype(str) == wrong_code, "5"].iloc[0]).strip().lower()
        self.assertEqual(ivanov_val, "н")
        self.assertNotEqual(wrong_val, "н")

    def test_legacy_cell_row_index_does_not_update_ivanov(self):
        """Старый POST cell_1_5 (индекс строки) не должен записать «н» Иванову."""
        full = self._full_schedule()
        full.loc[full["Код"].astype(str) == "1001", "5"] = ""
        request = self.rf.post("/graph/", {"cell_1_5": "н", "dep_mode": "all"})
        out = apply_schedule_cells_from_post(full.copy(), request, year=self.year, month=self.month)
        ivanov_val = str(out.loc[out["Код"].astype(str) == "1001", "5"].iloc[0]).strip().lower()
        self.assertEqual(ivanov_val, "")

    def test_correct_code_post_updates_petrov(self):
        full = self._full_schedule()
        request = self.rf.post("/graph/", {"cell_1002_5": "кп"})
        out = apply_schedule_cells_from_post(full.copy(), request, year=self.year, month=self.month)
        petrov_val = str(out.loc[out["Код"].astype(str) == "1002", "5"].iloc[0]).strip().lower()
        self.assertEqual(petrov_val, "кп")

    def test_partial_post_does_not_touch_other_employees(self):
        """Как при сохранении только изменённых ячеек (кисть / dirty)."""
        full = self._full_schedule()
        full.loc[full["Код"].astype(str) == "1007", "5"] = "д"
        request = self.rf.post("/graph/", {"cell_1001_5": "н"})
        out = apply_schedule_cells_from_post(full.copy(), request, year=self.year, month=self.month)
        self.assertEqual(
            str(out.loc[out["Код"].astype(str) == "1001", "5"].iloc[0]).strip().lower(),
            "н",
        )
        self.assertEqual(
            str(out.loc[out["Код"].astype(str) == "1007", "5"].iloc[0]).strip().lower(),
            "д",
        )


class GraphViewIntegrationTests(TestCase):
    def setUp(self):
        self._schedule_tmp = tempfile.TemporaryDirectory()
        self._schedule_patch = patch(
            "biota_shifts.schedule.SCHEDULE_DIR",
            Path(self._schedule_tmp.name),
        )
        self._schedule_patch.start()
        biota_schedule.save_schedule_table(
            biota_schedule.empty_schedule_from_db(_demo_employees(), 2026, 5),
            2026,
            5,
        )
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()

    def tearDown(self):
        self._schedule_patch.stop()
        self._schedule_tmp.cleanup()

    @patch("shifts.graph_views._employees_for_user")
    def test_filtered_html_uses_emp_code_cell_names(self, mock_employees):
        mock_employees.return_value = _demo_employees()
        dep = quote("Механический цех")
        url = f"/graph/?year=2026&month=5&dep_mode=pick&dep={dep}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="cell_1001_', html)
        self.assertIn('name="cell_1003_', html)
        # Индекс строки (0–9), не код сотрудника (1001…)
        self.assertIsNone(re.search(r'name="cell_[0-9]_', html))

    @patch("shifts.graph_views._employees_for_user")
    def test_post_save_ivanov_under_mech_filter_wrong_dep_mode(self, mock_employees):
        """POST как при баге: dep_mode=all, но ячейки по коду — только Иванов."""
        mock_employees.return_value = _demo_employees()
        dep = quote("Механический цех")
        get_url = f"/graph/?year=2026&month=5&dep_mode=pick&dep={dep}"
        page = self.client.get(get_url)
        csrf = re.search(r'csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
        self.assertIsNotNone(csrf)
        token = csrf.group(1)

        post_data = {
            "csrfmiddlewaretoken": token,
            "action": "save",
            "year": "2026",
            "month": "5",
            "dep_mode": "all",
            "pos_mode": "all",
            "cell_1001_5": "н",
        }
        resp = self.client.post(
            get_url,
            post_data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))

        full = biota_schedule.load_schedule_table(_demo_employees(), 2026, 5)
        ivanov = str(full.loc[full["Код"].astype(str) == "1001", "5"].iloc[0]).strip().lower()
        all_rows = _schedule_with_department(full, _demo_employees())
        dep_rank = _dept_rank_map(sorted(all_rows["Отдел"].unique().tolist()))
        pos_rank = _pos_rank_map(sorted(all_rows["Должность"].unique().tolist()))
        sorted_all = _sort_graph_rows(all_rows, dep_rank, pos_rank).reset_index(drop=True)
        wrong_code = str(sorted_all.iloc[1]["Код"])
        wrong_val = str(full.loc[full["Код"].astype(str) == wrong_code, "5"].iloc[0]).strip().lower()
        self.assertEqual(ivanov, "н")
        self.assertNotEqual(wrong_val, "н")
