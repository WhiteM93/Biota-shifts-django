# Generated manually for InsertSpec other/custom type fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0155_insertspec_threading_fields"),
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
                    ("other", "Другое"),
                ],
                default="",
                max_length=12,
                verbose_name="Тип пластины",
            ),
        ),
        migrations.AddField(
            model_name="insertspec",
            name="custom_type",
            field=models.CharField(
                blank=True,
                default="",
                max_length=80,
                verbose_name="Свой тип / категория",
            ),
        ),
        migrations.AddField(
            model_name="insertspec",
            name="item_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=120,
                verbose_name="Наименование",
            ),
        ),
    ]
