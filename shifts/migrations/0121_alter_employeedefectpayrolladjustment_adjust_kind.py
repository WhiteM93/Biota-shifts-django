from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0120_calculatormodesstate"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employeedefectpayrolladjustment",
            name="adjust_kind",
            field=models.CharField(
                choices=[
                    ("bonus_percent", "Премия — % (пункты)"),
                    ("bonus_rub", "Премия — ₽"),
                    ("penalty_quality_pct", "Качество — % (0…20)"),
                    ("penalty_result_pct", "Результат — % (0…20)"),
                    ("penalty_mode_pct", "Режим — % (0…10)"),
                    ("penalty_rub", "Штраф — ₽"),
                ],
                max_length=40,
                verbose_name="Поле в карточке ЗП",
            ),
        ),
    ]
