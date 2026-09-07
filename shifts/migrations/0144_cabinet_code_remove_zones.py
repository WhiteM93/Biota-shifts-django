# -*- coding: utf-8 -*-
import django.db.models.deletion
from django.db import migrations, models


LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CYR = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ"


def _next_code(used: set[str]) -> str:
    for ch in LATIN + CYR:
        if ch not in used:
            return ch
    for a in LATIN:
        for b in LATIN:
            cand = f"{a}{b}"
            if cand not in used:
                return cand
    return "X"


def assign_cabinet_codes(apps, schema_editor):
    VisualCabinet = apps.get_model("shifts", "VisualCabinet")
    VisualZone = apps.get_model("shifts", "VisualZone")
    VisualContainer = apps.get_model("shifts", "VisualContainer")

    zones = {z.id: (z.code or "").strip().upper() for z in VisualZone.objects.all()}
    used: set[str] = set()
    cabinets = list(VisualCabinet.objects.order_by("sort_order", "id"))

    for cab in cabinets:
        code = ""
        zid = getattr(cab, "zone_id", None)
        if zid and zones.get(zid):
            cand = zones[zid]
            if cand and cand not in used:
                code = cand
        if not code:
            code = _next_code(used)
        cab.code = code
        cab.save(update_fields=["code"])
        used.add(code)

        # refresh container addresses that used old zone prefix
        for cont in VisualContainer.objects.filter(cabinet_id=cab.id, parent__isnull=True):
            shelves = max(1, int(cab.shelves or 1))
            top = max(1, min(int(cont.shelf or 1), shelves))
            shelf_disp = f"{shelves - top + 1:02d}"
            place_disp = f"{max(1, int(cont.column or 1)):02d}"
            new_addr = f"{code}-{shelf_disp}-{place_disp}"
            old = (cont.address or "").strip().upper()
            # update empty or auto-looking zone-based addresses
            if not old or old.endswith(f"-{shelf_disp}-{place_disp}"):
                cont.address = new_addr
                cont.save(update_fields=["address"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0143_visual_zones_and_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="visualcabinet",
            name="code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Буква мебели для адреса: A, B, А, Б…",
                max_length=8,
                verbose_name="Буква / код",
            ),
        ),
        migrations.RunPython(assign_cabinet_codes, noop_reverse),
        migrations.RemoveField(
            model_name="visualcabinet",
            name="zone",
        ),
        migrations.DeleteModel(
            name="VisualZone",
        ),
        migrations.AlterModelOptions(
            name="visualcabinet",
            options={
                "ordering": ("sort_order", "code", "name", "id"),
                "verbose_name": "Визуальный шкаф",
                "verbose_name_plural": "Визуальные шкафы",
            },
        ),
    ]
