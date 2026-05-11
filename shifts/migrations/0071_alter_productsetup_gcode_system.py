# Allow extended workpiece offsets (e.g. G54.1 P10).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0070_inventory_stock_event_and_movement_revert"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productsetup",
            name="gcode_system",
            field=models.CharField(
                max_length=24,
                blank=True,
                default="G54",
                verbose_name="Система координат G",
            ),
        ),
    ]
