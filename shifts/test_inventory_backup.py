"""Тесты экспорта/восстановления резервной копии склада."""
from django.test import TestCase

from shifts.inventory_backup import (
    export_inventory_payload,
    parse_inventory_backup_bytes,
    payload_to_json_bytes,
    restore_inventory_from_payload,
)
from shifts.models import ToolItem


class InventoryBackupRoundtripTests(TestCase):
    def test_empty_roundtrip(self):
        payload = export_inventory_payload()
        raw = payload_to_json_bytes(payload)
        parsed = parse_inventory_backup_bytes(raw)
        restore_inventory_from_payload(parsed)
        self.assertEqual(ToolItem.objects.count(), 0)

    def test_tool_roundtrip(self):
        tool = ToolItem.objects.create(
            category="drill",
            name="Тестовое сверло",
            quantity=3,
        )
        payload = export_inventory_payload()
        ToolItem.objects.all().delete()
        self.assertEqual(ToolItem.objects.count(), 0)
        restore_inventory_from_payload(payload)
        restored = ToolItem.objects.get(pk=tool.pk)
        self.assertEqual(restored.name, "Тестовое сверло")
        self.assertEqual(restored.quantity, 3)
