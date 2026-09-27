"""Подбор позиций склада под строки инструмента установки наладки."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from django.db.models import F, IntegerField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse

from .models import StockMovement, ToolItem
from .size_label_normalize import normalize_cutting_size_label, size_label_match_variants

# setup tool_type → warehouse category + optional mill/tap filters
_SETUP_TYPE_MAP: dict[str, dict[str, str]] = {
    "Метчик": {"category": "tap", "tap_tool_type": "cutting"},
    "Раскатник": {"category": "tap", "tap_tool_type": "forming"},
    "Резьбофреза": {"category": "tap", "tap_tool_type": "thread_mill"},
    "Сверло": {"category": "drill"},
    "Сверло твердосплавное": {"category": "drill", "tool_material": "carbide"},
    "Центровка": {"category": "center_drill"},
    "Зенкер": {"category": "countersink"},
    "Развертка": {"category": "reamer"},
    "Т-образная фреза": {"category": "end_mill", "mill_type": "t_slot"},
    "Радиусная": {"category": "end_mill", "mill_type": "radius"},
    "Сферическая": {"category": "end_mill", "mill_type": "ball"},
    "Фреза обдирочная": {"category": "end_mill", "mill_type": "roughing"},
    "Фреза черновая": {"category": "end_mill", "mill_type": "roughing"},
    "Фреза чистовая": {"category": "end_mill", "mill_type": "end"},
    "Фреза профильная": {"category": "end_mill", "mill_type": "end"},
    "Фреза фасочная": {"category": "end_mill", "mill_type": "end", "fallback_category": "countersink"},
    "Фреза с СМП": {"category": "body_tool"},
}

_HOLE_MAP = {
    "Сквозной": "through",
    "сквозной": "through",
    "Глухой": "blind",
    "глухой": "blind",
}

_DIAM_CLEAN_RE = re.compile(r"[ØøФфD]\s*", re.IGNORECASE)
_RANGE_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)$",
)
_RADIUS_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*[Rr]\s*(\d+(?:[.,]\d+)?)$",
)
_NUM_RE = re.compile(r"^(\d+(?:[.,]\d+)?)$")


def _to_decimal(raw: str | None) -> Decimal | None:
    text = (raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _fmt_dec(v: Decimal | None) -> str:
    if v is None:
        return ""
    s = format(v, "f").rstrip("0").rstrip(".")
    return s or "0"


@dataclass
class DiameterSpec:
    diameter: Decimal | None = None
    diameter_max: Decimal | None = None
    corner_radius: Decimal | None = None
    size_label: str = ""


def parse_diameter_spec(raw: str) -> DiameterSpec:
    """Разбор ⌀ из строки наладки: 50, Ø50.0, 3R1.5, 2.7-2.8, M5."""
    text = (raw or "").strip()
    if not text:
        return DiameterSpec()
    text = text.replace("×", "x").replace("Х", "x").replace("х", "x")
    text = _DIAM_CLEAN_RE.sub("", text).strip()
    text = re.sub(r"\s+", "", text)

    # Метрический размер резьбы — только если уже есть M/М (голое «50» = Ø фрезы, не M50)
    if re.match(r"^[MmМм]\d", text):
        norm = normalize_cutting_size_label(text)
        if norm:
            return DiameterSpec(size_label=norm)

    m = _RADIUS_RE.fullmatch(text)
    if m:
        return DiameterSpec(diameter=_to_decimal(m.group(1)), corner_radius=_to_decimal(m.group(2)))

    m = _RANGE_RE.fullmatch(text)
    if m:
        a = _to_decimal(m.group(1))
        b = _to_decimal(m.group(2))
        if a is not None and b is not None:
            lo, hi = (a, b) if a <= b else (b, a)
            return DiameterSpec(diameter=lo, diameter_max=hi)
        return DiameterSpec()

    m = _NUM_RE.fullmatch(text)
    if m:
        return DiameterSpec(diameter=_to_decimal(m.group(1)))

    # fallback: первое число в строке
    nums = re.findall(r"\d+(?:[.,]\d+)?", text)
    if nums:
        return DiameterSpec(diameter=_to_decimal(nums[0]))
    return DiameterSpec()


@dataclass
class StockCandidate:
    id: int
    label: str
    qty: int
    address: str
    inventory_url: str


@dataclass
class OpenHolder:
    """Незакрытая выдача: инструмент на руках, можно попросить вернуть."""

    issue_id: int
    employee: str
    remaining: int
    movement_date: str
    tool_label: str
    outcome_url: str = ""


@dataclass
class SetupStockRowResult:
    row_id: int
    tool_number: str
    tool_type: str
    diameter: str
    overhang: str
    tap_hole_type: str
    note: str
    status: str  # ok | empty | unmapped | skip
    status_label: str
    category: str = ""
    filter_params: dict[str, str] = field(default_factory=dict)
    candidates: list[StockCandidate] = field(default_factory=list)
    total_qty: int = 0
    filter_url: str = ""
    open_holders: list[OpenHolder] = field(default_factory=list)


def _base_stock_qs() -> QuerySet:
    return ToolItem.objects.filter(is_deleted=False).select_related(
        "end_mill_spec",
        "tap_spec",
        "center_drill_spec",
        "countersink_spec",
        "drill_spec",
        "reamer_spec",
        "body_tool_spec",
        "insert_spec",
        "collet_spec",
        "tool_extension_spec",
    )


def _size_label_q(field_name: str, raw: str) -> Q:
    variants = size_label_match_variants(raw)
    if not variants:
        return Q(**{f"{field_name}__iexact": raw})
    q = Q()
    for v in variants:
        q |= Q(**{f"{field_name}__iexact": v})
    return q


def _inventory_url(params: dict[str, str], tool_id: int | None = None) -> str:
    q = {"panel": "stock", "show_all": "1"}
    q.update({k: v for k, v in params.items() if v})
    if tool_id:
        q["tool_id"] = str(tool_id)
    return reverse("inventory") + "?" + urlencode(q)


def _build_filter_params(
    category: str,
    mapping: dict[str, str],
    diam: DiameterSpec,
    hole_type: str,
) -> dict[str, str]:
    params: dict[str, str] = {"category": category}
    mill_type = mapping.get("mill_type") or ""
    if mill_type:
        params["mill_type"] = mill_type
    tap_tool_type = mapping.get("tap_tool_type") or ""
    if tap_tool_type:
        params["tap_tool_type"] = tap_tool_type
    tool_material = mapping.get("tool_material") or ""
    if tool_material:
        params["tool_material"] = tool_material

    hole = _HOLE_MAP.get((hole_type or "").strip(), "")
    if category == "tap" and hole:
        params["tap_hole_type"] = hole

    if category == "tap":
        size = diam.size_label or (normalize_cutting_size_label(_fmt_dec(diam.diameter)) if diam.diameter else "")
        if size:
            params["tap_size"] = size
    elif category == "end_mill":
        if diam.diameter is not None and diam.diameter_max is None:
            params["diameter_mm"] = _fmt_dec(diam.diameter)
        if diam.corner_radius is not None:
            params["mill_corner_radius_mm"] = _fmt_dec(diam.corner_radius)
    elif category == "body_tool":
        if diam.diameter is not None and diam.diameter_max is None:
            params["bt_diameter_mm"] = _fmt_dec(diam.diameter)
    elif category == "center_drill":
        if diam.diameter is not None and diam.diameter_max is None:
            params["center_diameter_mm"] = _fmt_dec(diam.diameter)
    elif category == "countersink":
        if diam.diameter is not None and diam.diameter_max is None:
            params["countersink_diameter_mm"] = _fmt_dec(diam.diameter)
        if diam.size_label:
            params["countersink_size_label"] = diam.size_label
    elif category == "drill":
        if diam.diameter is not None and diam.diameter_max is None:
            params["drill_diameter_mm"] = _fmt_dec(diam.diameter)
    elif category == "reamer":
        if diam.diameter is not None and diam.diameter_max is None:
            params["reamer_diameter_mm"] = _fmt_dec(diam.diameter)
    return params


def _apply_filters(qs: QuerySet, category: str, mapping: dict[str, str], diam: DiameterSpec, hole_type: str) -> QuerySet:
    qs = qs.filter(category=category)
    mill_type = mapping.get("mill_type") or ""
    if category == "end_mill" and mill_type:
        qs = qs.filter(end_mill_spec__mill_type=mill_type)
    tap_tool_type = mapping.get("tap_tool_type") or ""
    if category == "tap" and tap_tool_type:
        qs = qs.filter(tap_spec__tap_type=tap_tool_type)
    tool_material = mapping.get("tool_material") or ""
    if tool_material:
        qs = qs.filter(tool_material=tool_material)

    hole = _HOLE_MAP.get((hole_type or "").strip(), "")
    if category == "tap" and hole:
        qs = qs.filter(tap_spec__hole_type=hole)

    if category == "tap":
        size = diam.size_label or (normalize_cutting_size_label(_fmt_dec(diam.diameter)) if diam.diameter else "")
        if size:
            qs = qs.filter(_size_label_q("tap_spec__size_label", size))
    elif category == "end_mill":
        if diam.diameter is not None and diam.diameter_max is not None:
            qs = qs.filter(
                end_mill_spec__diameter_mm__gte=diam.diameter,
                end_mill_spec__diameter_mm__lte=diam.diameter_max,
            )
        elif diam.diameter is not None:
            qs = qs.filter(end_mill_spec__diameter_mm=diam.diameter)
        if diam.corner_radius is not None:
            qs = qs.filter(end_mill_spec__corner_radius_mm=diam.corner_radius)
    elif category == "body_tool":
        if diam.diameter is not None and diam.diameter_max is not None:
            qs = qs.filter(
                body_tool_spec__diameter_mm__gte=diam.diameter,
                body_tool_spec__diameter_mm__lte=diam.diameter_max,
            )
        elif diam.diameter is not None:
            qs = qs.filter(body_tool_spec__diameter_mm=diam.diameter)
    elif category == "center_drill":
        if diam.diameter is not None and diam.diameter_max is not None:
            qs = qs.filter(
                center_drill_spec__diameter_mm__gte=diam.diameter,
                center_drill_spec__diameter_mm__lte=diam.diameter_max,
            )
        elif diam.diameter is not None:
            qs = qs.filter(center_drill_spec__diameter_mm=diam.diameter)
    elif category == "countersink":
        if diam.diameter is not None and diam.diameter_max is not None:
            qs = qs.filter(
                countersink_spec__diameter_mm__gte=diam.diameter,
                countersink_spec__diameter_mm__lte=diam.diameter_max,
            )
        elif diam.diameter is not None:
            qs = qs.filter(countersink_spec__diameter_mm=diam.diameter)
        if diam.size_label:
            qs = qs.filter(_size_label_q("countersink_spec__size_label", diam.size_label))
    elif category == "drill":
        if diam.diameter is not None and diam.diameter_max is not None:
            qs = qs.filter(
                drill_spec__diameter_mm__gte=diam.diameter,
                drill_spec__diameter_mm__lte=diam.diameter_max,
            )
        elif diam.diameter is not None:
            qs = qs.filter(drill_spec__diameter_mm=diam.diameter)
    elif category == "reamer":
        if diam.diameter is not None and diam.diameter_max is not None:
            qs = qs.filter(
                reamer_spec__diameter_mm__gte=diam.diameter,
                reamer_spec__diameter_mm__lte=diam.diameter_max,
            )
        elif diam.diameter is not None:
            qs = qs.filter(reamer_spec__diameter_mm=diam.diameter)
    return qs


def _tool_label(tool: ToolItem) -> str:
    try:
        return tool.issue_select_label() or str(tool)
    except Exception:
        return (tool.name or "").strip() or f"#{tool.pk}"


def _candidates_from_qs(qs: QuerySet, filter_params: dict[str, str]) -> list[StockCandidate]:
    out: list[StockCandidate] = []
    for tool in qs.order_by("warehouse_address", "id")[:80]:
        out.append(
            StockCandidate(
                id=tool.pk,
                label=_tool_label(tool),
                qty=int(tool.quantity or 0),
                address=(tool.warehouse_address or "").strip(),
                inventory_url=_inventory_url(filter_params, tool.pk),
            )
        )
    return out


def _open_issue_movements_qs() -> QuerySet:
    """Выдачи с остатком к возврату/списанию (remaining_qty > 0)."""
    return (
        StockMovement.objects.filter(movement_type="issue", is_reverted=False)
        .select_related("tool")
        .annotate(
            processed_qty=Coalesce(
                Sum("issue_outcomes__quantity"),
                Value(0, output_field=IntegerField()),
            )
        )
        .annotate(remaining_qty=F("quantity") - F("processed_qty"))
        .filter(remaining_qty__gt=0)
        .order_by("-movement_date", "-id")
    )


def _outcome_url(employee: str) -> str:
    params = {"panel": "issue_outcome"}
    if employee:
        params["outcome_employee"] = employee
    return reverse("inventory") + "?" + urlencode(params)


def _find_open_holders(
    *,
    category: str,
    mapping: dict[str, str],
    diam: DiameterSpec,
    hole_type: str,
    candidate_ids: list[int],
    limit: int = 12,
) -> list[OpenHolder]:
    """Кто держит подходящий инструмент (выдан, не возвращён)."""
    tool_ids = [int(x) for x in candidate_ids if x]
    if not tool_ids and category:
        # В т.ч. удалённые позиции — выдача могла остаться открытой.
        qs = ToolItem.objects.all().select_related(
            "end_mill_spec",
            "tap_spec",
            "center_drill_spec",
            "countersink_spec",
            "drill_spec",
            "reamer_spec",
            "body_tool_spec",
        )
        qs = _apply_filters(qs, category, mapping, diam, hole_type)
        tool_ids = list(qs.values_list("pk", flat=True)[:80])
    if not tool_ids:
        return []

    out: list[OpenHolder] = []
    for iss in _open_issue_movements_qs().filter(tool_id__in=tool_ids)[: max(1, min(int(limit), 20))]:
        emp = (iss.employee_name or "").strip()
        tool = iss.tool
        label = _tool_label(tool) if tool else f"#{iss.tool_id}"
        out.append(
            OpenHolder(
                issue_id=int(iss.pk),
                employee=emp or "—",
                remaining=int(getattr(iss, "remaining_qty", 0) or 0),
                movement_date=iss.movement_date.isoformat() if iss.movement_date else "",
                tool_label=label[:90],
                outcome_url=_outcome_url(emp),
            )
        )
    return out


def _holders_summary(holders: list[OpenHolder], *, max_names: int = 3) -> str:
    if not holders:
        return ""
    parts: list[str] = []
    for h in holders[:max_names]:
        parts.append(f"{h.employee} ({h.remaining} шт.)")
    more = len(holders) - max_names
    text = ", ".join(parts)
    if more > 0:
        text += f" и ещё {more}"
    return text


def match_setup_tool_row(row: Any) -> SetupStockRowResult:
    tool_type = (getattr(row, "tool_type", None) or "").strip()
    diameter_raw = (getattr(row, "diameter", None) or "").strip()
    overhang = (getattr(row, "overhang", None) or "").strip()
    hole = (getattr(row, "tap_hole_type", None) or "").strip()
    note = (getattr(row, "name", None) or "").strip()
    tool_number = (getattr(row, "tool_number", None) or "").strip()
    row_id = int(getattr(row, "pk", 0) or 0)

    base = SetupStockRowResult(
        row_id=row_id,
        tool_number=tool_number,
        tool_type=tool_type,
        diameter=diameter_raw,
        overhang=overhang,
        tap_hole_type=hole,
        note=note,
        status="skip",
        status_label="",
    )

    if not tool_type and not diameter_raw and not note:
        base.status = "skip"
        base.status_label = "Пустая строка"
        return base

    mapping = _SETUP_TYPE_MAP.get(tool_type)
    if not mapping:
        base.status = "unmapped"
        base.status_label = "Тип не сопоставлен со складом"
        return base

    diam = parse_diameter_spec(diameter_raw)
    category = mapping["category"]
    filter_params = _build_filter_params(category, mapping, diam, hole)
    qs = _apply_filters(_base_stock_qs(), category, mapping, diam, hole)
    candidates = _candidates_from_qs(qs, filter_params)

    fallback = mapping.get("fallback_category") or ""
    if not candidates and fallback:
        fb_map = {"category": fallback}
        filter_params = _build_filter_params(fallback, fb_map, diam, hole)
        qs = _apply_filters(_base_stock_qs(), fallback, fb_map, diam, hole)
        candidates = _candidates_from_qs(qs, filter_params)
        category = fallback

    base.category = category
    base.filter_params = filter_params
    base.candidates = candidates
    base.total_qty = sum(c.qty for c in candidates)
    if candidates:
        base.status = "ok"
        base.status_label = f"Найдено позиций: {len(candidates)}"
    else:
        base.status = "empty"
        base.status_label = "На складе не найдено"
        # ссылка на фильтр без tool_id — чтобы открыть пустой/широкий список
        base.filter_params = filter_params
    base.filter_url = _inventory_url(filter_params) if filter_params else ""

    # Нет на складе (0 шт. или позиций нет) — смотрим, у кого на руках невозврат.
    if base.status in ("empty", "ok") and base.total_qty <= 0:
        holders = _find_open_holders(
            category=category,
            mapping=mapping,
            diam=diam,
            hole_type=hole,
            candidate_ids=[c.id for c in candidates],
        )
        base.open_holders = holders
        if holders:
            who = _holders_summary(holders)
            if base.status == "empty":
                base.status_label = f"На складе не найдено; на руках: {who}"
            else:
                base.status_label = f"Остаток 0; на руках: {who}"
    return base


def match_setup_tools(tools) -> list[SetupStockRowResult]:
    results: list[SetupStockRowResult] = []
    for row in tools:
        res = match_setup_tool_row(row)
        if res.status == "skip":
            continue
        results.append(res)
    return results
