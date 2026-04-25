import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0014_alter_employeedefectrecord_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=300, verbose_name="Название")),
                ("description", models.TextField(blank=True, default="", verbose_name="Описание")),
                (
                    "drawing_pdf",
                    models.FileField(
                        blank=True,
                        upload_to="products/drawings/",
                        validators=[django.core.validators.FileExtensionValidator(["pdf"])],
                        verbose_name="Чертёж (PDF)",
                    ),
                ),
                (
                    "cad_model",
                    models.FileField(
                        blank=True,
                        upload_to="products/cad/",
                        validators=[
                            django.core.validators.FileExtensionValidator(["stl", "stp", "step"])
                        ],
                        verbose_name="3D-модель (STL, STP, STEP)",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Изделие",
                "verbose_name_plural": "Изделия",
                "ordering": ("-updated_at", "-id"),
            },
        ),
    ]
