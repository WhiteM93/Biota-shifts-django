from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0130_body_tool_high_speed_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="bodytoolspec",
            name="corner_radius_mm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=7,
                null=True,
                verbose_name="Радиус, мм",
            ),
        ),
    ]
