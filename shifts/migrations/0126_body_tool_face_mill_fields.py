from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0125_body_tool_insert_family"),
    ]

    operations = [
        migrations.AddField(
            model_name="bodytoolspec",
            name="insert_size",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Размер / код пластины (1604, 12…)",
                max_length=24,
                verbose_name="Размер пластины",
            ),
        ),
        migrations.AddField(
            model_name="bodytoolspec",
            name="mount_diameter_mm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=7,
                null=True,
                verbose_name="d хвостовика / посадки, мм",
            ),
        ),
        migrations.AddField(
            model_name="bodytoolspec",
            name="coolant_through",
            field=models.BooleanField(default=False, verbose_name="Каналы для СОЖ"),
        ),
        migrations.AddField(
            model_name="bodytoolspec",
            name="ap_max_mm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=7,
                null=True,
                verbose_name="Максимальная глубина резания ap, мм",
            ),
        ),
        migrations.AddField(
            model_name="bodytoolspec",
            name="brand",
            field=models.CharField(blank=True, default="", max_length=80, verbose_name="Бренд"),
        ),
        migrations.AlterField(
            model_name="bodytoolspec",
            name="insert_family",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Семейство СМП под корпус (APKT, SEKT…)",
                max_length=24,
                verbose_name="Формфактор пластины",
            ),
        ),
    ]
