from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("regulations", "0004_normalize_plan_date_to_month_start"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="regulationplan",
            name="is_smoker",
        ),
    ]
