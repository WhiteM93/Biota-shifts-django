from django.db import migrations


def forwards(apps, schema_editor):
    RegulationPlan = apps.get_model("regulations", "RegulationPlan")
    for o in list(RegulationPlan.objects.all()):
        first = o.plan_date.replace(day=1)
        if o.plan_date == first:
            continue
        twin = (
            RegulationPlan.objects.filter(
                plan_date=first,
                employee_code=o.employee_code,
                shift=o.shift,
            )
            .exclude(pk=o.pk)
            .first()
        )
        if twin:
            o.delete()
        else:
            o.plan_date = first
            o.save(update_fields=["plan_date"])


class Migration(migrations.Migration):
    dependencies = [
        ("regulations", "0003_regulationplan_flags"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
