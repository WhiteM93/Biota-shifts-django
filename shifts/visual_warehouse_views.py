"""Визуальный склад: шкафы → ячейки → контейнеры → содержимое."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import ToolItem, VisualCabinet, VisualContainer, VisualContainerItem

MAX_CABINETS = 40
MAX_SHELVES = 20
MAX_COLUMNS = 12
MAX_ITEMS_PER_CONTAINER = 80
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_VALID_CATEGORIES = {c for c, _ in VisualContainerItem.TOOL_CATEGORY_CHOICES if c}


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


def _serialize_container(c: VisualContainer, *, with_items: bool = False) -> dict:
    color = (c.color or "").strip()
    if not _HEX_RE.match(color):
        color = "#e74c3c"
    data = {
        "id": c.id,
        "cabinet_id": c.cabinet_id,
        "shelf": c.shelf,
        "stack": max(1, int(c.stack or 1)),
        "column": c.column,
        "col_span": max(1, int(c.col_span or 1)),
        "row_span": max(1, int(c.row_span or 1)),
        "label": c.label,
        "color": color,
        "notes": c.notes or "",
        "items_count": getattr(c, "items_count", None),
    }
    if data["items_count"] is None:
        data["items_count"] = c.items.count()
    if with_items:
        items = list(c.items.select_related("tool_item").all())
        data["items"] = [_serialize_item(it, _stock_qty_for_item(it)) for it in items]
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
    shelves = _clamp_int(body.get("shelves"), 4, 1, MAX_SHELVES)
    columns = _clamp_int(body.get("columns"), 3, 1, MAX_COLUMNS)
    notes = str(body.get("notes") or "").strip()[:300]
    cab = VisualCabinet.objects.create(
        name=name,
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
    label = str(body.get("label") or "").strip()[:120]
    if not label:
        return _err("Укажите подпись контейнера")
    color = str(body.get("color") or "#e74c3c").strip()
    if not _HEX_RE.match(color):
        color = "#e74c3c"
    notes = str(body.get("notes") or "").strip()[:300]
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
