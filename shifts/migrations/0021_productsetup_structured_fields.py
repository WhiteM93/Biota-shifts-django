from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0020_product_list_preview_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="binding_x",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Привязка X"),
        ),
        migrations.AddField(
            model_name="productsetup",
            name="binding_y",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Привязка Y"),
        ),
        migrations.AddField(
            model_name="productsetup",
            name="binding_z",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Привязка Z"),
        ),
        migrations.AddField(
            model_name="productsetup",
            name="material",
            field=models.CharField(blank=True, default="", max_length=180, verbose_name="Материал"),
        ),
        migrations.AddField(
            model_name="productsetup",
            name="size",
            field=models.CharField(blank=True, default="", max_length=180, verbose_name="Размер"),
        ),
        migrations.AddField(
            model_name="productsetup",
            name="workpiece",
            field=models.CharField(blank=True, default="", max_length=220, verbose_name="Заготовка"),
        ),
    ]
