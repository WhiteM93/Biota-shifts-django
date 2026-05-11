# Generated manually for per-account inventory stock filter persistence.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0068_product_note_setup"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserInventoryStockFilterPrefs",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=200, unique=True, verbose_name="Аккаунт")),
                ("params", models.JSONField(blank=True, default=dict, verbose_name="Параметры фильтра")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Фильтр наличия (сохранённые параметры)",
                "verbose_name_plural": "Фильтры наличия (сохранённые параметры)",
            },
        ),
    ]
