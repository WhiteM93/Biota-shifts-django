# Generated manually for BodyToolSpec.photo

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0151_alter_body_cutter_end_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="bodytoolspec",
            name="photo",
            field=models.FileField(
                blank=True,
                upload_to="inventory/body_tool_photos/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        ["jpg", "jpeg", "png", "webp", "gif"]
                    )
                ],
                verbose_name="Фото",
            ),
        ),
    ]
