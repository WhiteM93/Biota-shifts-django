"""Данные для вкладки «Режимы резания» калькулятора (типы со склада)."""

from __future__ import annotations

from decimal import Decimal

from .models import END_MILL_TYPES, ToolItem

# Соответствие склада (tap_spec.tap_type) и типов в наладках / калькуляторе.
TAP_TYPE_TO_SETUP_TOOL: dict[str, str] = {
    "cutting": "Метчик",
    "forming": "Раскатник",
    "thread_mill": "Резьбофреза",
}

SETUP_THREAD_TOOL_TYPES = ("Метчик", "Раскатник", "Резьбофреза")

CUTTING_MODE_THREAD = "thread"
CUTTING_MODE_END_MILL = "end_mill"
CUTTING_MODE_DRILL = "drill"

SETUP_DRILL_TOOL_TYPES = ("Сверло",)

END_MILL_TYPE_LABELS: dict[str, str] = dict(END_MILL_TYPES)

MILL_OPERATION_TYPES = [
    ("rough", "Черновой"),
    ("adaptive", "Адаптив"),
    ("finish", "Чистовой"),
]

CUTTING_MODE_MATERIALS = [
    ("steel", "Сталь"),
    ("steel_hard", "Сталь зак."),
    ("alum", "Алюминий"),
    ("cast_iron", "Чугун"),
    ("brass", "Латунь"),
    ("titan", "Нерж./Титан"),
]


def _fmt_decimal(v: Decimal | None) -> str:
    if v is None:
        return ""
    s = format(v, "f").rstrip("0").rstrip(".")
    return s or "0"


def warehouse_thread_tool_types() -> list[str]:
    """Типы резьбового инструмента, которые реально есть на складе."""
    found: set[str] = set()
    qs = ToolItem.objects.filter(category="tap", is_deleted=False).select_related("tap_spec")
    for tool in qs:
        spec = getattr(tool, "tap_spec", None)
        if spec is None:
            found.add("Метчик")
            continue
        label = TAP_TYPE_TO_SETUP_TOOL.get((spec.tap_type or "").strip(), "Метчик")
        if label in SETUP_THREAD_TOOL_TYPES:
            found.add(label)
    if not found:
        return list(SETUP_THREAD_TOOL_TYPES)
    return [t for t in SETUP_THREAD_TOOL_TYPES if t in found]


def warehouse_end_mill_tool_types() -> list[str]:
    """Типы фрез со склада (по mill_type)."""
    found: set[str] = set()
    qs = ToolItem.objects.filter(category="end_mill", is_deleted=False).select_related("end_mill_spec")
    for tool in qs:
        em = getattr(tool, "end_mill_spec", None)
        if em is None:
            found.add(END_MILL_TYPE_LABELS.get("end", "Концевая фреза"))
            continue
        found.add(END_MILL_TYPE_LABELS.get((em.mill_type or "").strip(), "Концевая фреза"))
    order = [lbl for _key, lbl in END_MILL_TYPES]
    if not found:
        return order
    return [lbl for lbl in order if lbl in found]


def _drill_tool_label(diameter_mm: Decimal | None, angle_deg: Decimal | None) -> str:
    d = _fmt_decimal(diameter_mm) if diameter_mm is not None else "—"
    a = _fmt_decimal(angle_deg) if angle_deg is not None else "—"
    return f"Ø{d} / {a}°"


def warehouse_drill_tool_types() -> list[str]:
    """Типы сверл со склада (по диаметру и углу)."""
    found: list[str] = []
    seen: set[str] = set()
    qs = ToolItem.objects.filter(category="drill", is_deleted=False).select_related("drill_spec")
    for tool in qs:
        dr = getattr(tool, "drill_spec", None)
        if dr is None:
            label = SETUP_DRILL_TOOL_TYPES[0]
        else:
            label = _drill_tool_label(dr.diameter_mm, dr.angle_deg)
        if label in seen:
            continue
        seen.add(label)
        found.append(label)
    if not found:
        return list(SETUP_DRILL_TOOL_TYPES)
    return sorted(found, key=lambda s: (s == SETUP_DRILL_TOOL_TYPES[0], s))


def warehouse_drill_presets() -> dict[str, list[dict[str, str]]]:
    """Подсказки D и угла по сверлу со склада."""
    presets: dict[str, list[dict[str, str]]] = {}
    qs = ToolItem.objects.filter(category="drill", is_deleted=False).select_related("drill_spec")
    for tool in qs:
        dr = getattr(tool, "drill_spec", None)
        if dr is None:
            continue
        label = _drill_tool_label(dr.diameter_mm, dr.angle_deg)
        entry: dict[str, str] = {}
        if dr.diameter_mm is not None:
            entry["d"] = _fmt_decimal(dr.diameter_mm)
        if dr.angle_deg is not None:
            entry["angle"] = _fmt_decimal(dr.angle_deg)
        if dr.cutting_length_mm is not None:
            entry["cut_len"] = _fmt_decimal(dr.cutting_length_mm)
        if not entry:
            continue
        bucket = presets.setdefault(label, [])
        if entry not in bucket:
            bucket.append(entry)
    return presets


def warehouse_end_mill_presets() -> dict[str, list[dict[str, str]]]:
    """Подсказки D и Z по типу фрезы с склада (для автозаполнения строки)."""
    presets: dict[str, list[dict[str, str]]] = {}
    qs = ToolItem.objects.filter(category="end_mill", is_deleted=False).select_related("end_mill_spec")
    for tool in qs:
        em = getattr(tool, "end_mill_spec", None)
        if em is None:
            continue
        label = END_MILL_TYPE_LABELS.get((em.mill_type or "").strip(), "Концевая фреза")
        entry: dict[str, str] = {}
        if em.diameter_mm is not None:
            entry["d"] = _fmt_decimal(em.diameter_mm)
        if em.flutes_count is not None:
            entry["flutes"] = str(int(em.flutes_count))
        if not entry:
            continue
        bucket = presets.setdefault(label, [])
        if entry not in bucket:
            bucket.append(entry)
    return presets


def cutting_modes_payload() -> dict:
    """Конфигурация режимов резания для шаблона калькулятора."""
    thread_types = warehouse_thread_tool_types() or list(SETUP_THREAD_TOOL_TYPES)
    mill_types = warehouse_end_mill_tool_types()
    drill_types = warehouse_drill_tool_types()

    modes: list[dict] = [
        {
            "id": CUTTING_MODE_THREAD,
            "label": "Резьба",
            "hint": "Типы со склада: " + ", ".join(thread_types) + ". Колонка «Инструмент».",
            "form": CUTTING_MODE_THREAD,
            "tool_types": thread_types,
        },
        {
            "id": CUTTING_MODE_END_MILL,
            "label": "Фрезы",
            "hint": "Типы со склада: " + ", ".join(mill_types) + ". Колонка «Инструмент».",
            "form": CUTTING_MODE_END_MILL,
            "tool_types": mill_types,
            "operation_types": [{"id": oid, "label": lbl} for oid, lbl in MILL_OPERATION_TYPES],
            "tool_presets": warehouse_end_mill_presets(),
        },
        {
            "id": CUTTING_MODE_DRILL,
            "label": "Сверла",
            "hint": "Типы со склада: " + ", ".join(drill_types) + ". Колонка «Инструмент».",
            "form": CUTTING_MODE_DRILL,
            "tool_types": drill_types,
            "tool_presets": warehouse_drill_presets(),
        },
    ]
    return {
        "modes": modes,
        "materials": [{"id": mid, "label": lbl} for mid, lbl in CUTTING_MODE_MATERIALS],
    }
