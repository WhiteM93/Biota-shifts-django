# Generated manually
# Ранее сидил контракт ГОЗ-2026-25; данные больше не распространяются через git.

from django.db import migrations


def seed_forward(apps, schema_editor):
    # no-op: контракт не сидим в репозитории
    pass


def seed_backward(apps, schema_editor):
    WorkContract = apps.get_model("shifts", "WorkContract")
    WorkContract.objects.filter(name="ГОЗ-2026-25").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0170_alter_workcontractposition_stage"),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
