from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0048_employeepayrollsettlement_penalty_rub"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeedefectrecord",
            name="potential_defect_quantity",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Количество с потенциальным дефектом (учёт отдельно от подтверждённого брака).",
                verbose_name="Потенциальный брак",
            ),
        ),
    ]
