from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0049_employeedefectrecord_potential_defect_quantity"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeepayrollsettlement",
            name="advance_rub",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Уже выплаченный или запланированный аванс за месяц — для сверки с расчётом «к выплате».",
                max_digits=12,
                verbose_name="Аванс, ₽",
            ),
        ),
    ]
