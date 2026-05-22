from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0078_plannedproduct_workpiece_size_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserHomeLowStockPrefs",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=200, unique=True, verbose_name="Аккаунт")),
                ("category", models.CharField(blank=True, default="", max_length=20, verbose_name="Категория (пусто — все)")),
                ("max_qty", models.PositiveSmallIntegerField(default=10, verbose_name="Показывать остаток меньше (шт.)")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Главная: фильтр мало на складе",
                "verbose_name_plural": "Главная: фильтры мало на складе",
            },
        ),
    ]
