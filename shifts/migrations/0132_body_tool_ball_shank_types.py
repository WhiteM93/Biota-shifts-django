from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0131_body_tool_round_insert_radius"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bodytoolspec",
            name="shank_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "—"),
                    ("mt3", "МТ3"),
                    ("mt4", "МТ4"),
                    ("weldon", "Weldon"),
                    ("bore", "Отверстие (насадная)"),
                    ("cylindrical", "Цилиндрический"),
                ],
                default="",
                max_length=16,
                verbose_name="Тип хвостовика",
            ),
        ),
    ]
