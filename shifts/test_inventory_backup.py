"""Тесты экспорта/восстановления резервной копии склада."""
from django.test import TestCase

from shifts.inventory_backup import (
    export_inventory_payload,
    parse_inventory_backup_bytes,
    payload_to_json_bytes,
    restore_inventory_from_payload,
)
from shifts.models import (
    BodyToolSpec,
    ToolItem,
    VisualCabinet,
    VisualContainer,
    VisualContainerAudit,
    VisualContainerAuditLine,
    VisualContainerItem,
)


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

    def test_body_tool_photo_field_is_json_serializable(self):
        tool = ToolItem.objects.create(
            category="body",
            name="Корпус тест",
            quantity=1,
        )
        BodyToolSpec.objects.create(tool=tool)
        payload = export_inventory_payload()
        row = next(r for r in payload["body_tool_specs"] if r.get("tool_id") == tool.pk)
        self.assertIsInstance(row.get("photo"), str)
        raw = payload_to_json_bytes(payload)
        self.assertTrue(raw)
        restore_inventory_from_payload(parse_inventory_backup_bytes(raw))
        self.assertEqual(BodyToolSpec.objects.filter(tool_id=tool.pk).count(), 1)

    def test_restore_clears_visual_audit_protect_and_keeps_placement(self):
        tool = ToolItem.objects.create(category="drill", name="Сверло", quantity=2)
        cab = VisualCabinet.objects.create(code="Z", name="Шкаф", shelves=2, columns=2)
        cont = VisualContainer.objects.create(
            cabinet=cab, shelf=1, stack=1, column=1, label="Ящик", address="Z-01-01"
        )
        placement = VisualContainerItem.objects.create(
            container=cont, title="Сверло", tool_item=tool, sort_order=0
        )
        audit = VisualContainerAudit.objects.create(container=cont, audited_by="admin", changes_count=1)
        VisualContainerAuditLine.objects.create(
            audit=audit,
            tool=tool,
            expected_qty=1,
            counted_qty=2,
            delta=1,
            status=VisualContainerAuditLine.STATUS_ADJUSTED,
        )

        payload = export_inventory_payload()
        restore_inventory_from_payload(payload)

        self.assertEqual(ToolItem.objects.filter(pk=tool.pk).count(), 1)
        self.assertEqual(VisualContainerAudit.objects.count(), 0)
        self.assertEqual(VisualContainerAuditLine.objects.count(), 0)
        placement.refresh_from_db()
        self.assertEqual(placement.tool_item_id, tool.pk)
