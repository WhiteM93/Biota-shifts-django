from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0096_printform"),
    ]

    operations = [
        migrations.AddField(
            model_name="printform",
            name="page_settings",
            field=models.JSONField(blank=True, default=dict, verbose_name="Параметры листа и рамки"),
        ),
    ]
