import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0016_product_cad_preview_stl"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="product",
            name="cad_preview_stl",
        ),
        migrations.AddField(
            model_name="product",
            name="preview_stl",
            field=models.FileField(
                blank=True,
                help_text="Упрощённая или экспортированная сетка STL — показывается в карточке изделия. Для STEP/STP загрузите сюда STL отдельно.",
                upload_to="products/preview_stl/",
                validators=[django.core.validators.FileExtensionValidator(["stl"])],
                verbose_name="STL для предпросмотра",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="cad_model",
            field=models.FileField(
                blank=True,
                help_text="Основной файл для скачивания. Для STP/STEP предпросмотр в карточке — только через отдельное поле «STL для предпросмотра».",
                upload_to="products/cad/",
                validators=[
                    django.core.validators.FileExtensionValidator(["stl", "stp", "step"])
                ],
                verbose_name="3D-модель (STL, STP, STEP)",
            ),
        ),
    ]
