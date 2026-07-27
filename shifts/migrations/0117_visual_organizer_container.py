from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0116_visual_drawer_chest_kinds"),
    ]

    operations = [
        migrations.AlterField(
            model_name="visualcontainer",
            name="kind",
            field=models.CharField(
                choices=[
                    ("bin", "Контейнер"),
                    ("shelf_slot", "На полке"),
                    ("drawer_cell", "Ячейка ящика"),
                    ("organizer", "Органайзер (ярусы)"),
                ],
                default="bin",
                max_length=16,
                verbose_name="Тип",
            ),
        ),
        migrations.AddField(
            model_name="visualcontainer",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="children",
                to="shifts.visualcontainer",
                verbose_name="Родительский органайзер",
            ),
        ),
        migrations.AddField(
            model_name="visualcontainer",
            name="inner_tiers",
            field=models.PositiveSmallIntegerField(
                default=1,
                verbose_name="Ярусов внутри (органайзер)",
            ),
        ),
        migrations.AddField(
            model_name="visualcontainer",
            name="inner_columns",
            field=models.PositiveSmallIntegerField(
                default=1,
                verbose_name="Ячеек в ярусе (разделители)",
            ),
        ),
    ]
