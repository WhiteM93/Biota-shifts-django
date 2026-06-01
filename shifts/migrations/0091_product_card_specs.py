# Характеристики изделия на карточке наладки (Product), без PlannedProduct.

from django.db import migrations, models


def _material_from_plan_piece(pp, product_id, ProductSetup):
    wp = (pp.workpiece_type or "").strip()
    if wp == "laser":
        return (pp.laser_material_marking or "").strip()
    setup = (
        ProductSetup.objects.filter(product_id=product_id)
        .order_by("sort_order", "id")
        .first()
    )
    return (setup.material or "").strip() if setup else ""


def backfill_product_card_specs(apps, schema_editor):
    Product = apps.get_model("shifts", "Product")
    PlannedProduct = apps.get_model("shifts", "PlannedProduct")
    ProductSetup = apps.get_model("shifts", "ProductSetup")

    for product in Product.objects.all().iterator():
        pp = PlannedProduct.objects.filter(naladki_product_id=product.pk).first()
        if not pp:
            nm = (product.name or "").strip()
            if nm:
                pp = (
                    PlannedProduct.objects.filter(name__iexact=nm)
                    .order_by("-updated_at", "-id")
                    .first()
                )

        if pp:
            if pp.is_assembly:
                product.card_product_type = "assembly"
            elif pp.is_purchased:
                product.card_product_type = "pki"
            else:
                product.card_product_type = "made"
                product.card_workpiece_type = (pp.workpiece_type or "").strip()
            product.card_laser_thickness_mm = pp.laser_sheet_thickness_mm
            product.card_workpiece_size = (pp.workpiece_size or "").strip()
            product.card_workpiece_type_enum = (pp.workpiece_type_enum or "").strip()
            product.card_material = _material_from_plan_piece(pp, product.pk, ProductSetup)[:240]
        else:
            setup = (
                ProductSetup.objects.filter(product_id=product.pk)
                .order_by("sort_order", "id")
                .first()
            )
            if setup and (setup.material or "").strip():
                product.card_material = (setup.material or "").strip()[:240]

        if (product.drawing_blank_size or "").strip() and not (product.card_workpiece_size or "").strip():
            product.card_workpiece_size = (product.drawing_blank_size or "").strip()[:100]

        product.save(
            update_fields=[
                "card_product_type",
                "card_workpiece_type",
                "card_laser_thickness_mm",
                "card_material",
                "card_workpiece_size",
                "card_workpiece_type_enum",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0090_colletspec_inner_diameter"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="card_product_type",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Деталь / сборка / ПКИ — блок параметров на вкладке «Изделие».",
                max_length=20,
                verbose_name="Тип изделия (карточка)",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="card_workpiece_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("preparatory", "Ленточная пила"),
                    ("laser", "Лазерная резка"),
                    ("pki", "ПКИ"),
                ],
                default="",
                max_length=20,
                verbose_name="Вид заготовки (карточка)",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="card_laser_thickness_mm",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=8,
                null=True,
                verbose_name="Толщина листа (карточка), мм",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="card_material",
            field=models.CharField(
                blank=True,
                default="",
                max_length=240,
                verbose_name="Материал (карточка)",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="card_workpiece_size",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Размер заготовки (карточка)",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="card_workpiece_type_enum",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="Тип заготовки — плита/круг/пруток (карточка)",
            ),
        ),
        migrations.RunPython(backfill_product_card_specs, migrations.RunPython.noop),
    ]
