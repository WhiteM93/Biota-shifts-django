from django.db import migrations


def restore_forward(apps, schema_editor):
    from shifts.stock_tool_type_seed import restore_body_tool_cutter_catalog

    restore_body_tool_cutter_catalog(replace_fields=True)


def restore_backward(apps, schema_editor):
    StockToolType = apps.get_model("shifts", "StockToolType")
    StockToolType.objects.filter(code="body-tool").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0140_regroup_stock_tool_types"),
    ]

    operations = [
        migrations.RunPython(restore_forward, restore_backward),
    ]
