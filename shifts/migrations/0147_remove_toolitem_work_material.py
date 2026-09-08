# Generated manually for RemoveField ToolItem.work_material

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0146_sync_tool_address_from_visual_items"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="toolitem",
            name="work_material",
        ),
    ]
