from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0098_purchaserequest_store_link_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetuptoolrow",
            name="photo",
            field=models.FileField(
                blank=True,
                upload_to="products/setup_tool_photos/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        ["jpg", "jpeg", "png", "webp", "gif"]
                    )
                ],
                verbose_name="Фото инструмента",
            ),
        ),
    ]
