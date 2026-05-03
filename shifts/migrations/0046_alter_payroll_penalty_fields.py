from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0045_employee_payroll_settlement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employeepayrollsettlement",
            name="penalty_quality_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name="Вычет из доли «качество», п.п. от начисления (макс. 20)",
            ),
        ),
        migrations.AlterField(
            model_name="employeepayrollsettlement",
            name="penalty_result_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name="Вычет из доли «результат», п.п. от начисления (макс. 20)",
            ),
        ),
        migrations.AlterField(
            model_name="employeepayrollsettlement",
            name="penalty_mode_pct",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name="Вычет из доли «режим», п.п. от начисления (макс. 10)",
            ),
        ),
    ]
