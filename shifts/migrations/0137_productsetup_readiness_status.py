from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0136_visual_container_item_detail_filters"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsetup",
            name="readiness_status",
            field=models.CharField(
                choices=[
                    ("not_ready", "Наладка не готова"),
                    ("ready", "Наладка готова"),
                    ("worked", "Наладка отработана"),
                ],
                default="not_ready",
                max_length=16,
                verbose_name="Статус наладки",
            ),
        ),
    ]
