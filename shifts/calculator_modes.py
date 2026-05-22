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
    ]
    return {
        "modes": modes,
        "materials": [{"id": mid, "label": lbl} for mid, lbl in CUTTING_MODE_MATERIALS],
    }
