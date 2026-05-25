from django.db import migrations, models

import shifts.models


def backfill_original_filename(apps, schema_editor):
    ProductDrawingFile = apps.get_model("shifts", "ProductDrawingFile")
    for row in ProductDrawingFile.objects.all().iterator():
        if (row.original_filename or "").strip():
            continue
        name = shifts.models.drawing_file_display_name(row.file.name, "")
        if name:
            row.original_filename = name[:255]
            row.save(update_fields=["original_filename"])


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0081_productdrawingfile"),
    ]

    operations = [
        migrations.AddField(
            model_name="productdrawingfile",
            name="original_filename",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Имя при загрузке"),
        ),
        migrations.RunPython(backfill_original_filename, migrations.RunPython.noop),
    ]
