# Generated manually for MachinesBoardState singleton.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0073_product_cad_step_model"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachinesBoardState",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Данные (JSON)")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Станки: общая сводка",
                "verbose_name_plural": "Станки: общая сводка",
            },
        ),
    ]
