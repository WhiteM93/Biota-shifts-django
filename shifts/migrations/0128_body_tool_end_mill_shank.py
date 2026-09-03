from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0127_strip_inventory_supplier_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="bodytoolspec",
            name="shank_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "—"),
                    ("weldon", "Weldon"),
                    ("cylindrical", "Цилиндрический"),
                ],
                default="",
                max_length=16,
                verbose_name="Тип хвостовика",
            ),
        ),
        migrations.AlterField(
            model_name="bodytoolspec",
            name="cutter_type",
            field=models.CharField(
                choices=[
                    ("face", "Торцевые насадные фрезы"),
                    ("end", "Концевые насадные фрезы"),
                    ("chamfer", "Фасочные фрезы"),
                    ("high_speed", "Высокоскоростные фрезы"),
                    ("round_insert", "Фрезы с круглыми пластинами"),
                    ("disc", "Дисковые фрезы"),
                    ("ball", "Сферические фрезы"),
                    ("modular_head", "Фрезерные головки с пластинами"),
                ],
                default="face",
                max_length=20,
                verbose_name="Тип фрезы",
            ),
        ),
    ]
