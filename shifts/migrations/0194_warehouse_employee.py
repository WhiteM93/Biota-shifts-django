from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0193_remove_hr_payroll_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="WarehouseEmployee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True, verbose_name="ФИО / подпись")),
                ("note", models.CharField(blank=True, default="", max_length=200, verbose_name="Заметка")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Активен")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Сотрудник склада",
                "verbose_name_plural": "Сотрудники склада",
                "ordering": ("name", "id"),
            },
        ),
    ]
