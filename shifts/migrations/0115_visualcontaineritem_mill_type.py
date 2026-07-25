from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0114_visual_cabinet_container_kinds"),
    ]

    operations = [
        migrations.AddField(
            model_name="visualcontaineritem",
            name="mill_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Все типы"),
                    ("end", "Концевая фреза"),
                    ("roughing", "Обдирочная фреза"),
                    ("t_slot", "Т-образная фреза"),
                    ("radius", "Радиусная фреза"),
                    ("ball", "Сферическая фреза"),
                ],
                default="",
                max_length=20,
                verbose_name="Тип фрезы",
            ),
        ),
    ]
