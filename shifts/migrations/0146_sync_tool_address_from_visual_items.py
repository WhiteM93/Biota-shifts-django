# Перенос привязки «позиция → место» с VisualContainerItem на ToolItem.warehouse_address.

from django.db import migrations


def sync_addresses(apps, schema_editor):
    VisualContainerItem = apps.get_model("shifts", "VisualContainerItem")
    VisualContainer = apps.get_model("shifts", "VisualContainer")
    VisualCabinet = apps.get_model("shifts", "VisualCabinet")
    ToolItem = apps.get_model("shifts", "ToolItem")

    def pad2(n: int) -> str:
        return f"{max(0, int(n)):02d}"

    def shelf_display(shelves: int, shelf_top1: int) -> str:
        total = max(1, int(shelves or 1))
        top = max(1, min(int(shelf_top1 or 1), total))
        return pad2(total - top + 1)

    def suggested(cab, shelf: int, column: int) -> str:
        code = (getattr(cab, "code", None) or "").strip().upper() or "?"
        return f"{code}-{shelf_display(cab.shelves, shelf)}-{pad2(column)}"

    cab_cache = {c.pk: c for c in VisualCabinet.objects.all()}
    cont_cache = {
        c.pk: c
        for c in VisualContainer.objects.all().only("id", "cabinet_id", "parent_id", "shelf", "column", "address")
    }

    for item in VisualContainerItem.objects.exclude(tool_item_id=None).iterator():
        cont = cont_cache.get(item.container_id)
        if cont is None:
            continue
        # Для ячеек органайзера берём адрес родителя (трёхчастный A-01-02).
        target = cont
        if getattr(cont, "parent_id", None):
            parent = cont_cache.get(cont.parent_id)
            if parent is not None:
                target = parent
        cab = cab_cache.get(target.cabinet_id)
        if cab is None:
            continue
        addr = (target.address or "").strip().upper().replace(" ", "")
        if not addr:
            addr = suggested(cab, target.shelf, target.column)
        if not addr:
            continue
        tool = ToolItem.objects.filter(pk=item.tool_item_id, is_deleted=False).first()
        if tool is None:
            continue
        if (tool.warehouse_address or "").strip():
            continue
        tool.warehouse_address = addr[:32]
        tool.save(update_fields=["warehouse_address"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0145_reamerspec_and_category"),
    ]

    operations = [
        migrations.RunPython(sync_addresses, noop_reverse),
    ]
