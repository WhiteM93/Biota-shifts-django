import os

from django.core.files import File
from django.db import migrations, models
import django.db.models.deletion


def forwards_copy_program_files(apps, schema_editor):
    ProductSetup = apps.get_model("shifts", "ProductSetup")
    ProductSetupProgramFile = apps.get_model("shifts", "ProductSetupProgramFile")
    for setup in ProductSetup.objects.all():
        old = setup.program_file
        if not old or not getattr(old, "name", None):
            continue
        base = os.path.basename(old.name)
        try:
            with old.open("rb") as src:
                row = ProductSetupProgramFile(setup_id=setup.pk, sort_order=0)
                row.save()
                row.file.save(base, File(src), save=True)
        except Exception:
            continue
        try:
            old.delete(save=False)
        except Exception:
            pass
        ProductSetup.objects.filter(pk=setup.pk).update(program_file="")


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0052_employeedefectpayrolladjustment"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductSetupProgramFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "file",
                    models.FileField(upload_to="products/setup_programs/", verbose_name="Файл программы"),
                ),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                (
                    "setup",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="program_files",
                        to="shifts.productsetup",
                        verbose_name="Установка",
                    ),
                ),
            ],
            options={
                "verbose_name": "Файл программы установки",
                "verbose_name_plural": "Файлы программ установки",
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.RunPython(forwards_copy_program_files, backwards_noop),
    ]
