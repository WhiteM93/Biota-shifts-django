from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0026_productsetup_binding_photos"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="workpiece_photo",
            field=models.FileField(
                blank=True,
                upload_to="products/setup_bindings/",
                validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
                verbose_name="Фото заготовки",
            ),
        ),
    ]
