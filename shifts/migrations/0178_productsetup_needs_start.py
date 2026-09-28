from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0177_site_notebook_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="needs_start",
            field=models.BooleanField(default=False, verbose_name="Надо запускать"),
        ),
        migrations.AlterModelOptions(
            name="productsetup",
            options={
                "ordering": ("-in_work", "-needs_start", "sort_order", "id"),
                "verbose_name": "Установка изделия",
                "verbose_name_plural": "Установки изделий",
            },
        ),
    ]
