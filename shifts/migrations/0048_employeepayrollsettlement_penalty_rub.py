from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0047_payroll_penalty_effective_pct"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeepayrollsettlement",
            name="penalty_rub",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name="Штраф, ₽",
            ),
        ),
    ]
