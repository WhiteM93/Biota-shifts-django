from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0053_productsetupprogramfile"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetuptoolrow",
            name="correction_enabled",
            field=models.BooleanField(default=False, verbose_name="Корректор включен"),
        ),
    ]
