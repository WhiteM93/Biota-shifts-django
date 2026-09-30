from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0185_product_created_by_editors"),
    ]

    operations = [
        migrations.AddField(
            model_name="measuringtoolspec",
            name="thread_tolerance",
            field=models.CharField(
                blank=True,
                default="",
                max_length=16,
                verbose_name="Допуск резьбы",
            ),
        ),
        migrations.AlterField(
            model_name="measuringtoolspec",
            name="go_nogo",
            field=models.CharField(
                blank=True,
                choices=[("go", "ПР"), ("nogo", "НЕ"), ("set", "ПР-НЕ")],
                default="",
                max_length=8,
                verbose_name="ПР / НЕ",
            ),
        ),
    ]
