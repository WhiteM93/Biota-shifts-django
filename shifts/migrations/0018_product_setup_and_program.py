import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0017_product_preview_stl_remove_server_preview"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="program_file",
            field=models.FileField(
                blank=True,
                upload_to="products/programs/",
                verbose_name="Программа (G/M-код, без обязательного расширения)",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="setup_notes",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Заготовка, привязка, инструмент, нюансы и т.д.",
                verbose_name="Наладка (текст)",
            ),
        ),
        migrations.CreateModel(
            name="ProductSetupPhoto",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "image",
                    models.FileField(upload_to="products/setup/", verbose_name="Фото"),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="Порядок"),
                ),
                (
                    "caption",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=300,
                        verbose_name="Подпись",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="setup_photos",
                        to="shifts.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Фото наладки (изделие)",
                "verbose_name_plural": "Фото наладки (изделие)",
                "ordering": ("sort_order", "id"),
            },
        ),
    ]
