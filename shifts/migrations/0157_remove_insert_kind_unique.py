# Remove insert_kind "unique" (Уникальная)

from django.db import migrations, models


def remap_unique_to_milling(apps, schema_editor):
    InsertSpec = apps.get_model("shifts", "InsertSpec")
    InsertSpec.objects.filter(insert_kind="unique").update(insert_kind="milling")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0156_insertspec_other_custom_type"),
    ]

    operations = [
        migrations.RunPython(remap_unique_to_milling, noop_reverse),
        migrations.AlterField(
            model_name="insertspec",
            name="insert_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("milling", "Фрезерная"),
                    ("turning", "Токарная"),
                    ("threading", "Резьбовая"),
                    ("other", "Другое"),
                ],
                default="",
                max_length=12,
                verbose_name="Тип пластины",
            ),
        ),
    ]
