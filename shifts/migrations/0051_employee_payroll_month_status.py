from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0050_employeepayrollsettlement_advance_rub"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeePayrollMonthStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("emp_code", models.CharField(db_index=True, max_length=128, verbose_name="Код сотрудника")),
                ("year", models.PositiveSmallIntegerField(verbose_name="Год")),
                ("month", models.PositiveSmallIntegerField(verbose_name="Месяц")),
                (
                    "advance_closed",
                    models.BooleanField(
                        default=False,
                        help_text="Отметка: аванс за период учтён / сверен.",
                        verbose_name="Аванс учтён",
                    ),
                ),
                (
                    "payroll_closed",
                    models.BooleanField(
                        default=False,
                        help_text="Отметка: расчёт заработной платы за месяц по сотруднику закрыт.",
                        verbose_name="Расчёт ЗП завершён",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                ("updated_by", models.CharField(blank=True, default="", max_length=200, verbose_name="Кем обновлено")),
            ],
            options={
                "verbose_name": "Статус ЗП сотрудника за месяц",
                "verbose_name_plural": "Статусы ЗП по месяцам",
            },
        ),
        migrations.AddConstraint(
            model_name="employeepayrollmonthstatus",
            constraint=models.UniqueConstraint(
                fields=("emp_code", "year", "month"),
                name="uniq_employee_payroll_month_status_ym",
            ),
        ),
    ]
