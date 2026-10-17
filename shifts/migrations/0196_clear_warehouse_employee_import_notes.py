from django.db import migrations


def forwards(apps, schema_editor):
    WarehouseEmployee = apps.get_model("shifts", "WarehouseEmployee")
    WarehouseEmployee.objects.filter(note="из истории выдач").update(note="")


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0195_seed_warehouse_employees_from_movements"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
