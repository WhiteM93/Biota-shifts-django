"""Полки в адресе сверху вниз (01 = верх); пересчёт авто-адресов."""

from django.db import migrations


def _pad2(n: int) -> str:
    return f"{max(0, int(n)):02d}"


def _normalize(addr: str) -> str:
    return (addr or "").strip().upper().replace(" ", "")


def _move_tools(ToolItem, old_addr: str, new_addr: str) -> None:
    old_n = _normalize(old_addr)
    new_n = _normalize(new_addr)
    if not old_n or not new_n or old_n == new_n:
        return
    ToolItem.objects.filter(is_deleted=False, warehouse_address__iexact=old_n).update(
        warehouse_address=new_n
    )


def _move_wh_addr(WarehouseAddress, old_addr: str, new_addr: str) -> None:
    old_n = _normalize(old_addr)
    new_n = _normalize(new_addr)
    if not old_n or not new_n or old_n == new_n:
        return
    row = WarehouseAddress.objects.filter(address__iexact=old_n).first()
    if row is None:
        return
    if WarehouseAddress.objects.filter(address__iexact=new_n).exclude(pk=row.pk).exists():
        # целевой уже есть — переносим подпись, если пусто
        target = WarehouseAddress.objects.filter(address__iexact=new_n).first()
        if target and not (target.label or "").strip() and (row.label or "").strip():
            target.label = row.label
            target.save(update_fields=["label", "updated_at"])
        row.delete()
        return
    row.address = new_n
    row.save(update_fields=["address", "updated_at"])


def forwards(apps, schema_editor):
    VisualCabinet = apps.get_model("shifts", "VisualCabinet")
    VisualContainer = apps.get_model("shifts", "VisualContainer")
    ToolItem = apps.get_model("shifts", "ToolItem")
    WarehouseAddress = apps.get_model("shifts", "WarehouseAddress")

    # Двухфазно: иначе A-01 ↔ A-03 пересекаются.
    phase1 = []  # (cont_id, old, tmp, new)
    for cab in VisualCabinet.objects.all().prefetch_related(
        "containers", "sections", "sections__levels", "containers__level", "containers__level__section"
    ):
        sec_count = cab.sections.count()
        for cont in cab.containers.filter(parent__isnull=True):
            old = _normalize(cont.address or "")
            if not old:
                continue
            code = (cab.code or "").strip().upper()
            if code and not old.startswith(f"{code}-"):
                continue  # кастомный адрес не трогаем
            level = getattr(cont, "level", None)
            shelf_top1 = int(cont.shelf or 1)
            section_index = None
            levels_total = max(1, int(cab.shelves or 1))
            if level is not None:
                shelf_top1 = int(level.index or shelf_top1)
                section = getattr(level, "section", None)
                if section is not None:
                    section_index = int(section.index or 1)
                    levels_total = max(1, section.levels.count())
            level_lab = _pad2(shelf_top1)
            # место пересчитаем по column (как simplified); place_index сложнее в historical
            place_lab = _pad2(int(cont.column or 1))
            if sec_count > 1 and section_index is not None:
                new = f"{(code or '?')}-{section_index}-{level_lab}-{place_lab}"
            else:
                new = f"{(code or '?')}-{level_lab}-{place_lab}"
            new = _normalize(new)
            if not new or new == old:
                continue
            tmp = f"__MIG{cont.pk}__"
            phase1.append((cont.pk, old, tmp, new))

    for cont_id, old, tmp, _new in phase1:
        VisualContainer.objects.filter(pk=cont_id).update(address=tmp)
        _move_tools(ToolItem, old, tmp)
        _move_wh_addr(WarehouseAddress, old, tmp)

    for cont_id, _old, tmp, new in phase1:
        VisualContainer.objects.filter(pk=cont_id).update(address=new)
        _move_tools(ToolItem, tmp, new)
        _move_wh_addr(WarehouseAddress, tmp, new)


def backwards(apps, schema_editor):
    # Обратный пересчёт: display = total - index + 1
    VisualCabinet = apps.get_model("shifts", "VisualCabinet")
    VisualContainer = apps.get_model("shifts", "VisualContainer")
    ToolItem = apps.get_model("shifts", "ToolItem")
    WarehouseAddress = apps.get_model("shifts", "WarehouseAddress")

    phase1 = []
    for cab in VisualCabinet.objects.all().prefetch_related(
        "containers", "sections", "sections__levels", "containers__level", "containers__level__section"
    ):
        sec_count = cab.sections.count()
        for cont in cab.containers.filter(parent__isnull=True):
            old = _normalize(cont.address or "")
            if not old:
                continue
            code = (cab.code or "").strip().upper()
            if code and not old.startswith(f"{code}-"):
                continue
            level = getattr(cont, "level", None)
            shelf_top1 = int(cont.shelf or 1)
            section_index = None
            levels_total = max(1, int(cab.shelves or 1))
            if level is not None:
                shelf_top1 = int(level.index or shelf_top1)
                section = getattr(level, "section", None)
                if section is not None:
                    section_index = int(section.index or 1)
                    levels_total = max(1, section.levels.count())
            level_lab = _pad2(levels_total - shelf_top1 + 1)
            place_lab = _pad2(int(cont.column or 1))
            if sec_count > 1 and section_index is not None:
                new = f"{(code or '?')}-{section_index}-{level_lab}-{place_lab}"
            else:
                new = f"{(code or '?')}-{level_lab}-{place_lab}"
            new = _normalize(new)
            if not new or new == old:
                continue
            tmp = f"__MIG{cont.pk}__"
            phase1.append((cont.pk, old, tmp, new))

    for cont_id, old, tmp, _new in phase1:
        VisualContainer.objects.filter(pk=cont_id).update(address=tmp)
        _move_tools(ToolItem, old, tmp)
        _move_wh_addr(WarehouseAddress, old, tmp)

    for cont_id, _old, tmp, new in phase1:
        VisualContainer.objects.filter(pk=cont_id).update(address=new)
        _move_tools(ToolItem, tmp, new)
        _move_wh_addr(WarehouseAddress, tmp, new)


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0189_site_notebook_reject"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
