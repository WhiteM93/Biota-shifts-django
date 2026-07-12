from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0105_product_catalog_section"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductOsnastkaUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.PositiveSmallIntegerField(default=0, verbose_name="Порядок")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                (
                    "osnastka",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="used_in_naladki",
                        to="shifts.product",
                        verbose_name="Оснастка",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="osnastka_usages",
                        to="shifts.product",
                        verbose_name="Наладка",
                    ),
                ),
            ],
            options={
                "verbose_name": "Используемая оснастка",
                "verbose_name_plural": "Используемая оснастка",
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="productosnastkausage",
            constraint=models.UniqueConstraint(
                fields=("product", "osnastka"),
                name="unique_product_osnastka_usage",
            ),
        ),
    ]
