import re

from django.db import migrations

_SUPPLIER_NAMES = (
    "ООО МВ",
    "ИП Иванов",
    "ИП Игнатьев",
    "ИП Ясинов",
)
_PAREN_RE = re.compile(r"\s*\([^)]*(?:ООО|ИП)[^)]*\)")


def _scrub(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw
    out = raw
    for name in _SUPPLIER_NAMES:
        out = out.replace(f" ({name})", "")
        out = out.replace(f"({name})", "")
        out = out.replace(name, "")
    out = _PAREN_RE.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,;—-")
    return out


def forwards(apps, schema_editor):
    StockMovement = apps.get_model("shifts", "StockMovement")
    InventoryStockEvent = apps.get_model("shifts", "InventoryStockEvent")
    for model, field in ((StockMovement, "comment"), (InventoryStockEvent, "summary")):
        for obj in model.objects.exclude(**{field: ""}).iterator():
            current = getattr(obj, field) or ""
            cleaned = _scrub(current)
            if cleaned != current:
                setattr(obj, field, cleaned)
                obj.save(update_fields=[field])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0126_body_tool_face_mill_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
