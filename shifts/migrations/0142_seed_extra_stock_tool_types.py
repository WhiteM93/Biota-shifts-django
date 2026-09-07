from django.db import migrations


def seed_forward(apps, schema_editor):
    from shifts.stock_tool_type_seed import ensure_extra_stock_tool_types

    ensure_extra_stock_tool_types()


def seed_backward(apps, schema_editor):
    StockToolType = apps.get_model("shifts", "StockToolType")
    codes = [
        "abrasives",
        "ppe",
        "tools",
        "measuring",
        "fasteners",
        "tech-chemistry",
    ]
    StockToolType.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0141_restore_body_tool_cutter_catalog"),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
