from django.db import migrations


def regroup_forward(apps, schema_editor):
    # Runtime helper: схема StockToolType уже актуальна после 0138/0139.
    from shifts.stock_tool_type_seed import regroup_stock_tool_types_into_groups

    regroup_stock_tool_types_into_groups()


def regroup_backward(apps, schema_editor):
    """Откат только удаляет группы; подтипы обратно в типы не восстанавливаем."""
    StockToolType = apps.get_model("shifts", "StockToolType")
    StockToolType.objects.filter(code__in=("cutting", "tooling")).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0139_seed_stock_tool_types"),
    ]

    operations = [
        migrations.RunPython(regroup_forward, regroup_backward),
    ]
