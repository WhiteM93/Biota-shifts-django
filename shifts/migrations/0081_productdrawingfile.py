import os

from django.db import migrations, models
import django.core.validators


def migrate_legacy_drawing_pdf(apps, schema_editor):
    Product = apps.get_model("shifts", "Product")
    ProductDrawingFile = apps.get_model("shifts", "ProductDrawingFile")
    for product in Product.objects.exclude(drawing_pdf="").iterator():
        if ProductDrawingFile.objects.filter(product_id=product.pk).exists():
            continue
        name = (product.drawing_pdf.name or "").strip()
        if not name:
            continue
        row = ProductDrawingFile(product_id=product.pk, sort_order=0)
        row.save()
        base = os.path.basename(name.replace("\\", "/"))
        row.file.save(base, product.drawing_pdf, save=True)


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0080_toolmaterialextra"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductDrawingFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "file",
                    models.FileField(
                        upload_to="products/drawings/",
                        validators=[django.core.validators.FileExtensionValidator(["pdf"])],
                        verbose_name="Чертёж (PDF)",
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="drawing_files",
                        to="shifts.product",
                        verbose_name="Изделие",
                    ),
                ),
            ],
            options={
                "verbose_name": "Чертёж изделия (PDF)",
                "verbose_name_plural": "Чертежи изделия (PDF)",
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.RunPython(migrate_legacy_drawing_pdf, migrations.RunPython.noop),
    ]
