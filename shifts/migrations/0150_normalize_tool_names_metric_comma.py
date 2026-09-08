# Fix tool names that still contain metric commas (M2,5 → M2.5)

import re

from django.db import migrations


_NAME_METRIC_COMMA = re.compile(r"(M)(\d+),(\d+)", re.IGNORECASE)


def _normalize_name(name: str) -> str:
    text = (name or "").replace("М", "M").replace("м", "M")
    return _NAME_METRIC_COMMA.sub(r"\1\2.\3", text)


def forwards(apps, schema_editor):
    ToolItem = apps.get_model("shifts", "ToolItem")
    for tool in ToolItem.objects.exclude(name="").iterator():
        fixed = _normalize_name(tool.name or "")[:200]
        if fixed != (tool.name or ""):
            tool.name = fixed
            tool.save(update_fields=["name"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0149_normalize_cutting_size_label_comma"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
