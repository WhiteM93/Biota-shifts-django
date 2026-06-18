"""Тесты уведомлений склада."""
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from biota_shifts.constants import MSK
from biota_shifts.inventory_notify import (
    format_inventory_event_message,
    format_stock_movement_message,
    inventory_notify_enabled,
    movement_operation_title,
    try_notify_stock_movement,
)


class InventoryNotifyFormatTests(SimpleTestCase):
    def _movement(self, **kwargs):
        tool = MagicMock()
        tool.name = "Сверло D7.5"
        tool.quantity = 12
        m = MagicMock()
        m.tool = tool
        m.tool_id = 1
        m.id = 99
        m.movement_type = kwargs.get("movement_type", "restock")
        m.quantity = kwargs.get("quantity", 4)
        m.movement_date = kwargs.get("movement_date", date(2026, 6, 18))
        m.created_at = kwargs.get("created_at", datetime(2026, 6, 18, 14, 35, tzinfo=MSK))
        m.created_by_account = kwargs.get("created_by_account", "maxim")
        m.employee_name = kwargs.get("employee_name", "")
        m.comment = kwargs.get("comment", "Приход (ООО МВ)")
        m.parent_issue_id = kwargs.get("parent_issue_id")
        m.get_movement_type_display = lambda: "Пополнение"
        return m

    def test_format_restock_message(self):
        text = format_stock_movement_message(self._movement())
        self.assertIn("Склад — Пополнение", text)
        self.assertIn("Сверло D7.5", text)
        self.assertIn("4 шт.", text)
        self.assertIn("maxim", text)
        self.assertIn("Приход (ООО МВ)", text)

    def test_format_issue_outcome_return(self):
        m = self._movement(
            movement_type="restock",
            parent_issue_id=55,
            comment="Возврат по выдаче #55. износ",
            employee_name="Иванов",
        )
        self.assertEqual(movement_operation_title(m), "Возврат на склад")
        text = format_stock_movement_message(m)
        self.assertIn("Возврат на склад", text)
        self.assertIn("По выдаче №55", text)

    def test_format_writeoff(self):
        m = self._movement(movement_type="writeoff", comment="брак")
        m.get_movement_type_display = lambda: "Списание"
        text = format_stock_movement_message(m)
        self.assertIn("Склад — Списание", text)

    def test_skip_rollback_compensation_comment(self):
        m = self._movement(comment="Откат движения №1 (выдача 2 шт.).")
        self.assertEqual(movement_operation_title(m), "Откат операции")

    def test_format_inventory_event(self):
        event = MagicMock()
        event.created_at = datetime(2026, 6, 18, 15, 0, tzinfo=MSK)
        event.actor_username = "admin"
        event.get_event_type_display = lambda: "Удаление позиции"
        event.event_type = "tool_delete"
        event.tool = MagicMock(name="Фреза D10")
        event.tool.name = "Фреза D10"
        event.summary = "Помечено удаление позиции: Фреза D10"
        event.stock_movement_id = None
        text = format_inventory_event_message(event)
        self.assertIn("Удаление позиции", text)
        self.assertIn("admin", text)

    @patch("biota_shifts.inventory_notify.send_inventory_notification")
    def test_try_notify_skips_rollback_compensation(self, mock_send):
        m = MagicMock()
        m.tool_id = 1
        m.comment = "Откат движения №5 (выдача 2 шт.)."
        with patch("shifts.models.StockMovement") as mock_model:
            mock_model.objects.select_related.return_value.filter.return_value.first.return_value = m
            try_notify_stock_movement(1)
        mock_send.assert_not_called()

    def test_inventory_notify_env_disable(self):
        with patch("biota_shifts.inventory_notify._config_str", return_value="0"):
            self.assertFalse(inventory_notify_enabled())
