from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0187_warehouseaddress"),
    ]

    operations = [
        migrations.AddField(
            model_name="visualcabinetlevel",
            name="rows",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Сколько рядов тары друг на друге (1–4). Место = коробка/контейнер.",
                verbose_name="Рядов на полке",
            ),
        ),
    ]
