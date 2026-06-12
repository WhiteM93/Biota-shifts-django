from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0095_productsetup_in_work"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrintForm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Название")),
                (
                    "orientation",
                    models.CharField(
                        choices=[("portrait", "Книжная"), ("landscape", "Альбомная")],
                        default="portrait",
                        max_length=16,
                        verbose_name="Ориентация",
                    ),
                ),
                ("show_border", models.BooleanField(default=True, verbose_name="Рамка листа")),
                ("elements", models.JSONField(blank=True, default=list, verbose_name="Элементы формы")),
                ("created_by", models.CharField(blank=True, default="", max_length=150, verbose_name="Автор")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Печатная форма",
                "verbose_name_plural": "Печатные формы",
                "ordering": ("name", "id"),
            },
        ),
    ]
