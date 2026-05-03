from decimal import Decimal

from django.db import migrations, models


def _to_effective(val, cap: Decimal) -> Decimal:
    """Раньше в полях хранился «вычет» d (0…cap); теперь — выплачиваемый % e = cap − d."""
    v = Decimal(str(val or 0))
    capd = Decimal(str(cap))
    d = min(max(v, Decimal("0")), capd)
    return capd - d


def forwards_convert_deduction_to_effective(apps, schema_editor):
    """Было: в полях хранился вычет d из доли cap. Стало: выплачиваемый % e = cap − d.

    Если вы уже вручную вводили именно «выплачиваемые %», после миграции пересохраните карточку с нужными значениями.
    """
    EmployeePayrollSettlement = apps.get_model("shifts", "EmployeePayrollSettlement")
    for s in EmployeePayrollSettlement.objects.all():
        s.penalty_quality_pct = _to_effective(s.penalty_quality_pct, Decimal("20"))
        s.penalty_result_pct = _to_effective(s.penalty_result_pct, Decimal("20"))
        s.penalty_mode_pct = _to_effective(s.penalty_mode_pct, Decimal("10"))
        s.save(
            update_fields=[
                "penalty_quality_pct",
                "penalty_result_pct",
                "penalty_mode_pct",
            ]
        )


def backwards_noop(apps, schema_editor):
    """Обратный переход не восстанавливает старую семантику без потерь."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0046_alter_payroll_penalty_fields"),
    ]

    operations = [
        migrations.RunPython(forwards_convert_deduction_to_effective, backwards_noop),
        migrations.AlterField(
            model_name="employeepayrollsettlement",
            name="penalty_quality_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=20,
                max_digits=5,
                verbose_name="Качество, % от начисления по табелю (макс. 20)",
            ),
        ),
        migrations.AlterField(
            model_name="employeepayrollsettlement",
            name="penalty_result_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=20,
                max_digits=5,
                verbose_name="Результат, % от начисления по табелю (макс. 20)",
            ),
        ),
        migrations.AlterField(
            model_name="employeepayrollsettlement",
            name="penalty_mode_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=10,
                max_digits=5,
                verbose_name="Режим, % от начисления по табелю (макс. 10)",
            ),
        ),
    ]
