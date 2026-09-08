# Normalize Cyrillic М → Latin M in tap/countersink size_label

from django.db import migrations


def _normalize_label(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    return text.replace("М", "M").replace("м", "M")


def forwards(apps, schema_editor):
    TapSpec = apps.get_model("shifts", "TapSpec")
    CountersinkSpec = apps.get_model("shifts", "CountersinkSpec")
    for model in (TapSpec, CountersinkSpec):
        for row in model.objects.all().iterator():
            old = row.size_label or ""
            new = _normalize_label(old)[:32]
            if new != old:
                row.size_label = new
                row.save(update_fields=["size_label"])


def backwards(apps, schema_editor):
    # Необратимо: исходную кириллицу восстановить нельзя
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0147_remove_toolitem_work_material"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
