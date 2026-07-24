from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0113_visual_container_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="visualcabinet",
            name="kind",
            field=models.CharField(
                choices=[("cabinet", "Шкаф"), ("rack", "Стеллаж")],
                default="cabinet",
                max_length=16,
                verbose_name="Тип",
            ),
        ),
        migrations.AddField(
            model_name="visualcontainer",
            name="kind",
            field=models.CharField(
                choices=[("bin", "Контейнер"), ("shelf_slot", "На полке")],
                default="bin",
                max_length=16,
                verbose_name="Тип",
            ),
        ),
        migrations.AlterField(
            model_name="visualcontainer",
            name="color",
            field=models.CharField(
                blank=True,
                default="#e74c3c",
                max_length=7,
                verbose_name="Цвет этикетки",
            ),
        ),
    ]
