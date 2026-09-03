from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0128_body_tool_end_mill_shank"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bodytoolspec",
            name="shank_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "—"),
                    ("weldon", "Weldon"),
                    ("bore", "Отверстие (насадная)"),
                    ("cylindrical", "Цилиндрический"),
                ],
                default="",
                max_length=16,
                verbose_name="Тип хвостовика",
            ),
        ),
        migrations.AddField(
            model_name="bodytoolspec",
            name="variable_angle",
            field=models.BooleanField(default=False, verbose_name="С переменным углом"),
        ),
    ]
