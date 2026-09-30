from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0186_thread_gauge_tolerance"),
    ]

    operations = [
        migrations.CreateModel(
            name="WarehouseAddress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("address", models.CharField(db_index=True, max_length=32, unique=True, verbose_name="Адрес")),
                ("label", models.CharField(blank=True, default="", max_length=120, verbose_name="Наименование")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Адрес склада",
                "verbose_name_plural": "Адреса склада",
                "ordering": ("address",),
            },
        ),
    ]
