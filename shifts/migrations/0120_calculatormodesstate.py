# Generated manually for CalculatorModesState singleton.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0119_visualcontaineritem_hole_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="CalculatorModesState",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Данные (JSON)")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "updated_by",
                    models.CharField(blank=True, default="", max_length=200, verbose_name="Кто обновил"),
                ),
            ],
            options={
                "verbose_name": "Калькулятор: общая база режимов",
                "verbose_name_plural": "Калькулятор: общая база режимов",
            },
        ),
    ]
