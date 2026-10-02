from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0188_cabinet_level_rows"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitenotebooktask",
            name="reject_reason",
            field=models.TextField(blank=True, default="", verbose_name="Причина отказа"),
        ),
        migrations.AlterField(
            model_name="sitenotebooktask",
            name="status",
            field=models.CharField(
                choices=[("open", "Открыта"), ("done", "Выполнено"), ("rejected", "Отказано")],
                db_index=True,
                default="open",
                max_length=12,
                verbose_name="Статус",
            ),
        ),
    ]
