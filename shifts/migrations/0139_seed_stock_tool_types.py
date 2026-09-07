from django.db import migrations


def seed_forward(apps, schema_editor):
    # Импорт runtime-хелпера: модели уже на актуальной схеме после 0138.
    from shifts.stock_tool_type_seed import seed_stock_tool_types

    seed_stock_tool_types(replace_fields=False)


def seed_backward(apps, schema_editor):
    StockToolType = apps.get_model("shifts", "StockToolType")
    codes = [
        "end-mill",
        "tap",
        "center-drill",
        "countersink",
        "drill",
        "insert",
        "collet",
        "body-tool",
    ]
    StockToolType.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0138_stock_tool_types"),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
