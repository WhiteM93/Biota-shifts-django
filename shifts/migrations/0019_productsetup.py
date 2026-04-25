from django.db import migrations, models
import django.db.models.deletion


def seed_initial_setups(apps, schema_editor):
    Product = apps.get_model("shifts", "Product")
    ProductSetup = apps.get_model("shifts", "ProductSetup")

    for product in Product.objects.all().iterator():
        has_setup_notes = bool((product.setup_notes or "").strip())
        has_program = bool(product.program_file)
        if not (has_setup_notes or has_program):
            continue
        if ProductSetup.objects.filter(product=product).exists():
            continue
        ProductSetup.objects.create(
            product=product,
            name="Установка 1",
            setup_notes=product.setup_notes or "",
            program_file=product.program_file,
            sort_order=0,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0018_product_setup_and_program"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductSetup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180, verbose_name="Название установки")),
                ("setup_notes", models.TextField(blank=True, default="", verbose_name="Наладка (текст)")),
                (
                    "program_file",
                    models.FileField(blank=True, upload_to="products/programs/", verbose_name="Программа (G/M, любой файл)"),
                ),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="setups", to="shifts.product"),
                ),
            ],
            options={
                "verbose_name": "Установка изделия",
                "verbose_name_plural": "Установки изделий",
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.RunPython(seed_initial_setups, migrations.RunPython.noop),
    ]
