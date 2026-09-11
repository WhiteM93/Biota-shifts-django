# Generated manually for InsertSpec.insert_kind

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0153_insertspec_brand"),
    ]

    operations = [
        migrations.AddField(
            model_name="insertspec",
            name="insert_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("milling", "Фрезерная"),
                    ("turning", "Токарная"),
                    ("unique", "Уникальная"),
                ],
                default="",
                max_length=12,
                verbose_name="Тип пластины",
            ),
        ),
    ]
