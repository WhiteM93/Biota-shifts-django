# Normalize size_label commas/M and fix tool names that still contain M2,5 etc.

import re

from django.db import migrations


def _normalize_label(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    return text.replace("М", "M").replace("м", "M").replace(",", ".")


_NAME_METRIC_COMMA = re.compile(r"(M)(\d+),(\d+)", re.IGNORECASE)


def _normalize_name(name: str) -> str:
    text = (name or "").replace("М", "M").replace("м", "M")
    return _NAME_METRIC_COMMA.sub(r"\1\2.\3", text)


def forwards(apps, schema_editor):
    TapSpec = apps.get_model("shifts", "TapSpec")
    CountersinkSpec = apps.get_model("shifts", "CountersinkSpec")
    ToolItem = apps.get_model("shifts", "ToolItem")

    for model in (TapSpec, CountersinkSpec):
        for row in model.objects.select_related("tool").iterator():
            old = row.size_label or ""
            new = _normalize_label(old)[:32]
            if new != old:
                row.size_label = new
                row.save(update_fields=["size_label"])
            tool = getattr(row, "tool", None)
            if tool and tool.name:
                fixed = _normalize_name(tool.name)[:200]
                if fixed != tool.name:
                    tool.name = fixed
                    tool.save(update_fields=["name"])

    # Any leftover tool names with metric commas
    for tool in ToolItem.objects.exclude(name="").iterator():
        fixed = _normalize_name(tool.name or "")[:200]
        if fixed != (tool.name or ""):
            tool.name = fixed
            tool.save(update_fields=["name"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0148_normalize_cutting_size_label_cyrillic_m"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
