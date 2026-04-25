from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0019_productsetup"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="list_preview_image",
            field=models.FileField(
                blank=True,
                help_text="Сохраняется из 3D-окна кнопкой «Сохранить превью».",
                upload_to="products/list_previews/",
                validators=[django.core.validators.FileExtensionValidator(["png", "jpg", "jpeg", "webp"])],
                verbose_name="Превью для списка изделий (PNG)",
            ),
        ),
    ]
