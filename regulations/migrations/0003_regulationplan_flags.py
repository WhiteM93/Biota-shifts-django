from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("regulations", "0002_regulationplan_shift_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="regulationplan",
            name="locked",
            field=models.BooleanField(default=False, verbose_name="Заблокировано"),
        ),
        migrations.AddField(
            model_name="regulationplan",
            name="is_smoker",
            field=models.BooleanField(default=False, verbose_name="Курит"),
        ),
        migrations.AddField(
            model_name="regulationplan",
            name="eight_hour_shift",
            field=models.BooleanField(
                default=False,
                verbose_name="Смена 8 ч (один перерыв на питание)",
            ),
        ),
    ]
