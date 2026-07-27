from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0115_visualcontaineritem_mill_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="visualcabinet",
            name="kind",
            field=models.CharField(
                choices=[
                    ("cabinet", "Шкаф"),
                    ("rack", "Стеллаж"),
                    ("drawer_chest", "Тумба с ящиками"),
                ],
                default="cabinet",
                max_length=16,
                verbose_name="Тип",
            ),
        ),
        migrations.AlterField(
            model_name="visualcontainer",
            name="kind",
            field=models.CharField(
                choices=[
                    ("bin", "Контейнер"),
                    ("shelf_slot", "На полке"),
                    ("drawer_cell", "Ячейка ящика"),
                ],
                default="bin",
                max_length=16,
                verbose_name="Тип",
            ),
        ),
    ]
