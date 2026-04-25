import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0015_product"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="cad_preview_stl",
            field=models.FileField(
                blank=True,
                upload_to="products/cad_preview/",
                validators=[django.core.validators.FileExtensionValidator(["stl"])],
                verbose_name="Предпросмотр STL (из STEP, сервер)",
            ),
        ),
    ]
