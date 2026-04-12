# Generated manually: separate day/night regulation per employee per date.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("regulations", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="regulationplan",
            name="uniq_regulation_employee_per_day",
        ),
        migrations.AddConstraint(
            model_name="regulationplan",
            constraint=models.UniqueConstraint(
                fields=("plan_date", "employee_code", "shift"),
                name="uniq_regulation_employee_day_shift",
            ),
        ),
    ]
