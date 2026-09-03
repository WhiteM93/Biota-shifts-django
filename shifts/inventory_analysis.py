"""Сводка и контроль остатков склада (вкладка «Анализ»)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from urllib.parse import urlencode

from django.db.models import Count, Q, Sum
from django.urls import reverse

from shifts.models import InventoryWatchTemplate, ToolItem

# group_field → ORM path (values/annotate)
GROUP_FIELD_PATHS: dict[str, dict[str, str]] = {
    "end_mill": {
        "diameter_mm": "end_mill_spec__diameter_mm",
        "mill_type": "end_mill_spec__mill_type",
        "flutes_count": "end_mill_spec__flutes_count",
        "corner_radius_mm": "end_mill_spec__corner_radius_mm",
    },
    "body_tool": {
        "diameter_mm": "body_tool_spec__diameter_mm",
        "family": "body_tool_spec__family",
        "cutter_type": "body_tool_spec__cutter_type",
        "teeth_count": "body_tool_spec__teeth_count",
        "coupling": "body_tool_spec__coupling",
        "insert_family": "body_tool_spec__insert_family",
        "insert_size": "body_tool_spec__insert_size",
        "mount_diameter_mm": "body_tool_spec__mount_diameter_mm",
        "cutting_length_mm": "body_tool_spec__cutting_length_mm",
        "overall_length_mm": "body_tool_spec__overall_length_mm",
        "shank_type": "body_tool_spec__shank_type",
        "variable_angle": "body_tool_spec__variable_angle",
        "hs_body_style": "body_tool_spec__hs_body_style",
        "has_purpose": "body_tool_spec__has_purpose",
        "corner_radius_mm": "body_tool_spec__corner_radius_mm",
        "cutting_length_mm": "body_tool_spec__cutting_length_mm",
        "ap_max_mm": "body_tool_spec__ap_max_mm",
        "approach_angle_deg": "body_tool_spec__approach_angle_deg",
        "brand": "body_tool_spec__brand",
    },
    "tap": {
        "size_label": "tap_spec__size_label",
        "thread_standard": "tap_spec__thread_standard",
        "tap_type": "tap_spec__tap_type",
    },
    "center_drill": {
        "diameter_mm": "center_drill_spec__diameter_mm",
        "angle_deg": "center_drill_spec__angle_deg",
    },
    "countersink": {
        "diameter_mm": "countersink_spec__diameter_mm",
        "countersink_type": "countersink_spec__countersink_type",
        "angle_deg": "countersink_spec__angle_deg",
    },
    "drill": {
        "diameter_mm": "drill_spec__diameter_mm",
        "angle_deg": "drill_spec__angle_deg",
    },
    "insert": {
        "insert_shape": "insert_spec__insert_shape",
        "cutting_edge_length_code": "insert_spec__cutting_edge_length_code",
        "iso_designation": "insert_spec__iso_designation",
        "milling_family": "insert_spec__milling_family",
        "chipbreaker_grade": "insert_spec__chipbreaker_grade",
    },
    "collet": {
        "collet_type": "collet_spec__collet_type",
        "er_size": "collet_spec__er_size",
        "clamp_range": "collet_spec__clamp_range",
        "inner_diameter": "collet_spec__inner_diameter",
    },
}

GROUP_FIELD_LABELS: dict[str, dict[str, str]] = {
    cat: {key: key for key in paths}
    for cat, paths in GROUP_FIELD_PATHS.items()
}

GROUP_FIELD_LABELS["end_mill"].update(
    {
        "diameter_mm": "Диаметр, мм",
        "mill_type": "Тип фрезы",
        "flutes_count": "Кромок",
        "corner_radius_mm": "Радиус, мм",
    }
)
GROUP_FIELD_LABELS["body_tool"].update(
    {
        "diameter_mm": "Диаметр, мм",
        "family": "Семейство",
        "cutter_type": "Тип",
        "teeth_count": "Z",
        "coupling": "Крепление",
        "insert_family": "Формфактор пластины",
        "insert_size": "Размер пластины",
        "mount_diameter_mm": "d посадки, мм",
        "overall_length_mm": "L, мм",
        "shank_type": "Хвостовик",
        "variable_angle": "Перем. угол",
        "hs_body_style": "Насадная/концевая",
        "has_purpose": "Назначение",
        "corner_radius_mm": "Радиус, мм",
        "cutting_length_mm": "H (ширина паза), мм",
        "ap_max_mm": "ap, мм",
        "approach_angle_deg": "Угол, °",
        "brand": "Бренд",
    }
)
GROUP_FIELD_LABELS["tap"].update(
    {
        "size_label": "Размер резьбы",
        "thread_standard": "Стандарт",
        "tap_type": "Тип метчика",
    }
)
GROUP_FIELD_LABELS["center_drill"].update(
    {"diameter_mm": "Диаметр, мм", "angle_deg": "Угол, °"}
)
GROUP_FIELD_LABELS["countersink"].update(
    {
        "diameter_mm": "Диаметр, мм",
        "countersink_type": "Тип",
        "angle_deg": "Угол, °",
    }
)
GROUP_FIELD_LABELS["drill"].update({"diameter_mm": "Диаметр, мм", "angle_deg": "Угол, °"})
GROUP_FIELD_LABELS["insert"].update(
    {
        "insert_shape": "Форма",
        "cutting_edge_length_code": "Код L",
        "iso_designation": "ISO",
        "milling_family": "Семейство",
        "chipbreaker_grade": "Пластина",
    }
)
GROUP_FIELD_LABELS["collet"].update(
    {
        "collet_type": "Тип",
        "er_size": "ER",
        "clamp_range": "Диапазон",
        "inner_diameter": "Внутр. Ø",
    }
)

DEFAULT_GROUP_FIELD: dict[str, str] = {
    "end_mill": "diameter_mm",
    "body_tool": "family",
    "tap": "size_label",
    "center_drill": "diameter_mm",
    "countersink": "diameter_mm",
    "drill": "diameter_mm",
    "insert": "insert_shape",
    "collet": "collet_type",
}

# group_field → GET-параметр вкладки «Склад»
STOCK_FILTER_PARAMS: dict[str, dict[str, str]] = {
    "end_mill": {
        "diameter_mm": "diameter_mm",
        "mill_type": "mill_type",
        "flutes_count": "mill_flutes_count",
        "corner_radius_mm": "mill_corner_radius_mm",
    },
    "body_tool": {
        "diameter_mm": "bt_diameter_mm",
        "family": "body_family",
        "cutter_type": "body_cutter",
        "teeth_count": "bt_teeth_count",
        "coupling": "bt_coupling",
        "insert_family": "bt_insert_family",
        "insert_size": "bt_insert_size",
        "mount_diameter_mm": "bt_mount_diameter_mm",
        "overall_length_mm": "bt_overall_length_mm",
        "shank_type": "bt_shank_type",
        "variable_angle": "bt_variable_angle",
        "hs_body_style": "bt_hs_body_style",
        "has_purpose": "bt_has_purpose",
        "corner_radius_mm": "bt_corner_radius_mm",
        "cutting_length_mm": "bt_cutting_length_mm",
        "ap_max_mm": "bt_ap_max_mm",
        "approach_angle_deg": "bt_angle_deg",
        "brand": "bt_brand",
    },
    "tap": {
        "size_label": "tap_size",
        "thread_standard": "tap_thread_standard",
        "tap_type": "tap_tool_type",
    },
    "center_drill": {
        "diameter_mm": "center_diameter_mm",
        "angle_deg": "center_angle_deg",
    },
    "countersink": {
        "diameter_mm": "countersink_diameter_mm",
        "countersink_type": "countersink_type",
        "angle_deg": "countersink_angle_deg",
    },
    "drill": {
        "diameter_mm": "drill_diameter_mm",
        "angle_deg": "drill_angle_deg",
    },
    "insert": {
        "insert_shape": "ins_shape",
        "cutting_edge_length_code": "ins_edge_code",
        "iso_designation": "ins_iso",
        "milling_family": "ins_family",
        "chipbreaker_grade": "ins_grade",
    },
    "collet": {
        "collet_type": "collet_type",
        "er_size": "collet_er_size",
        "clamp_range": "collet_clamp_range",
        "inner_diameter": "collet_inner_diameter",
    },
}

try:
    from shifts.body_tool_constants import (
        BODY_TOOL_COUPLINGS,
        BODY_TOOL_FAMILIES,
        BODY_TOOL_SHANK_TYPES,
        HIGH_SPEED_BODY_STYLES,
        INDEXABLE_MILL_CUTTER_TYPES,
    )
    from shifts.insert_constants import MILLING_INSERT_FAMILIES
    from shifts.models import END_MILL_TYPES, COUNTERSINK_TYPES, COLLET_TYPES, THREAD_STANDARDS, TAP_TOOL_TYPES

    CHOICE_LABELS: dict[str, dict[str, str]] = {
        "mill_type": dict(END_MILL_TYPES),
        "family": dict(BODY_TOOL_FAMILIES),
        "cutter_type": dict(INDEXABLE_MILL_CUTTER_TYPES),
        "coupling": {k: lab for k, lab in BODY_TOOL_COUPLINGS if k},
        "shank_type": {k: lab for k, lab in BODY_TOOL_SHANK_TYPES if k},
        "variable_angle": {"True": "Да", "False": "Нет", "1": "Да", "0": "Нет", True: "Да", False: "Нет"},
        "has_purpose": {"True": "Есть", "False": "Нет", "1": "Есть", "0": "Нет", True: "Есть", False: "Нет"},
        "hs_body_style": {k: lab for k, lab in HIGH_SPEED_BODY_STYLES if k},
        "insert_family": {k: lab for k, lab in MILLING_INSERT_FAMILIES if k},
        "countersink_type": dict(COUNTERSINK_TYPES),
        "collet_type": dict(COLLET_TYPES),
        "thread_standard": dict(THREAD_STANDARDS),
        "tap_type": dict(TAP_TOOL_TYPES),
    }
except Exception:
    CHOICE_LABELS = {}


def category_choices() -> list[tuple[str, str]]:
    return list(ToolItem._meta.get_field("category").choices)


def group_field_choices(category: str) -> list[tuple[str, str]]:
    paths = GROUP_FIELD_PATHS.get(category, {})
    labels = GROUP_FIELD_LABELS.get(category, {})
    return [(k, labels.get(k, k)) for k in paths]


def normalize_group_field(category: str, raw: str) -> str:
    fields = GROUP_FIELD_PATHS.get(category, {})
    if raw in fields:
        return raw
    return DEFAULT_GROUP_FIELD.get(category, next(iter(fields), "diameter_mm"))


def fmt_group_value(val: Any, field_key: str = "") -> str:
    if val is None or val == "":
        return "—"
    if isinstance(val, Decimal):
        s = f"{val:.3f}".rstrip("0").rstrip(".")
        return s or "0"
    if field_key and field_key in CHOICE_LABELS:
        return CHOICE_LABELS[field_key].get(str(val), str(val))
    return str(val).strip()


def stock_filter_query(category: str, group_field: str, group_value: str) -> dict[str, str]:
    param = STOCK_FILTER_PARAMS.get(category, {}).get(group_field)
    if not param or not group_value or group_value == "—":
        return {"panel": "stock", "category": category}
    return {"panel": "stock", "category": category, param: group_value}


def _base_qs(*, include_zero: bool) -> Any:
    qs = ToolItem.objects.filter(is_deleted=False)
    if not include_zero:
        qs = qs.filter(quantity__gt=0)
    return qs


def aggregate_by_group(
    category: str,
    group_field: str,
    *,
    include_zero: bool = False,
    search: str = "",
) -> list[dict]:
    path = GROUP_FIELD_PATHS.get(category, {}).get(group_field)
    if not path:
        return []

    qs = _base_qs(include_zero=include_zero).filter(category=category)
    rows = (
        qs.values(path)
        .annotate(total_qty=Sum("quantity"), sku_count=Count("id"))
        .order_by(path)
    )

    out: list[dict] = []
    needle = (search or "").strip().casefold()
    for row in rows:
        raw = row.get(path)
        label = fmt_group_value(raw, group_field)
        if needle and needle not in label.casefold():
            continue
        out.append(
            {
                "group_value": label,
                "group_raw": raw,
                "total_qty": int(row["total_qty"] or 0),
                "sku_count": int(row["sku_count"] or 0),
                "stock_query": stock_filter_query(category, group_field, label),
                "stock_url": f"{reverse('inventory')}?{urlencode(stock_filter_query(category, group_field, label))}",
            }
        )
    return out


def group_total_qty(category: str, group_field: str, group_value: str, *, include_zero: bool = True) -> int:
    path = GROUP_FIELD_PATHS.get(category, {}).get(group_field)
    if not path or not group_value or group_value == "—":
        return 0
    qs = _base_qs(include_zero=include_zero).filter(category=category)
    parsed = _parse_group_filter_value(group_value, group_field)
    if parsed is None:
        qs = qs.filter(**{f"{path}__iexact": group_value.strip()})
    else:
        qs = qs.filter(**{path: parsed})
    return int(qs.aggregate(total=Sum("quantity"))["total"] or 0)


def _parse_group_filter_value(raw: str, field_key: str) -> Any | None:
    text = (raw or "").strip()
    if not text or text == "—":
        return None
    if field_key in ("flutes_count", "teeth_count"):
        try:
            return int(text)
        except ValueError:
            return None
    if field_key.endswith("_mm") or field_key in ("angle_deg",):
        try:
            return Decimal(text.replace(",", "."))
        except (InvalidOperation, ValueError):
            return None
    return None


def watch_status(total_qty: int, min_qty: int) -> str:
    if total_qty >= min_qty:
        return "ok"
    if total_qty <= 0:
        return "critical"
    return "warn"


def evaluate_watch_templates(templates) -> list[dict]:
    rows: list[dict] = []
    for tpl in templates:
        if not tpl.is_active:
            continue
        total = group_total_qty(tpl.category, tpl.group_field, tpl.group_value)
        status = watch_status(total, tpl.min_qty)
        rows.append(
            {
                "template": tpl,
                "total_qty": total,
                "status": status,
                "stock_query": stock_filter_query(tpl.category, tpl.group_field, tpl.group_value),
                "stock_url": f"{reverse('inventory')}?{urlencode(stock_filter_query(tpl.category, tpl.group_field, tpl.group_value))}",
                "group_label": GROUP_FIELD_LABELS.get(tpl.category, {}).get(tpl.group_field, tpl.group_field),
                "category_label": dict(category_choices()).get(tpl.category, tpl.category),
            }
        )
    return rows


def list_watch_templates(username: str) -> list[InventoryWatchTemplate]:
    return list(
        InventoryWatchTemplate.objects.filter(username=username, is_active=True).order_by("sort_order", "name", "id")
    )


def analysis_context(request, username: str) -> dict:
    category = (request.GET.get("analysis_category") or request.GET.get("category") or "end_mill").strip()
    if category not in GROUP_FIELD_PATHS:
        category = "end_mill"
    group_field = normalize_group_field(category, (request.GET.get("group_by") or "").strip())
    include_zero = (request.GET.get("show_zero") or "") == "1"
    search = (request.GET.get("analysis_search") or "").strip()

    summary_rows = aggregate_by_group(
        category,
        group_field,
        include_zero=include_zero,
        search=search,
    )
    templates = list_watch_templates(username)
    watch_rows = evaluate_watch_templates(templates)

    alerts = [r for r in watch_rows if r["status"] != "ok"]
    group_label = GROUP_FIELD_LABELS.get(category, {}).get(group_field, group_field)
    cat_label = dict(category_choices()).get(category, category)

    return {
        "analysis_category": category,
        "analysis_group_field": group_field,
        "analysis_group_label": group_label,
        "analysis_category_label": cat_label,
        "analysis_include_zero": include_zero,
        "analysis_search": search,
        "analysis_rows": summary_rows,
        "analysis_group_fields": group_field_choices(category),
        "analysis_categories": category_choices(),
        "analysis_watch_rows": watch_rows,
        "analysis_watch_alerts": alerts,
        "analysis_watch_templates": templates,
        "analysis_total_skus": sum(r["sku_count"] for r in summary_rows),
        "analysis_total_qty": sum(r["total_qty"] for r in summary_rows),
    }
