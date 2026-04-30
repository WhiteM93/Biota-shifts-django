from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0031_productsetup_preview_stl"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="gcode_system",
            field=models.CharField(blank=True, default="G54", max_length=3, verbose_name="Система координат G"),
        ),
    ]
