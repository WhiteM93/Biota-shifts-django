"""Тесты резервного копирования регламентов."""
from datetime import time

from django.test import TestCase

from regulations.models import RegulationPlan
from regulations.regulations_backup import (
    export_regulations_payload,
    parse_regulations_backup_bytes,
    payload_to_json_bytes,
    restore_regulations_from_payload,
)


class RegulationsBackupTests(TestCase):
    def _sample_plan(self, code: str = "100", shift: str = "д") -> RegulationPlan:
        return RegulationPlan.objects.create(
            employee_code=code,
            employee_name=f"Сотрудник {code}",
            department="Цех",
            position="Оператор",
            shift=shift,
            breakfast_start=time(9, 0),
            breakfast_end=time(9, 15),
            lunch_start=time(12, 0),
            lunch_end=time(12, 30),
            breaks=[{"label": "Перекур", "start": "10:00", "end": "10:10", "color_kind": "break"}],
            locked=True,
        )

    def test_roundtrip(self):
        self._sample_plan("101", "д")
        self._sample_plan("101", "н")
        payload = export_regulations_payload()
        self.assertEqual(len(payload["regulation_plans"]), 2)

        RegulationPlan.objects.all().delete()
        self.assertEqual(RegulationPlan.objects.count(), 0)

        restore_regulations_from_payload(payload)
        self.assertEqual(RegulationPlan.objects.count(), 2)
        row = RegulationPlan.objects.get(employee_code="101", shift="д")
        self.assertTrue(row.locked)
        self.assertEqual(len(row.breaks), 1)

    def test_parse_bytes(self):
        plan = self._sample_plan()
        raw = payload_to_json_bytes(export_regulations_payload())
        parsed = parse_regulations_backup_bytes(raw)
        RegulationPlan.objects.all().delete()
        restore_regulations_from_payload(parsed)
        restored = RegulationPlan.objects.get(pk=plan.pk)
        self.assertEqual(restored.employee_code, "100")
