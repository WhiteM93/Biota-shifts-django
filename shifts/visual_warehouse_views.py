"""Визуальный склад: шкафы → ячейки → контейнеры → содержимое."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, F, Prefetch, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .collet_constants import COLLET_TYPES, COLLET_TYPE_VALUES
from .models import (
    COATING_TYPE_TOOLTIPS,
    COUNTERSINK_TYPES,
    END_MILL_TYPES,
    TAP_HOLE_TYPES,
    TAP_TOOL_TYPES,
    CenterDrillSpec,
    CountersinkSpec,
    DrillSpec,
    EndMillSpec,
    InventoryStockEvent,
    StockMovement,
    TapSpec,
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
MAX_ORGANIZER_TIERS = 8
MAX_ORGANIZER_COLUMNS = 6
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_VALID_CATEGORIES = {c for c, _ in VisualContainerItem.TOOL_CATEGORY_CHOICES if c}
_VALID_MILL_TYPES = {c for c, _ in END_MILL_TYPES}
_VALID_TAP_TYPES = {c for c, _ in TAP_TOOL_TYPES}
_VALID_TAP_HOLE_TYPES = {c for c, _ in TAP_HOLE_TYPES}
_VALID_COUNTERSINK_TYPES = {c for c, _ in COUNTERSINK_TYPES}
_VALID_COLLET_TYPES = set(COLLET_TYPE_VALUES)
_DIAMETER_FIELD_BY_CATEGORY = {
    "end_mill": "end_mill_spec__diameter_mm",
    "drill": "drill_spec__diameter_mm",
    "center_drill": "center_drill_spec__diameter_mm",
    "countersink": "countersink_spec__diameter_mm",
}


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
        "mill_type": (getattr(item, "mill_type", None) or ""),
        "tap_type": (getattr(item, "tap_type", None) or ""),
        "hole_type": (getattr(item, "hole_type", None) or ""),
        "countersink_type": (getattr(item, "countersink_type", None) or ""),
        "collet_type": (getattr(item, "collet_type", None) or ""),
        "size_label": (getattr(item, "size_label", None) or ""),
        "diameter_from_mm": float(item.diameter_from_mm) if item.diameter_from_mm is not None else None,
        "diameter_to_mm": float(item.diameter_to_mm) if item.diameter_to_mm is not None else None,
        "tool_item_id": item.tool_item_id,
        "quantity_note": item.quantity_note or "",
        "notes": item.notes or "",
        "sort_order": item.sort_order,
        "stock_qty": stock_qty,
    }


def _cutting_diameter_mm(tool: ToolItem):
    cat = tool.category or ""
    if cat == "end_mill":
        em = getattr(tool, "end_mill_spec", None)
        return em.diameter_mm if em else None
    if cat == "drill":
        dr = getattr(tool, "drill_spec", None)
        return dr.diameter_mm if dr else None
    if cat == "center_drill":
        cd = getattr(tool, "center_drill_spec", None)
        return cd.diameter_mm if cd else None
    if cat == "countersink":
        cs = getattr(tool, "countersink_spec", None)
        return cs.diameter_mm if cs else None
    return tool.main_diameter_mm


def _stock_qty_for_item(item: VisualContainerItem) -> int | None:
    if item.tool_item_id and item.tool_item and not item.tool_item.is_deleted:
        return int(item.tool_item.quantity or 0)
    if not item.tool_category:
        return None
    qs = _tool_qs_for_filter(
        category=item.tool_category,
        d_from=item.diameter_from_mm,
        d_to=item.diameter_to_mm,
        mill_type=getattr(item, "mill_type", None) or "",
        tap_type=getattr(item, "tap_type", None) or "",
        hole_type=getattr(item, "hole_type", None) or "",
        countersink_type=getattr(item, "countersink_type", None) or "",
        collet_type=getattr(item, "collet_type", None) or "",
        size_label=getattr(item, "size_label", None) or "",
    )
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
    cutting = _cutting_diameter_mm(tool)
    diam = float(cutting) if cutting is not None else None
    coating = (tool.coating_type or "none").strip() or "none"
    coating_label = "без покрытия" if coating == "none" else str(tool.get_coating_type_display())
    wm_codes = tool.work_material_codes_list()
    mill_type = ""
    mill_type_label = ""
    subtype = ""
    subtype_label = ""
    size_label = ""
    hole_type = ""
    hole_type_label = ""
    overall_length_mm = None
    cutting_length_mm = None
    flutes_count = None
    corner_radius_mm = None
    pitch_mm = None
    angle_deg = None
    if tool.category == "end_mill":
        em = getattr(tool, "end_mill_spec", None)
        if em:
            mill_type = (em.mill_type or "").strip()
            mill_type_label = em.get_mill_type_display() if mill_type else ""
            subtype = mill_type
            subtype_label = mill_type_label
            overall_length_mm = float(em.overall_length_mm) if em.overall_length_mm is not None else None
            cutting_length_mm = float(em.cutting_length_mm) if em.cutting_length_mm is not None else None
            flutes_count = int(em.flutes_count) if em.flutes_count is not None else None
            corner_radius_mm = float(em.corner_radius_mm) if em.corner_radius_mm is not None else None
    elif tool.category == "tap":
        tap = getattr(tool, "tap_spec", None)
        if tap:
            subtype = (tap.tap_type or "").strip()
            subtype_label = tap.get_tap_type_display() if subtype else ""
            size_label = (tap.size_label or "").strip()
            hole_type = (tap.hole_type or "").strip()
            hole_type_label = tap.get_hole_type_display() if hole_type else ""
            overall_length_mm = float(tap.overall_length_mm) if tap.overall_length_mm is not None else None
            cutting_length_mm = float(tap.cutting_length_mm) if tap.cutting_length_mm is not None else None
            pitch_mm = float(tap.pitch_mm) if tap.pitch_mm is not None else None
    elif tool.category == "countersink":
        cs = getattr(tool, "countersink_spec", None)
        if cs:
            subtype = (cs.countersink_type or "").strip()
            subtype_label = cs.get_countersink_type_display() if subtype else ""
            overall_length_mm = float(cs.overall_length_mm) if cs.overall_length_mm is not None else None
            flutes_count = int(cs.flutes_count) if cs.flutes_count is not None else None
            angle_deg = str(cs.angle_deg) if cs.angle_deg else ""
            size_label = (cs.size_label or "").strip()
    elif tool.category == "collet":
        cl = getattr(tool, "collet_spec", None)
        if cl:
            subtype = (cl.collet_type or "").strip()
            subtype_label = cl.get_collet_type_display() if subtype else ""
    elif tool.category == "center_drill":
        cd = getattr(tool, "center_drill_spec", None)
        if cd:
            overall_length_mm = float(cd.overall_length_mm) if cd.overall_length_mm is not None else None
            angle_deg = str(cd.angle_deg) if cd.angle_deg else ""
    elif tool.category == "drill":
        dr = getattr(tool, "drill_spec", None)
        if dr:
            overall_length_mm = float(dr.overall_length_mm) if dr.overall_length_mm is not None else None
            cutting_length_mm = float(dr.cutting_length_mm) if dr.cutting_length_mm is not None else None
            angle_deg = float(dr.angle_deg) if dr.angle_deg is not None else None
    card = tool.issue_combo_card()
    return {
        "id": tool.id,
        "name": tool.name,
        "category": tool.category or "",
        "category_label": tool.get_category_display() if tool.category else "",
        "diameter_mm": diam,
        "mill_type": mill_type,
        "mill_type_label": mill_type_label,
        "subtype": subtype,
        "subtype_label": subtype_label,
        "size_label": size_label,
        "hole_type": hole_type,
        "hole_type_label": hole_type_label,
        "overall_length_mm": overall_length_mm,
        "cutting_length_mm": cutting_length_mm,
        "flutes_count": flutes_count,
        "corner_radius_mm": corner_radius_mm,
        "pitch_mm": pitch_mm,
        "angle_deg": angle_deg if angle_deg not in ("", None) else None,
        "type_label": (card.get("tool_type") or "").strip(),
        "specs": (card.get("specs") or "").strip(),
        "main_diameter_mm": float(tool.main_diameter_mm) if tool.main_diameter_mm is not None else None,
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
    mill_type: str = "",
    tap_type: str = "",
    hole_type: str = "",
    countersink_type: str = "",
    collet_type: str = "",
    size_label: str = "",
):
    if tool_item_id:
        return ToolItem.objects.filter(pk=tool_item_id, is_deleted=False).select_related(
            "end_mill_spec",
            "drill_spec",
            "center_drill_spec",
            "countersink_spec",
            "tap_spec",
            "collet_spec",
            "insert_spec",
        )
    if not category:
        return ToolItem.objects.none()
    qs = ToolItem.objects.filter(is_deleted=False, category=category).select_related(
        "end_mill_spec",
        "drill_spec",
        "center_drill_spec",
        "countersink_spec",
        "tap_spec",
        "collet_spec",
        "insert_spec",
    )
    diam_field = _DIAMETER_FIELD_BY_CATEGORY.get(category)
    if diam_field and (d_from is not None or d_to is not None):
        # Режущий Ø из спецификации; если пусто — запасной main_diameter_mm
        qs = qs.annotate(_match_diameter=Coalesce(F(diam_field), F("main_diameter_mm")))
        if d_from is not None:
            qs = qs.filter(_match_diameter__gte=d_from)
        if d_to is not None:
            qs = qs.filter(_match_diameter__lte=d_to)
    elif category == "tap":
        # У метчиков режущий Ø обычно в main_diameter / размере — оставляем запасной фильтр
        if d_from is not None:
            qs = qs.filter(main_diameter_mm__gte=d_from)
        if d_to is not None:
            qs = qs.filter(main_diameter_mm__lte=d_to)
    if category == "end_mill" and mill_type:
        qs = qs.filter(end_mill_spec__mill_type=mill_type)
    if category == "tap" and tap_type:
        qs = qs.filter(tap_spec__tap_type=tap_type)
    if category == "tap" and hole_type:
        qs = qs.filter(tap_spec__hole_type=hole_type)
    if category == "tap" and size_label:
        qs = qs.filter(tap_spec__size_label__icontains=size_label.strip())
    if category == "countersink" and countersink_type:
        qs = qs.filter(countersink_spec__countersink_type=countersink_type)
    if category == "collet" and collet_type:
        qs = qs.filter(collet_spec__collet_type=collet_type)
    return qs


def _matching_tools_for_container(c: VisualContainer, items: list[VisualContainerItem] | None = None) -> list[dict]:
    """Список реальных позиций склада, попадающих под содержимое ящика."""
    seen: set[int] = set()
    out: list[dict] = []
    rows = items if items is not None else list(c.items.select_related("tool_item").all())

    def _add_from_qs(qs):
        for tool in qs.order_by("category", "name"):
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
                    mill_type=getattr(item, "mill_type", None) or "",
                    tap_type=getattr(item, "tap_type", None) or "",
                    hole_type=getattr(item, "hole_type", None) or "",
                    countersink_type=getattr(item, "countersink_type", None) or "",
                    collet_type=getattr(item, "collet_type", None) or "",
                    size_label=getattr(item, "size_label", None) or "",
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

    def _sort_key(t: dict):
        diam = t.get("diameter_mm")
        length = t.get("overall_length_mm")
        cutting = t.get("cutting_length_mm")
        return (
            t.get("category") or "",
            diam if diam is not None else 1e9,
            length if length is not None else 1e9,
            cutting if cutting is not None else 1e9,
            (t.get("size_label") or "").lower(),
            (t.get("name") or "").lower(),
            t.get("id") or 0,
        )

    out.sort(key=_sort_key)
    return out


def _normalize_cabinet_kind(raw) -> str:
    kind = str(raw or "").strip().lower()
    if kind == VisualCabinet.KIND_RACK:
        return VisualCabinet.KIND_RACK
    if kind == VisualCabinet.KIND_DRAWER_CHEST:
        return VisualCabinet.KIND_DRAWER_CHEST
    return VisualCabinet.KIND_CABINET


def _normalize_container_kind(raw) -> str:
    kind = str(raw or "").strip().lower()
    if kind == VisualContainer.KIND_SHELF_SLOT:
        return VisualContainer.KIND_SHELF_SLOT
    if kind == VisualContainer.KIND_DRAWER_CELL:
        return VisualContainer.KIND_DRAWER_CELL
    if kind == VisualContainer.KIND_ORGANIZER:
        return VisualContainer.KIND_ORGANIZER
    return VisualContainer.KIND_BIN


def _default_organizer_cell_label(tier: int, col: int, cols: int) -> str:
    if cols == 2:
        side = "СК" if col == 1 else "ГЛ"
        return f"Ярус {tier} {side}"
    return f"Ярус {tier} · {col}"


def _serialize_container(
    c: VisualContainer,
    *,
    with_items: bool = False,
    children: list[VisualContainer] | None = None,
) -> dict:
    color = (c.color or "").strip()
    if not _HEX_RE.match(color):
        color = "#e74c3c"
    kind = _normalize_container_kind(getattr(c, "kind", None))
    if getattr(c, "parent_id", None) and kind == VisualContainer.KIND_BIN:
        kind = VisualContainer.KIND_DRAWER_CELL
    data = {
        "id": c.id,
        "cabinet_id": c.cabinet_id,
        "parent_id": getattr(c, "parent_id", None),
        "kind": kind,
        "shelf": c.shelf,
        "stack": max(1, int(c.stack or 1)),
        "column": c.column,
        "col_span": max(1, int(c.col_span or 1)),
        "row_span": max(1, int(c.row_span or 1)),
        "inner_tiers": max(1, int(getattr(c, "inner_tiers", 1) or 1)),
        "inner_columns": max(1, int(getattr(c, "inner_columns", 1) or 1)),
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
    if children is not None:
        data["children"] = [
            _serialize_container(ch) for ch in sorted(children, key=lambda x: (x.shelf, x.column, x.id))
        ]
    elif kind == VisualContainer.KIND_ORGANIZER:
        kids = list(c.children.all()) if hasattr(c, "_prefetched_objects_cache") and "children" in getattr(c, "_prefetched_objects_cache", {}) else list(c.children.all())
        data["children"] = [
            _serialize_container(ch) for ch in sorted(kids, key=lambda x: (x.shelf, x.column, x.id))
        ]
    if with_items:
        items = list(c.items.select_related("tool_item").all())
        data["items"] = [_serialize_item(it, _stock_qty_for_item(it)) for it in items]
        data["stock_tools"] = _matching_tools_for_container(c, items)
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
    qs = VisualContainer.objects.filter(cabinet=cab, parent__isnull=True)
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


def _ensure_organizer_children(org: VisualContainer) -> None:
    tiers = max(1, min(MAX_ORGANIZER_TIERS, int(org.inner_tiers or 1)))
    cols = max(1, min(MAX_ORGANIZER_COLUMNS, int(org.inner_columns or 1)))
    org.inner_tiers = tiers
    org.inner_columns = cols
    existing = {(ch.shelf, ch.column): ch for ch in org.children.all()}
    to_create: list[VisualContainer] = []
    for t in range(1, tiers + 1):
        for c in range(1, cols + 1):
            if (t, c) in existing:
                continue
            to_create.append(
                VisualContainer(
                    cabinet_id=org.cabinet_id,
                    parent=org,
                    kind=VisualContainer.KIND_DRAWER_CELL,
                    shelf=t,
                    stack=1,
                    column=c,
                    col_span=1,
                    row_span=1,
                    inner_tiers=1,
                    inner_columns=1,
                    label=_default_organizer_cell_label(t, c, cols),
                    color=org.color or "#e74c3c",
                )
            )
    if to_create:
        VisualContainer.objects.bulk_create(to_create)
    # Удаляем лишние пустые ячейки за пределами сетки
    for (t, c), ch in existing.items():
        if t > tiers or c > cols:
            if ch.items.exists():
                continue
            ch.delete()


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
        all_conts = list(cab.containers.all())
        children_by_parent: dict[int, list[VisualContainer]] = {}
        tops: list[VisualContainer] = []
        for c in all_conts:
            if getattr(c, "parent_id", None):
                children_by_parent.setdefault(c.parent_id, []).append(c)
            else:
                tops.append(c)
        data["containers"] = [
            _serialize_container(c, children=children_by_parent.get(c.id, []))
            for c in tops
        ]
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
            "end_mill_types": [{"value": v, "label": lab} for v, lab in END_MILL_TYPES],
            "tap_types": [{"value": v, "label": lab} for v, lab in TAP_TOOL_TYPES],
            "tap_hole_types": [{"value": v, "label": lab} for v, lab in TAP_HOLE_TYPES],
            "countersink_types": [{"value": v, "label": lab} for v, lab in COUNTERSINK_TYPES],
            "collet_types": [{"value": v, "label": lab} for v, lab in COLLET_TYPES],
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
        if new_kind != VisualCabinet.KIND_RACK:
            has_slot = cab.containers.filter(kind=VisualContainer.KIND_SHELF_SLOT).exists()
            if has_slot:
                return _err(
                    "Нельзя сменить тип: есть зоны «на полке». Удалите их или оставьте стеллаж."
                )
        if new_kind != VisualCabinet.KIND_DRAWER_CHEST:
            has_cells = cab.containers.filter(
                kind=VisualContainer.KIND_DRAWER_CELL,
                parent__isnull=True,
            ).exists()
            if has_cells:
                return _err(
                    "Нельзя сменить тип: есть ячейки ящика. Удалите их или оставьте тумбу с ящиками."
                )
        cab.kind = new_kind
    if "notes" in body:
        cab.notes = str(body.get("notes") or "").strip()[:300]
    if "shelves" in body or "columns" in body:
        shelves = _clamp_int(body.get("shelves", cab.shelves), cab.shelves, 1, MAX_SHELVES)
        columns = _clamp_int(body.get("columns", cab.columns), cab.columns, 1, MAX_COLUMNS)
        for cont in cab.containers.filter(parent__isnull=True):
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
    parent_id = body.get("parent_id")
    parent = None
    if parent_id:
        try:
            parent = VisualContainer.objects.get(pk=int(parent_id), cabinet=cab, kind=VisualContainer.KIND_ORGANIZER)
        except (TypeError, ValueError, VisualContainer.DoesNotExist):
            return _err("Некорректный органайзер для ячейки")

    if cont_kind == VisualContainer.KIND_SHELF_SLOT and cab_kind != VisualCabinet.KIND_RACK:
        return _err("Зона «на полке» доступна только на стеллаже")
    if cont_kind == VisualContainer.KIND_SHELF_SLOT and stack > 1:
        return _err("Зона «на полке» не ставится в стопку — только ярус 1")
    if cont_kind == VisualContainer.KIND_DRAWER_CELL:
        if parent:
            pass  # ячейка внутри органайзера в шкафу/стеллаже
        elif cab_kind != VisualCabinet.KIND_DRAWER_CHEST:
            return _err("Ячейка ящика доступна только в тумбе с ящиками или внутри органайзера")
        if stack > 1:
            return _err("Ячейка ящика не ставится в стопку — только ярус 1")
    if cont_kind == VisualContainer.KIND_ORGANIZER:
        if parent:
            return _err("Органайзер нельзя вложить в другой органайзер")
        if cab_kind == VisualCabinet.KIND_DRAWER_CHEST:
            return _err("Органайзер ставьте в шкаф или на стеллаж, не в тумбу с ящиками")
        stack = 1
    if cab_kind == VisualCabinet.KIND_DRAWER_CHEST and cont_kind == VisualContainer.KIND_SHELF_SLOT:
        return _err("На тумбе с ящиками нельзя зону «на полке» — используйте ячейку ящика")
    # В тумбе по умолчанию ячейки лежат в одном ярусе-ящике
    if cab_kind == VisualCabinet.KIND_DRAWER_CHEST and cont_kind == VisualContainer.KIND_BIN and stack > 1:
        return _err("В тумбе с ящиками стопки не используются — ячейки в одном ярусе")

    inner_tiers = _clamp_int(body.get("inner_tiers"), 3, 1, MAX_ORGANIZER_TIERS)
    inner_columns = _clamp_int(body.get("inner_columns"), 2, 1, MAX_ORGANIZER_COLUMNS)
    if cont_kind != VisualContainer.KIND_ORGANIZER:
        inner_tiers = 1
        inner_columns = 1

    cid = body.get("id")
    exclude_id = int(cid) if cid else None

    # Ячейки органайзера не занимают место на полке шкафа — координаты внутри родителя
    if parent:
        shelf = _clamp_int(body.get("shelf"), 1, 1, max(1, int(parent.inner_tiers or 1)))
        column = _clamp_int(body.get("column"), 1, 1, max(1, int(parent.inner_columns or 1)))
        col_span = 1
        stack = 1
    else:
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
        if cont.parent_id and cont_kind == VisualContainer.KIND_ORGANIZER:
            return _err("Нельзя превратить ячейку в органайзер")
        cont.kind = cont_kind
        cont.shelf = shelf
        cont.stack = stack
        cont.column = column
        cont.col_span = col_span
        cont.row_span = 1
        cont.label = label
        cont.color = color
        cont.notes = notes
        if cont_kind == VisualContainer.KIND_ORGANIZER:
            cont.inner_tiers = inner_tiers
            cont.inner_columns = inner_columns
        cont.save()
        if cont_kind == VisualContainer.KIND_ORGANIZER:
            _ensure_organizer_children(cont)
    else:
        cont = VisualContainer.objects.create(
            cabinet=cab,
            parent=parent,
            kind=cont_kind,
            shelf=shelf,
            stack=stack,
            column=column,
            col_span=col_span,
            row_span=1,
            inner_tiers=inner_tiers if cont_kind == VisualContainer.KIND_ORGANIZER else 1,
            inner_columns=inner_columns if cont_kind == VisualContainer.KIND_ORGANIZER else 1,
            label=label,
            color=color,
            notes=notes,
        )
        if cont_kind == VisualContainer.KIND_ORGANIZER:
            _ensure_organizer_children(cont)
    cont = (
        VisualContainer.objects.annotate(items_count=Count("items"))
        .prefetch_related(
            Prefetch("items", queryset=VisualContainerItem.objects.select_related("tool_item")),
            "children",
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
    mill_type = str(body.get("mill_type") or "").strip()
    if mill_type and mill_type not in _VALID_MILL_TYPES:
        return _err("Некорректный тип фрезы")
    if category != "end_mill":
        mill_type = ""
    tap_type = str(body.get("tap_type") or "").strip()
    if tap_type and tap_type not in _VALID_TAP_TYPES:
        return _err("Некорректный тип резьбового инструмента")
    if category != "tap":
        tap_type = ""
    hole_type = str(body.get("hole_type") or "").strip()
    if hole_type and hole_type not in _VALID_TAP_HOLE_TYPES:
        return _err("Некорректный тип отверстия")
    if category != "tap":
        hole_type = ""
    countersink_type = str(body.get("countersink_type") or "").strip()
    if countersink_type and countersink_type not in _VALID_COUNTERSINK_TYPES:
        return _err("Некорректный тип зенкера")
    if category != "countersink":
        countersink_type = ""
    collet_type = str(body.get("collet_type") or "").strip()
    if collet_type and collet_type not in _VALID_COLLET_TYPES:
        return _err("Некорректный тип цанги")
    if category != "collet":
        collet_type = ""
    size_label = str(body.get("size_label") or "").strip()[:32]
    if category != "tap":
        size_label = ""
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
        item.mill_type = mill_type
        item.tap_type = tap_type
        item.hole_type = hole_type
        item.countersink_type = countersink_type
        item.collet_type = collet_type
        item.size_label = size_label
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
            mill_type=mill_type,
            tap_type=tap_type,
            hole_type=hole_type,
            countersink_type=countersink_type,
            collet_type=collet_type,
            size_label=size_label,
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


def _auto_tool_name(
    category: str,
    *,
    diameter=None,
    mill_type: str = "",
    tap_type: str = "",
    hole_type: str = "",
    size_label: str = "",
) -> str:
    cat_labels = dict(VisualContainerItem.TOOL_CATEGORY_CHOICES)
    base = cat_labels.get(category) or "Инструмент"
    if category == "end_mill":
        mt = dict(END_MILL_TYPES).get(mill_type) or ""
        parts = [p for p in [mt or "Фреза", f"Ø{diameter}" if diameter is not None else ""] if p]
        return " ".join(parts)[:200] or base
    if category == "tap":
        tt = dict(TAP_TOOL_TYPES).get(tap_type) or "Метчик"
        ht = dict(TAP_HOLE_TYPES).get(hole_type) or ""
        parts = [p for p in [tt, size_label, ht] if p]
        return (" ".join(parts) if parts else tt)[:200]
    if diameter is not None:
        return f"{base} Ø{diameter}"[:200]
    return base[:200]


def _create_tool_for_audit(data: dict) -> ToolItem:
    """Создать позицию склада из строки «новый инструмент» при инвентаризации (qty=0)."""
    if not isinstance(data, dict):
        raise ValueError("Некорректные данные нового инструмента")
    category = str(data.get("category") or "").strip()
    if category not in _VALID_CATEGORIES:
        raise ValueError("Укажите категорию нового инструмента")
    counted = _clamp_int(data.get("quantity"), -1, 0, 999999)
    if counted < 0:
        raise ValueError("Укажите количество нового инструмента")
    diameter = _dec(data.get("diameter_mm"))
    mill_type = str(data.get("mill_type") or "").strip()
    if mill_type and mill_type not in _VALID_MILL_TYPES:
        raise ValueError("Некорректный тип фрезы")
    if category != "end_mill":
        mill_type = ""
    tap_type = str(data.get("tap_type") or "").strip()
    if tap_type and tap_type not in _VALID_TAP_TYPES:
        raise ValueError("Некорректный тип резьбового инструмента")
    if category != "tap":
        tap_type = ""
    hole_type = str(data.get("hole_type") or "").strip()
    if hole_type and hole_type not in _VALID_TAP_HOLE_TYPES:
        raise ValueError("Некорректный тип отверстия")
    if category != "tap":
        hole_type = ""
    size_label = str(data.get("size_label") or "").strip()[:32]
    flutes = _clamp_int(data.get("flutes_count"), 0, 0, 20) or None
    main_d = _dec(data.get("main_diameter_mm"))
    name = str(data.get("name") or "").strip()[:200]
    if not name:
        name = _auto_tool_name(
            category,
            diameter=diameter,
            mill_type=mill_type,
            tap_type=tap_type,
            hole_type=hole_type,
            size_label=size_label,
        )

    if category in {"end_mill", "drill", "center_drill", "countersink"} and diameter is None:
        raise ValueError("Укажите диаметр нового инструмента")
    if category == "tap" and not size_label:
        raise ValueError("Укажите размер метчика (например M6)")
    if category in {"insert", "collet"} and not str(data.get("name") or "").strip():
        raise ValueError("Укажите название пластины/цанги")

    tool = ToolItem.objects.create(
        category=category,
        name=name,
        main_diameter_mm=main_d if main_d is not None else diameter,
        quantity=0,
    )
    if category == "end_mill":
        EndMillSpec.objects.create(
            tool=tool,
            mill_type=mill_type or "end",
            diameter_mm=diameter,
            flutes_count=flutes,
        )
    elif category == "drill":
        DrillSpec.objects.create(tool=tool, diameter_mm=diameter)
    elif category == "center_drill":
        CenterDrillSpec.objects.create(tool=tool, diameter_mm=diameter)
    elif category == "countersink":
        CountersinkSpec.objects.create(tool=tool, diameter_mm=diameter)
    elif category == "tap":
        TapSpec.objects.create(
            tool=tool,
            size_label=size_label,
            tap_type=tap_type or "cutting",
            hole_type=hole_type or "any",
        )
    return tool


def _link_tool_to_container(cont: VisualContainer, tool: ToolItem) -> None:
    """Привязать найденный инструмент к ящику, чтобы он оставался в списке."""
    if VisualContainerItem.objects.filter(container=cont, tool_item=tool).exists():
        return
    if cont.items.count() >= MAX_ITEMS_PER_CONTAINER:
        raise ValueError(f"В ящике слишком много правил (макс. {MAX_ITEMS_PER_CONTAINER})")
    VisualContainerItem.objects.create(
        container=cont,
        title=(tool.name or "Инструмент")[:200],
        tool_category=tool.category or "",
        tool_item=tool,
        sort_order=900 + cont.items.count(),
    )


@write_permission_required
def _container_audit_create(request, cont: VisualContainer):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    raw_lines = body.get("lines")
    if raw_lines is None:
        raw_lines = []
    if not isinstance(raw_lines, list):
        return _err("Некорректные строки инвентаризации")
    raw_new = body.get("new_tools")
    if raw_new is None:
        raw_new = []
    if not isinstance(raw_new, list):
        return _err("Некорректный список новых инструментов")
    if not raw_lines and not raw_new:
        return _err("Укажите строки инвентаризации или добавьте новый инструмент")
    if len(raw_lines) + len(raw_new) > MAX_AUDIT_LINES:
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

    new_payloads: list[dict] = []
    for row in raw_new:
        if not isinstance(row, dict):
            return _err("Некорректные данные нового инструмента")
        new_payloads.append(row)

    allowed_ids = {t["id"] for t in _matching_tools_for_container(cont)}
    if allowed_ids and seen and not seen.issubset(allowed_ids):
        return _err("В проверке есть инструмент, которого нет в этом ящике")

    today = timezone.localdate()

    try:
        with transaction.atomic():
            created_ids: set[int] = set()
            for payload in new_payloads:
                tool = _create_tool_for_audit(payload)
                _link_tool_to_container(cont, tool)
                created_ids.add(tool.pk)
                counted = _clamp_int(payload.get("quantity"), -1, 0, 999999)
                note = str(payload.get("note") or "").strip()[:300] or "найден при инвентаризации"
                if tool.pk in seen:
                    raise ValueError("Дубликат инструмента в строках")
                seen.add(tool.pk)
                parsed.append((tool.pk, counted, note))

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
                    reason = note or ("новый инструмент" if tool_id in created_ids else "расхождение")
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
                    "new_tools_count": len(created_ids),
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
