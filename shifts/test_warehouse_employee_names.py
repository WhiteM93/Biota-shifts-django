from django.test import SimpleTestCase

from shifts.warehouse_employee_names import (
    format_warehouse_employee_name,
    pick_merge_keep_name,
    resolve_warehouse_employee_names,
)


class FormatWarehouseEmployeeNameTests(SimpleTestCase):
    def test_full_fio(self):
        self.assertEqual(
            format_warehouse_employee_name("Иванов Алексей Петрович"),
            "Иванов А.П.",
        )

    def test_already_short(self):
        self.assertEqual(format_warehouse_employee_name("Иванов М.С."), "Иванов М.С.")
        self.assertEqual(format_warehouse_employee_name("Иванов М.С"), "Иванов М.С.")
        self.assertEqual(format_warehouse_employee_name("Борисов АВ"), "Борисов А.В.")

    def test_surname_only(self):
        self.assertEqual(format_warehouse_employee_name("Павлов"), "Павлов")

    def test_casefold(self):
        self.assertEqual(format_warehouse_employee_name("успенский а.л."), "Успенский А.Л.")

    def test_resolve_merges_prefix_initials(self):
        mapping = resolve_warehouse_employee_names(
            ["Иванов М.", "Иванов М.С.", "Иванов М.С", "Павлов", "Павлов В.", "Павлов В.И."]
        )
        self.assertEqual(mapping["Иванов М."], "Иванов М.С.")
        self.assertEqual(mapping["Иванов М.С"], "Иванов М.С.")
        self.assertEqual(mapping["Павлов В."], "Павлов В.И.")
        # Фамилия без инициалов не подменяется.
        self.assertEqual(mapping["Павлов"], "Павлов")

    def test_pick_merge_keep_name(self):
        self.assertEqual(
            pick_merge_keep_name(["Белянкин", "Белянкин А."]),
            "Белянкин А.",
        )
