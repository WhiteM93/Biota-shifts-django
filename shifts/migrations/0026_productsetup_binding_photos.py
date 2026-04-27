from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0025_alter_product_cad_model_alter_product_preview_stl_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="binding_x_photo",
            field=models.FileField(
                blank=True,
                upload_to="products/setup_bindings/",
                validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
                verbose_name="Фото привязки X",
            ),
        ),
        migrations.AddField(
            model_name="productsetup",
            name="binding_y_photo",
            field=models.FileField(
                blank=True,
                upload_to="products/setup_bindings/",
                validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
                verbose_name="Фото привязки Y",
            ),
        ),
        migrations.AddField(
            model_name="productsetup",
            name="binding_z_photo",
            field=models.FileField(
                blank=True,
                upload_to="products/setup_bindings/",
                validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
                verbose_name="Фото привязки Z",
            ),
        ),
    ]
