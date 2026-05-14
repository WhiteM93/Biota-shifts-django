"""Разовое заполнение связей План ↔ Наладки для записей до внедрения сигнала post_save."""

from django.db import migrations, transaction


def forwards_sync(apps, schema_editor):
    from shifts.models import PlannedProduct, Product
    from shifts.plan_naladki_bridge import (
        finalize_plan_piece_naladki_link,
        sync_plan_piece_for_naladki_in_same_transaction,
    )

    for pk in Product.objects.order_by("id").values_list("pk", flat=True).iterator(chunk_size=500):
        with transaction.atomic():
            sync_plan_piece_for_naladki_in_same_transaction(pk)
    for pk in (
        PlannedProduct.objects.filter(is_assembly=False, is_purchased=False)
        .order_by("id")
        .values_list("pk", flat=True)
        .iterator(chunk_size=500)
    ):
        with transaction.atomic():
            finalize_plan_piece_naladki_link(pk)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0064_merge_toolrow_correction_and_plan"),
    ]

    operations = [
        migrations.RunPython(forwards_sync, backwards_noop),
    ]
