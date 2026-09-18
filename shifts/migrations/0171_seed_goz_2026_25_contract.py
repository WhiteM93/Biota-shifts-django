# Generated manually

from django.db import migrations


def seed_forward(apps, schema_editor):
    from shifts.contract_seed import ensure_goz_2026_25_contract

    WorkContract = apps.get_model("shifts", "WorkContract")
    WorkContractPosition = apps.get_model("shifts", "WorkContractPosition")
    WorkPositionOperation = apps.get_model("shifts", "WorkPositionOperation")
    ensure_goz_2026_25_contract(
        WorkContract=WorkContract,
        WorkContractPosition=WorkContractPosition,
        WorkPositionOperation=WorkPositionOperation,
    )


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
