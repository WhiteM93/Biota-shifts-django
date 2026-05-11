# Optional STEP/STP alongside main cad_model (e.g. STL in cad_model + STEP here).

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0072_alter_toolitem_tool_material"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="cad_step_model",
            field=models.FileField(
                blank=True,
                help_text="Дополнительно к основной 3D: не показывается в окне, только ссылка в боковой панели.",
                upload_to="products/cad_step/",
                validators=[django.core.validators.FileExtensionValidator(["stp", "step"])],
                verbose_name="STEP/STP для скачивания",
            ),
        ),
    ]
