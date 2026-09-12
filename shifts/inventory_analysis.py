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
    "reamer": {
        "diameter_mm": "reamer_spec__diameter_mm",
        "overall_length_mm": "reamer_spec__overall_length_mm",
        "cutting_length_mm": "reamer_spec__cutting_length_mm",
        "accuracy_class": "reamer_spec__accuracy_class",
        "flutes_count": "reamer_spec__flutes_count",
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
GROUP_FIELD_LABELS["reamer"].update(
    {
        "diameter_mm": "Диаметр, мм",
        "overall_length_mm": "L, мм",
        "cutting_length_mm": "Lc, мм",
        "accuracy_class": "Квалитет",
        "flutes_count": "Z",
    }
)
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
    "reamer": "diameter_mm",
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
    "reamer": {
        "diameter_mm": "reamer_diameter_mm",
        "overall_length_mm": "reamer_overall_length_mm",
        "cutting_length_mm": "reamer_cutting_length_mm",
        "accuracy_class": "reamer_accuracy_class",
        "flutes_count": "reamer_flutes_count",
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
    from shifts.models import END_MILL_TYPES, COUNTERSINK_TYPES, COLLET_TYPES, REAMER_ACCURACY_CLASSES, THREAD_STANDARDS, TAP_TOOL_TYPES

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
        "accuracy_class": dict(REAMER_ACCURACY_CLASSES),
    }
except Exception:
    CHOICE_LABELS = {}


def category_choices() -> list[tuple[str, str]]:
    return list(ToolItem._meta.get_field("category").choices)


def category_grouped_choices() -> list[tuple[str, str, list[tuple[str, str]]]]:
    from shifts.models import stock_category_grouped_choices

    return stock_category_grouped_choices()


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
    value = group_value
    if group_field == "size_label":
        from shifts.size_label_normalize import normalize_cutting_size_label

        value = normalize_cutting_size_label(group_value) or group_value
    return {"panel": "stock", "category": category, param: value}


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
    # size_label: М/M и запятая/точка — один размер (как в фильтрах склада)
    if group_field == "size_label":
        from shifts.size_label_normalize import size_label_match_variants

        variants = size_label_match_variants(group_value)
        if not variants:
            return 0
        q = Q()
        for variant in variants:
            q |= Q(**{f"{path}__iexact": variant})
        qs = qs.filter(q)
    else:
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
    """Контекст вкладки «Анализ»: панель руководителя склада."""
    from django.db.models import F, IntegerField, Sum, Value
    from django.db.models.functions import Coalesce

    from shifts.models import StockMovement, VisualContainer

    base_tools = ToolItem.objects.filter(is_deleted=False)
    nomenclature = base_tools.count()
    total_qty = int(base_tools.aggregate(t=Coalesce(Sum("quantity"), Value(0)))["t"] or 0)

    templates = list_watch_templates(username)
    watch_rows = evaluate_watch_templates(templates)
    alerts = [r for r in watch_rows if r["status"] != "ok"]
    if templates:
        below_min = len(alerts)
    else:
        below_min = base_tools.filter(quantity__lte=0).count()

    issued_qty = int(
        StockMovement.objects.filter(movement_type="issue", is_reverted=False)
        .annotate(
            processed_qty=Coalesce(
                Sum("issue_outcomes__quantity"),
                Value(0, output_field=IntegerField()),
            )
        )
        .annotate(remaining_qty=F("quantity") - F("processed_qty"))
        .filter(remaining_qty__gt=0)
        .aggregate(t=Coalesce(Sum("remaining_qty"), Value(0)))["t"]
        or 0
    )

    writeoff_count = StockMovement.objects.filter(movement_type="writeoff", is_reverted=False).count()

    storage_cells = VisualContainer.objects.filter(parent__isnull=True).count()
    if storage_cells <= 0:
        storage_cells = (
            base_tools.exclude(warehouse_address="")
            .exclude(warehouse_address__isnull=True)
            .values("warehouse_address")
            .distinct()
            .count()
        )

    cat_labels = dict(category_choices())
    by_cat_raw = list(
        base_tools.values("category")
        .annotate(total_qty=Coalesce(Sum("quantity"), Value(0)), sku_count=Count("id"))
        .order_by("-total_qty", "category")
    )
    by_category = [
        {
            "category": row["category"],
            "label": cat_labels.get(row["category"], row["category"]),
            "total_qty": int(row["total_qty"] or 0),
            "sku_count": int(row["sku_count"] or 0),
        }
        for row in by_cat_raw
    ]

    top_items = list(
        base_tools.filter(quantity__gt=0)
        .order_by("-quantity", "name")
        .values("id", "name", "quantity", "category")[:12]
    )
    nomenclature_bars = [
        {
            "id": row["id"],
            "name": (row["name"] or "—")[:48],
            "quantity": int(row["quantity"] or 0),
            "category": row["category"],
        }
        for row in top_items
    ]

    # Сохраняем старые ключи сводки (пустые), чтобы старые шаблоны/ссылки не падали
    category = (request.GET.get("analysis_category") or request.GET.get("category") or "end_mill").strip()
    if category not in GROUP_FIELD_PATHS:
        category = "end_mill"
    group_field = normalize_group_field(category, (request.GET.get("group_by") or "").strip())

    kpi_rows = [
        {"label": "Номенклатура", "value": nomenclature},
        {"label": "Позиций ниже минимума", "value": below_min},
        {"label": "Общее количество на складе", "value": total_qty},
        {"label": "Инструмента выдано сейчас", "value": issued_qty},
        {"label": "Количество списаний", "value": writeoff_count},
        {"label": "Ячеек хранения", "value": storage_cells},
    ]

    # Круговая диаграмма: только неотрицательные доли (отрицательные остатки — в таблице)
    pie_cats = [r for r in by_category if r["total_qty"] > 0]
    if not pie_cats and by_category:
        pie_cats = [{"label": r["label"], "total_qty": 0} for r in by_category[:1]]

    chart_payload = {
        "nomenclature": {
            "labels": [r["name"] for r in nomenclature_bars],
            "values": [r["quantity"] for r in nomenclature_bars],
        },
        "categories": {
            "labels": [r["label"] for r in pie_cats],
            "values": [r["total_qty"] for r in pie_cats],
        },
    }

    return {
        "analysis_dashboard": True,
        "dash_kpi_rows": kpi_rows,
        "dash_by_category": by_category,
        "dash_nomenclature_bars": nomenclature_bars,
        "dash_chart_data": chart_payload,
        "dash_nomenclature": nomenclature,
        "dash_below_min": below_min,
        "dash_total_qty": total_qty,
        "dash_issued_qty": issued_qty,
        "dash_writeoff_count": writeoff_count,
        "dash_storage_cells": storage_cells,
        "analysis_watch_alerts": alerts,
        "analysis_watch_rows": watch_rows,
        "analysis_watch_templates": templates,
        # legacy keys (фильтры сводки больше не в UI)
        "analysis_category": category,
        "analysis_group_field": group_field,
        "analysis_group_label": GROUP_FIELD_LABELS.get(category, {}).get(group_field, group_field),
        "analysis_category_label": cat_labels.get(category, category),
        "analysis_include_zero": False,
        "analysis_search": "",
        "analysis_rows": [],
        "analysis_group_fields": group_field_choices(category),
        "analysis_categories": category_choices(),
        "stock_category_groups": category_grouped_choices(),
        "analysis_total_skus": nomenclature,
        "analysis_total_qty": total_qty,
    }
