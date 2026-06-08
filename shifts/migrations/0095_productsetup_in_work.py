from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0094_purchasestore_purchaserequest_store_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="in_work",
            field=models.BooleanField(default=False, verbose_name="В работе"),
        ),
        migrations.AlterModelOptions(
            name="productsetup",
            options={
                "ordering": ("-in_work", "sort_order", "id"),
                "verbose_name": "Установка изделия",
                "verbose_name_plural": "Установки изделий",
            },
        ),
    ]
