import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0051_employee_payroll_month_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeDefectPayrollAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "adjust_kind",
                    models.CharField(
                        choices=[
                            ("bonus_percent", "Премия, % от начисления по табелю"),
                            ("bonus_rub", "Премия, ₽ (фикс)"),
                            ("penalty_quality_pct", "Качество, % от начисления (0–20)"),
                            ("penalty_result_pct", "Результат, % от начисления (0–20)"),
                            ("penalty_mode_pct", "Режим, % от начисления (0–10)"),
                            ("penalty_rub", "Штраф, ₽"),
                        ],
                        max_length=40,
                        verbose_name="Поле в карточке ЗП",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Суммируется с соответствующим полем в расчёте; для процентов — п.п.; допускается «−».",
                        max_digits=12,
                        verbose_name="Добавка",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                ("updated_by", models.CharField(blank=True, default="", max_length=200, verbose_name="Кем обновлено")),
                (
                    "defect_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payroll_adjustments",
                        to="shifts.employeedefectrecord",
                        verbose_name="Запись брака",
                    ),
                ),
            ],
            options={
                "verbose_name": "Корректировка ЗП по записи брака",
                "verbose_name_plural": "Корректировки ЗП по браку",
            },
        ),
        migrations.AddConstraint(
            model_name="employeedefectpayrolladjustment",
            constraint=models.UniqueConstraint(
                fields=("defect_record", "adjust_kind"),
                name="uniq_defect_payroll_adj_kind",
            ),
        ),
    ]
