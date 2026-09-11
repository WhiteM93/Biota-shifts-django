# Generated manually for InsertSpec.brand

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0152_bodytoolspec_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="insertspec",
            name="brand",
            field=models.CharField(blank=True, default="", max_length=80, verbose_name="Бренд"),
        ),
    ]
