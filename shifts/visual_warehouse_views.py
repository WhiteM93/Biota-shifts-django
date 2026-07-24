"""Визуальный склад: шкафы → ячейки → контейнеры → содержимое."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import (
    COATING_TYPE_TOOLTIPS,
    InventoryStockEvent,
    StockMovement,
    ToolItem,
    VisualCabinet,
    VisualContainer,
    VisualContainerAudit,
    VisualContainerAuditLine,
    VisualContainerItem,
)

MAX_CABINETS = 40
MAX_SHELVES = 20
MAX_COLUMNS = 12
MAX_ITEMS_PER_CONTAINER = 80
MAX_AUDIT_LINES = 120
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_VALID_CATEGORIES = {c for c, _ in VisualContainerItem.TOOL_CATEGORY_CHOICES if c}


def _fmt_dt(dt) -> str:
    if not dt:
        return ""
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    return local.strftime("%d.%m.%Y %H:%M")


def _json_body(request):
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        data = json.loads(raw or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _err(message: str, status: int = 400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _clamp_int(val, default: int, lo: int, hi: int) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _dec(val):
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _username(request) -> str:
    return (biota_user(request) or "").strip()


def _serialize_item(item: VisualContainerItem, stock_qty: int | None = None) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "tool_category": item.tool_category or "",
        "diameter_from_mm": float(item.diameter_from_mm) if item.diameter_from_mm is not None else None,
        "diameter_to_mm": float(item.diameter_to_mm) if item.diameter_to_mm is not None else None,
        "tool_item_id": item.tool_item_id,
        "quantity_note": item.quantity_note or "",
        "notes": item.notes or "",
        "sort_order": item.sort_order,
        "stock_qty": stock_qty,
    }


def _stock_qty_for_item(item: VisualContainerItem) -> int | None:
    if item.tool_item_id and item.tool_item and not item.tool_item.is_deleted:
        return int(item.tool_item.quantity or 0)
    if not item.tool_category:
        return None
    qs = ToolItem.objects.filter(is_deleted=False, category=item.tool_category)
    if item.diameter_from_mm is not None:
        qs = qs.filter(main_diameter_mm__gte=item.diameter_from_mm)
    if item.diameter_to_mm is not None:
        qs = qs.filter(main_diameter_mm__lte=item.diameter_to_mm)
    total = qs.aggregate(s=Sum("quantity"))["s"]
    return int(total or 0)


def _infer_filter_from_label(label: str) -> dict | None:
    """Грубая подсказка фильтра по подписи ящика: «Фрезы концевые 0-1»."""
    text = (label or "").strip().lower().replace("–", "-").replace("—", "-")
    if not text:
        return None
    category = ""
    if "фрез" in text:
        category = "end_mill"
    elif "сверл" in text:
        category = "drill"
    elif "центров" in text:
        category = "center_drill"
    elif "зенкер" in text:
        category = "countersink"
    elif "резьб" in text or "метчик" in text or " плаш" in text:
        category = "tap"
    elif "пластин" in text:
        category = "insert"
    elif "цанг" in text:
        category = "collet"
    if not category:
        return None
    d_from = d_to = None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[-/]\s*(\d+(?:[.,]\d+)?)", text)
    if m:
        try:
            d_from = Decimal(m.group(1).replace(",", "."))
            d_to = Decimal(m.group(2).replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            d_from = d_to = None
    else:
        m1 = re.search(r"[øØ⌀]\s*(\d+(?:[.,]\d+)?)", text)
        if m1:
            try:
                d_from = d_to = Decimal(m1.group(1).replace(",", "."))
            except (InvalidOperation, TypeError, ValueError):
                d_from = d_to = None
    return {
        "tool_category": category,
        "diameter_from_mm": d_from,
        "diameter_to_mm": d_to,
    }


def _serialize_tool(tool: ToolItem) -> dict:
    diam = float(tool.main_diameter_mm) if tool.main_diameter_mm is not None else None
    coating = (tool.coating_type or "none").strip() or "none"
    coating_label = "без покрытия" if coating == "none" else str(tool.get_coating_type_display())
    wm_codes = tool.work_material_codes_list()
    return {
        "id": tool.id,
        "name": tool.name,
        "category": tool.category or "",
        "category_label": tool.get_category_display() if tool.category else "",
        "diameter_mm": diam,
        "quantity": int(tool.quantity or 0),
        "notes": tool.notes or "",
        "tool_material": (tool.tool_material or "").strip(),
        "tool_material_label": tool.get_tool_material_display() or "",
        "coating_type": coating,
        "coating_label": coating_label,
        "coating_title": COATING_TYPE_TOOLTIPS.get(coating, coating_label),
        "work_material_codes": wm_codes,
        "work_material_label": tool.get_work_materials_display() or "",
    }


def _tool_qs_for_filter(
    *,
    tool_item_id: int | None = None,
    category: str = "",
    d_from=None,
    d_to=None,
):
    if tool_item_id:
        return ToolItem.objects.filter(pk=tool_item_id, is_deleted=False)
    if not category:
        return ToolItem.objects.none()
    qs = ToolItem.objects.filter(is_deleted=False, category=category)
    if d_from is not None:
        qs = qs.filter(main_diameter_mm__gte=d_from)
    if d_to is not None:
        qs = qs.filter(main_diameter_mm__lte=d_to)
    return qs


def _matching_tools_for_container(c: VisualContainer, items: list[VisualContainerItem] | None = None) -> list[dict]:
    """Список реальных позиций склада, попадающих под содержимое ящика."""
    seen: set[int] = set()
    out: list[dict] = []
    rows = items if items is not None else list(c.items.select_related("tool_item").all())

    def _add_from_qs(qs):
        for tool in qs.order_by("category", "main_diameter_mm", "name")[:120]:
            if tool.pk in seen:
                continue
            seen.add(tool.pk)
            out.append(_serialize_tool(tool))

    has_rule = False
    for item in rows:
        if item.tool_item_id:
            has_rule = True
            _add_from_qs(_tool_qs_for_filter(tool_item_id=item.tool_item_id))
        elif item.tool_category:
            has_rule = True
            _add_from_qs(
                _tool_qs_for_filter(
                    category=item.tool_category,
                    d_from=item.diameter_from_mm,
                    d_to=item.diameter_to_mm,
                )
            )

    if not has_rule:
        inferred = _infer_filter_from_label(c.label or "")
        if inferred:
            _add_from_qs(
                _tool_qs_for_filter(
                    category=inferred["tool_category"],
                    d_from=inferred["diameter_from_mm"],
                    d_to=inferred["diameter_to_mm"],
                )
            )
    return out


def _normalize_cabinet_kind(raw) -> str:
    kind = str(raw or "").strip().lower()
    if kind == VisualCabinet.KIND_RACK:
        return VisualCabinet.KIND_RACK
    return VisualCabinet.KIND_CABINET


def _normalize_container_kind(raw) -> str:
    kind = str(raw or "").strip().lower()
    if kind == VisualContainer.KIND_SHELF_SLOT:
        return VisualContainer.KIND_SHELF_SLOT
    return VisualContainer.KIND_BIN


def _serialize_container(c: VisualContainer, *, with_items: bool = False) -> dict:
    color = (c.color or "").strip()
    if not _HEX_RE.match(color):
        color = "#e74c3c"
    data = {
        "id": c.id,
        "cabinet_id": c.cabinet_id,
        "kind": _normalize_container_kind(getattr(c, "kind", None)),
        "shelf": c.shelf,
        "stack": max(1, int(c.stack or 1)),
        "column": c.column,
        "col_span": max(1, int(c.col_span or 1)),
        "row_span": max(1, int(c.row_span or 1)),
        "label": c.label,
        "color": color,
        "notes": c.notes or "",
        "items_count": getattr(c, "items_count", None),
        "last_audited_at": _fmt_dt(getattr(c, "last_audited_at", None)),
        "last_audited_by": (getattr(c, "last_audited_by", None) or ""),
        "last_audited_at_iso": (
            timezone.localtime(c.last_audited_at).isoformat()
            if getattr(c, "last_audited_at", None)
            else ""
        ),
    }
    if data["items_count"] is None:
        data["items_count"] = c.items.count()
    if with_items:
        items = list(c.items.select_related("tool_item").all())
        data["items"] = [_serialize_item(it, _stock_qty_for_item(it)) for it in items]
        data["stock_tools"] = _matching_tools_for_container(c, items)
    return data


def _serialize_audit_line(line: VisualContainerAuditLine) -> dict:
    tool = line.tool
    return {
        "id": line.id,
        "tool_id": line.tool_id,
        "tool_name": tool.name if tool else "",
        "expected_qty": line.expected_qty,
        "counted_qty": line.counted_qty,
        "delta": line.delta,
        "note": line.note or "",
        "status": line.status,
        "stock_movement_id": line.stock_movement_id,
    }


def _serialize_audit(audit: VisualContainerAudit, *, with_lines: bool = True) -> dict:
    data = {
        "id": audit.id,
        "container_id": audit.container_id,
        "audited_by": audit.audited_by or "",
        "audited_at": _fmt_dt(audit.audited_at),
        "notes": audit.notes or "",
        "changes_count": int(audit.changes_count or 0),
    }
    if with_lines:
        lines = list(audit.lines.select_related("tool").all())
        data["lines"] = [_serialize_audit_line(ln) for ln in lines]
    return data


def _cells_of(shelf: int, stack: int, column: int, col_span: int):
    for c in range(column, column + col_span):
        yield (shelf, stack, c)


def _container_overlap_error(
    cab: VisualCabinet,
    *,
    shelf: int,
    stack: int,
    column: int,
    col_span: int,
    exclude_id: int | None = None,
) -> str | None:
    if shelf < 1 or shelf > cab.shelves:
        return "Некорректный номер полки"
    if column < 1 or col_span < 1:
        return "Некорректное место на полке"
    occupied: set[tuple[int, int, int]] = set()
    qs = VisualContainer.objects.filter(cabinet=cab)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    for other in qs:
        cs = max(1, int(other.col_span or 1))
        st = max(1, int(other.stack or 1))
        occupied.update(_cells_of(other.shelf, st, other.column, cs))
    for cell in _cells_of(shelf, stack, column, col_span):
        if cell in occupied:
            return "Это место уже занято другим ящиком. Выберите другое «место слева» или нажмите «+» на полке."
    return None


def _serialize_cabinet(cab: VisualCabinet, *, with_containers: bool = True) -> dict:
    data = {
        "id": cab.id,
        "name": cab.name,
        "kind": _normalize_cabinet_kind(getattr(cab, "kind", None)),
        "shelves": cab.shelves,
        "columns": cab.columns,
        "notes": cab.notes or "",
        "sort_order": cab.sort_order,
    }
    if with_containers:
        containers = list(cab.containers.all())
        data["containers"] = [_serialize_container(c) for c in containers]
    return data


@biota_login_required
@nav_permission_required("visual_warehouse")
def visual_warehouse_view(request):
    return render(
        request,
        "shifts/visual_warehouse.html",
        {
            "tool_categories": [
                {"value": v, "label": lab}
                for v, lab in VisualContainerItem.TOOL_CATEGORY_CHOICES
                if v
            ],
        },
    )


@biota_login_required
@nav_permission_required("visual_warehouse")
@require_http_methods(["GET", "POST"])
def visual_warehouse_api_cabinets(request):
    if request.method == "GET":
        qs = (
            VisualCabinet.objects.annotate(containers_count=Count("containers"))
            .prefetch_related(
                Prefetch(
                    "containers",
                    queryset=VisualContainer.objects.annotate(items_count=Count("items")),
                )
            )
            .all()
        )
        return JsonResponse({"ok": True, "cabinets": [_serialize_cabinet(c) for c in qs]})

    return _cabinets_create(request)


@write_permission_required
def _cabinets_create(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    if VisualCabinet.objects.count() >= MAX_CABINETS:
        return _err(f"Лимит шкафов: {MAX_CABINETS}")

    name = str(body.get("name") or "").strip()[:120]
    if not name:
        return _err("Укажите название шкафа")
    kind = _normalize_cabinet_kind(body.get("kind"))
    shelves = _clamp_int(body.get("shelves"), 4, 1, MAX_SHELVES)
    columns = _clamp_int(body.get("columns"), 3, 1, MAX_COLUMNS)
    notes = str(body.get("notes") or "").strip()[:300]
    cab = VisualCabinet.objects.create(
        name=name,
        kind=kind,
        shelves=shelves,
        columns=columns,
        notes=notes,
        created_by=_username(request),
    )
    return JsonResponse({"ok": True, "cabinet": _serialize_cabinet(cab)}, status=201)


@biota_login_required
@nav_permission_required("visual_warehouse")
@require_http_methods(["GET", "PATCH", "DELETE"])
def visual_warehouse_api_cabinet_detail(request, pk: int):
    cab = get_object_or_404(
        VisualCabinet.objects.prefetch_related(
            Prefetch(
                "containers",
                queryset=VisualContainer.objects.annotate(items_count=Count("items")),
            )
        ),
        pk=pk,
    )
    if request.method == "GET":
        return JsonResponse({"ok": True, "cabinet": _serialize_cabinet(cab)})
    return _cabinet_mutate(request, cab)


@write_permission_required
def _cabinet_mutate(request, cab: VisualCabinet):
    if request.method == "DELETE":
        cab.delete()
        return JsonResponse({"ok": True})

    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    if "name" in body:
        name = str(body.get("name") or "").strip()[:120]
        if not name:
            return _err("Укажите название")
        cab.name = name
    if "kind" in body:
        new_kind = _normalize_cabinet_kind(body.get("kind"))
        if new_kind == VisualCabinet.KIND_CABINET:
            has_slot = cab.containers.filter(kind=VisualContainer.KIND_SHELF_SLOT).exists()
            if has_slot:
                return _err("Нельзя сделать шкаф: на стеллаже есть зоны «на полке». Удалите их или оставьте стеллаж.")
        cab.kind = new_kind
    if "notes" in body:
        cab.notes = str(body.get("notes") or "").strip()[:300]
    if "shelves" in body or "columns" in body:
        shelves = _clamp_int(body.get("shelves", cab.shelves), cab.shelves, 1, MAX_SHELVES)
        columns = _clamp_int(body.get("columns", cab.columns), cab.columns, 1, MAX_COLUMNS)
        for cont in cab.containers.all():
            cs = max(1, int(cont.col_span or 1))
            if cont.shelf > shelves or cont.column + cs - 1 > columns:
                return _err("Уменьшить сетку нельзя: контейнеры не помещаются")
        cab.shelves = shelves
        cab.columns = columns
    if "sort_order" in body:
        cab.sort_order = _clamp_int(body.get("sort_order"), cab.sort_order, 0, 9999)
    cab.save()
    cab = VisualCabinet.objects.prefetch_related(
        Prefetch(
            "containers",
            queryset=VisualContainer.objects.annotate(items_count=Count("items")),
        )
    ).get(pk=cab.pk)
    return JsonResponse({"ok": True, "cabinet": _serialize_cabinet(cab)})


@biota_login_required
@nav_permission_required("visual_warehouse")
@write_permission_required
@require_http_methods(["POST"])
def visual_warehouse_api_container_upsert(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    cab = get_object_or_404(VisualCabinet, pk=body.get("cabinet_id"))
    shelf = _clamp_int(body.get("shelf"), 0, 1, cab.shelves)
    stack = _clamp_int(body.get("stack"), 1, 1, 20)
    # Важно: не ограничивать column текущим cab.columns — иначе «место 2»
    # при columns=1 сжимается в 1 и всегда пересекается с первым ящиком.
    column = _clamp_int(body.get("column"), 0, 1, MAX_COLUMNS)
    col_span = _clamp_int(body.get("col_span"), 1, 1, MAX_COLUMNS)
    # Сохраняем ручные переносы (\n), обрезаем края строк
    label_raw = str(body.get("label") or "")
    label = "\n".join(line.rstrip() for line in label_raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    label = label.strip("\n")[:120]
    if not label.strip():
        return _err("Укажите подпись контейнера")
    color = str(body.get("color") or "#e74c3c").strip()
    if not _HEX_RE.match(color):
        color = "#e74c3c"
    notes = str(body.get("notes") or "").strip()[:300]
    cont_kind = _normalize_container_kind(body.get("kind"))
    cab_kind = _normalize_cabinet_kind(cab.kind)
    if cont_kind == VisualContainer.KIND_SHELF_SLOT and cab_kind != VisualCabinet.KIND_RACK:
        return _err("Зона «на полке» доступна только на стеллаже")
    if cont_kind == VisualContainer.KIND_SHELF_SLOT and stack > 1:
        return _err("Зона «на полке» не ставится в стопку — только ярус 1")
    cid = body.get("id")
    exclude_id = int(cid) if cid else None

    need_cols = column + col_span - 1
    if need_cols > MAX_COLUMNS:
        return _err(f"Максимум мест в ряд: {MAX_COLUMNS}")
    if need_cols > cab.columns:
        cab.columns = need_cols
        cab.save(update_fields=["columns", "updated_at"])

    overlap = _container_overlap_error(
        cab,
        shelf=shelf,
        stack=stack,
        column=column,
        col_span=col_span,
        exclude_id=exclude_id,
    )
    if overlap:
        return _err(overlap)
    if cid:
        cont = get_object_or_404(VisualContainer, pk=cid, cabinet=cab)
        cont.kind = cont_kind
        cont.shelf = shelf
        cont.stack = stack
        cont.column = column
        cont.col_span = col_span
        cont.row_span = 1
        cont.label = label
        cont.color = color
        cont.notes = notes
        cont.save()
    else:
        cont = VisualContainer.objects.create(
            cabinet=cab,
            kind=cont_kind,
            shelf=shelf,
            stack=stack,
            column=column,
            col_span=col_span,
            row_span=1,
            label=label,
            color=color,
            notes=notes,
        )
    cont = (
        VisualContainer.objects.annotate(items_count=Count("items"))
        .prefetch_related(
            Prefetch("items", queryset=VisualContainerItem.objects.select_related("tool_item"))
        )
        .get(pk=cont.pk)
    )
    # Отдаём актуальный шкаф (columns мог вырасти)
    cab.refresh_from_db()
    return JsonResponse({
        "ok": True,
        "container": _serialize_container(cont, with_items=True),
        "cabinet": _serialize_cabinet(cab),
    })


@biota_login_required
@nav_permission_required("visual_warehouse")
@require_http_methods(["GET", "DELETE"])
def visual_warehouse_api_container_detail(request, pk: int):
    cont = get_object_or_404(
        VisualContainer.objects.select_related("cabinet").prefetch_related(
            Prefetch("items", queryset=VisualContainerItem.objects.select_related("tool_item"))
        ),
        pk=pk,
    )
    if request.method == "GET":
        return JsonResponse({"ok": True, "container": _serialize_container(cont, with_items=True)})
    return _container_delete(request, cont)


@write_permission_required
def _container_delete(request, cont: VisualContainer):
    cont.delete()
    return JsonResponse({"ok": True})


@biota_login_required
@nav_permission_required("visual_warehouse")
@write_permission_required
@require_http_methods(["POST"])
def visual_warehouse_api_item_upsert(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    cont = get_object_or_404(VisualContainer, pk=body.get("container_id"))
    title = str(body.get("title") or "").strip()[:200]
    if not title:
        return _err("Укажите название позиции")
    category = str(body.get("tool_category") or "").strip()
    if category and category not in _VALID_CATEGORIES:
        return _err("Некорректная категория")
    d_from = _dec(body.get("diameter_from_mm"))
    d_to = _dec(body.get("diameter_to_mm"))
    quantity_note = str(body.get("quantity_note") or "").strip()[:80]
    notes = str(body.get("notes") or "").strip()[:300]
    tool_item_id = body.get("tool_item_id")
    tool_item = None
    if tool_item_id:
        tool_item = ToolItem.objects.filter(pk=tool_item_id, is_deleted=False).first()
        if not tool_item:
            return _err("Позиция склада не найдена")

    item_id = body.get("id")
    if item_id:
        item = get_object_or_404(VisualContainerItem, pk=item_id, container=cont)
        item.title = title
        item.tool_category = category
        item.diameter_from_mm = d_from
        item.diameter_to_mm = d_to
        item.quantity_note = quantity_note
        item.notes = notes
        item.tool_item = tool_item
        item.save()
    else:
        if cont.items.count() >= MAX_ITEMS_PER_CONTAINER:
            return _err(f"Лимит позиций в контейнере: {MAX_ITEMS_PER_CONTAINER}")
        item = VisualContainerItem.objects.create(
            container=cont,
            title=title,
            tool_category=category,
            diameter_from_mm=d_from,
            diameter_to_mm=d_to,
            quantity_note=quantity_note,
            notes=notes,
            tool_item=tool_item,
            sort_order=cont.items.count(),
        )
    item = VisualContainerItem.objects.select_related("tool_item").get(pk=item.pk)
    return JsonResponse({"ok": True, "item": _serialize_item(item, _stock_qty_for_item(item))})


@biota_login_required
@nav_permission_required("visual_warehouse")
@write_permission_required
@require_http_methods(["POST", "DELETE"])
def visual_warehouse_api_item_delete(request, pk: int):
    item = get_object_or_404(VisualContainerItem, pk=pk)
    item.delete()
    return JsonResponse({"ok": True})


@biota_login_required
@nav_permission_required("visual_warehouse")
@require_http_methods(["GET", "POST"])
def visual_warehouse_api_container_audits(request, pk: int):
    cont = get_object_or_404(
        VisualContainer.objects.select_related("cabinet").prefetch_related(
            Prefetch("items", queryset=VisualContainerItem.objects.select_related("tool_item"))
        ),
        pk=pk,
    )
    if request.method == "GET":
        audits = (
            VisualContainerAudit.objects.filter(container=cont)
            .prefetch_related(Prefetch("lines", queryset=VisualContainerAuditLine.objects.select_related("tool")))
            .order_by("-audited_at", "-id")[:20]
        )
        return JsonResponse({
            "ok": True,
            "container": _serialize_container(cont),
            "audits": [_serialize_audit(a) for a in audits],
        })
    return _container_audit_create(request, cont)


@write_permission_required
def _container_audit_create(request, cont: VisualContainer):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    raw_lines = body.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        return _err("Укажите строки инвентаризации")
    if len(raw_lines) > MAX_AUDIT_LINES:
        return _err(f"Слишком много строк (макс. {MAX_AUDIT_LINES})")

    notes = str(body.get("notes") or "").strip()[:500]
    who = _username(request) or "unknown"
    label = (cont.label or "Ящик").strip()

    parsed: list[tuple[int, int, str]] = []
    seen: set[int] = set()
    for row in raw_lines:
        if not isinstance(row, dict):
            return _err("Некорректная строка инвентаризации")
        try:
            tool_id = int(row.get("tool_id"))
        except (TypeError, ValueError):
            return _err("Некорректный инструмент в строке")
        if tool_id <= 0 or tool_id in seen:
            return _err("Дубликат или пустой инструмент в строках")
        seen.add(tool_id)
        counted = _clamp_int(row.get("counted_qty"), -1, 0, 999999)
        if counted < 0:
            return _err("Укажите фактическое количество")
        note = str(row.get("note") or "").strip()[:300]
        parsed.append((tool_id, counted, note))

    allowed_ids = {t["id"] for t in _matching_tools_for_container(cont)}
    if allowed_ids and not seen.issubset(allowed_ids):
        return _err("В проверке есть инструмент, которого нет в этом ящике")

    today = timezone.localdate()

    try:
        with transaction.atomic():
            tools = {
                t.pk: t
                for t in ToolItem.objects.select_for_update().filter(pk__in=seen, is_deleted=False)
            }
            if len(tools) != len(seen):
                raise ValueError("Один или несколько инструментов не найдены")

            # Предпроверка остатков до записи
            for tool_id, counted, _note in parsed:
                tool = tools[tool_id]
                expected = int(tool.quantity or 0)
                delta = counted - expected
                if delta < 0 and expected < abs(delta):
                    raise ValueError(f"Недостаточно остатков у «{tool.name}»: доступно {expected}")

            audit = VisualContainerAudit.objects.create(
                container=cont,
                audited_by=who[:120],
                notes=notes,
                changes_count=0,
            )
            changes = 0
            line_rows: list[VisualContainerAuditLine] = []
            change_summaries: list[str] = []

            for tool_id, counted, note in parsed:
                tool = tools[tool_id]
                expected = int(tool.quantity or 0)
                delta = counted - expected
                movement = None
                status = VisualContainerAuditLine.STATUS_OK
                if delta != 0:
                    status = VisualContainerAuditLine.STATUS_ADJUSTED
                    changes += 1
                    move_qty = abs(delta)
                    move_type = "restock" if delta > 0 else "writeoff"
                    reason = note or "расхождение"
                    comment = f"Инвентаризация «{label}»: {reason}"[:300]
                    if delta < 0:
                        tool.quantity = expected - move_qty
                    else:
                        tool.quantity = expected + move_qty
                    tool.save(update_fields=["quantity", "updated_at"])
                    movement = StockMovement.objects.create(
                        movement_type=move_type,
                        tool=tool,
                        quantity=move_qty,
                        employee_name="",
                        movement_date=today,
                        comment=comment,
                        created_by_account=who[:120],
                    )
                    sign = "+" if delta > 0 else ""
                    change_summaries.append(f"{tool.name}: {expected}→{counted} ({sign}{delta})")

                line_rows.append(
                    VisualContainerAuditLine(
                        audit=audit,
                        tool=tool,
                        expected_qty=expected,
                        counted_qty=counted,
                        delta=delta,
                        note=note,
                        stock_movement=movement,
                        status=status,
                    )
                )

            VisualContainerAuditLine.objects.bulk_create(line_rows)
            audit.changes_count = changes
            audit.save(update_fields=["changes_count"])

            now = timezone.now()
            cont.last_audited_at = now
            cont.last_audited_by = who[:120]
            cont.save(update_fields=["last_audited_at", "last_audited_by", "updated_at"])

            summary = (
                f"Инвентаризация ящика «{label}»: без расхождений"
                if changes == 0
                else f"Инвентаризация ящика «{label}»: изменено {changes}"
            )
            InventoryStockEvent.objects.create(
                actor_username=who[:120],
                event_type=InventoryStockEvent.EVENT_CONTAINER_AUDIT,
                summary=summary[:500],
                details={
                    "container_id": cont.id,
                    "cabinet_id": cont.cabinet_id,
                    "label": label,
                    "audit_id": audit.id,
                    "changes_count": changes,
                    "changes": change_summaries[:40],
                    "notes": notes,
                },
            )

            cont = (
                VisualContainer.objects.annotate(items_count=Count("items"))
                .prefetch_related(
                    Prefetch("items", queryset=VisualContainerItem.objects.select_related("tool_item"))
                )
                .get(pk=cont.pk)
            )
            audit = (
                VisualContainerAudit.objects.prefetch_related(
                    Prefetch("lines", queryset=VisualContainerAuditLine.objects.select_related("tool"))
                ).get(pk=audit.pk)
            )
    except ValueError as e:
        return _err(str(e))

    return JsonResponse({
        "ok": True,
        "audit": _serialize_audit(audit),
        "container": _serialize_container(cont, with_items=True),
    })
