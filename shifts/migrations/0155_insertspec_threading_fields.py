# Generated manually for InsertSpec threading fields + kind choice

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0154_insertspec_insert_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="insertspec",
            name="insert_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("milling", "Фрезерная"),
                    ("turning", "Токарная"),
                    ("threading", "Резьбовая"),
                    ("unique", "Уникальная"),
                ],
                default="",
                max_length=12,
                verbose_name="Тип пластины",
            ),
        ),
        migrations.AddField(
            model_name="insertspec",
            name="thread_side",
            field=models.CharField(
                blank=True,
                choices=[("internal", "Внутренняя"), ("external", "Наружная")],
                default="",
                max_length=12,
                verbose_name="Резьба: внутр./наруж.",
            ),
        ),
        migrations.AddField(
            model_name="insertspec",
            name="thread_hand",
            field=models.CharField(
                blank=True,
                choices=[("right", "Правая"), ("left", "Левая")],
                default="",
                max_length=8,
                verbose_name="Резьба: лев./прав.",
            ),
        ),
        migrations.AddField(
            model_name="insertspec",
            name="thread_size",
            field=models.CharField(
                blank=True,
                default="",
                max_length=8,
                verbose_name="Размер резьбовой пластины",
            ),
        ),
        migrations.AddField(
            model_name="insertspec",
            name="thread_pitch_mm",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=6,
                null=True,
                verbose_name="Шаг резьбы, мм",
            ),
        ),
    ]
