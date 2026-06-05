from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0093_sectionactionlog"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseStore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True, verbose_name="Магазин")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Магазин (закупки)",
                "verbose_name_plural": "Магазины (закупки)",
                "ordering": ("name",),
            },
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="store_name",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="Магазин"),
        ),
    ]
