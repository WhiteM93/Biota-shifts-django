# Normalize bare metric sizes: 8 / М8 → M8

from django.db import migrations
import re

_BARE = re.compile(r"^\d+(?:\.\d+)?$")
_M_NUM = re.compile(r"^M(\d+)(?:\.(\d+))?$", re.IGNORECASE)


def _normalize_label(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = text.replace("М", "M").replace("м", "M").replace(",", ".")
    if len(text) >= 2 and text[0] in "mM" and text[1].isdigit():
        text = "M" + text[1:]
    if _BARE.fullmatch(text):
        text = "M" + text
    m = _M_NUM.fullmatch(text)
    if m:
        int_part = str(int(m.group(1)))
        frac = m.group(2)
        text = "M" + int_part + (("." + frac) if frac is not None else "")
    return text


def forwards(apps, schema_editor):
    TapSpec = apps.get_model("shifts", "TapSpec")
    CountersinkSpec = apps.get_model("shifts", "CountersinkSpec")
    VisualContainerItem = apps.get_model("shifts", "VisualContainerItem")

    for model in (TapSpec, CountersinkSpec):
        for row in model.objects.select_related("tool").iterator():
            old = row.size_label or ""
            new = _normalize_label(old)[:32]
            if new == old:
                continue
            row.size_label = new
            row.save(update_fields=["size_label"])
            tool = getattr(row, "tool", None)
            if tool and tool.name:
                # «8 / …» → «M8 / …»
                prefix = f"{old} /"
                if tool.name.startswith(prefix):
                    tool.name = (new + tool.name[len(old) :])[:200]
                    tool.save(update_fields=["name"])
                elif old and old in tool.name:
                    tool.name = tool.name.replace(old, new, 1)[:200]
                    tool.save(update_fields=["name"])

    for row in VisualContainerItem.objects.iterator():
        old = row.size_label or ""
        new = _normalize_label(old)[:32]
        if new != old:
            row.size_label = new
            row.save(update_fields=["size_label"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0160_body_tool_thread_cutter"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
