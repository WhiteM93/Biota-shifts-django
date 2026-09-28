from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0175_inventory_ai_turn"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bodytoolspec",
            name="cutter_type",
            field=models.CharField(
                choices=[
                    ("end", "Концевая"),
                    ("chamfer", "Фасочная"),
                    ("high_speed", "Высокоскоростная"),
                    ("disc", "Т-образная"),
                    ("ball", "Сферическая"),
                    ("thread", "Резьбовая"),
                    ("drill", "Сверло"),
                    ("face", "Торцевая"),
                    ("round_insert", "С круглыми пластинами"),
                    ("modular_head", "Модульная головка"),
                ],
                default="end",
                max_length=20,
                verbose_name="Тип фрезы",
            ),
        ),
        migrations.AlterField(
            model_name="visualcontaineritem",
            name="body_cutter_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Все типы"),
                    ("end", "Концевая"),
                    ("chamfer", "Фасочная"),
                    ("high_speed", "Высокоскоростная"),
                    ("disc", "Т-образная"),
                    ("ball", "Сферическая"),
                    ("thread", "Резьбовая"),
                    ("drill", "Сверло"),
                    ("face", "Торцевая"),
                    ("round_insert", "С круглыми пластинами"),
                    ("modular_head", "Модульная головка"),
                ],
                default="",
                max_length=20,
                verbose_name="Тип корпусной фрезы",
            ),
        ),
    ]
