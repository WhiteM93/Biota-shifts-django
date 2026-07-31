"""Данные для вкладки «Режимы резания» калькулятора (типы со склада)."""

from __future__ import annotations

import math
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
    ("helical_rad", "Винт. радиальное"),
    ("helical_ax", "Винт. осевое"),
    ("spiral", "Спираль"),
    ("adaptive", "Адаптив"),
    ("finish", "Чистовой"),
]

CUTTING_MODE_MATERIALS = [
    ("d16", "Д16"),
    ("ls59", "ЛС59"),
    ("amg6", "Амг6"),
    ("st30", "Ст30"),
    ("st45", "Ст45"),
    ("x18h9t", "12Х18Н9Т"),
]

# Базовый каталог Ø концевых фрез для режимов резания.
END_MILL_BASELINE_DIAMETERS: tuple[float, ...] = (
    16,
    12,
    10,
    8,
    6,
    4,
    3,
    2.5,
    2,
    1.5,
    1,
)

# Vc (м/мин) и fz (мм/зуб) — ориентиры для твердосплавных концевых фрез по маркам.
# r=черновой, f=чистовой, a=адаптив, hr=винт.радиальное, ha=винт.осевое, s=спираль.
_MAT_CUT_PARAMS: dict[str, dict[str, float]] = {
    # Д16 — дюраль, хорошо обрабатывается
    "d16": {
        "vc_r": 280, "vc_f": 380, "vc_a": 320, "vc_hr": 270, "vc_ha": 240, "vc_s": 300,
        "fz_r": 0.11, "fz_f": 0.045, "fz_a": 0.085, "fz_hr": 0.085, "fz_ha": 0.055, "fz_s": 0.09,
    },
    # ЛС59 — латунь свинцовистая
    "ls59": {
        "vc_r": 180, "vc_f": 220, "vc_a": 200, "vc_hr": 170, "vc_ha": 150, "vc_s": 190,
        "fz_r": 0.08, "fz_f": 0.04, "fz_a": 0.06, "fz_hr": 0.06, "fz_ha": 0.045, "fz_s": 0.065,
    },
    # Амг6 — Al-Mg, вязкая, чуть ниже Д16
    "amg6": {
        "vc_r": 220, "vc_f": 300, "vc_a": 250, "vc_hr": 210, "vc_ha": 190, "vc_s": 235,
        "fz_r": 0.09, "fz_f": 0.04, "fz_a": 0.07, "fz_hr": 0.07, "fz_ha": 0.05, "fz_s": 0.075,
    },
    # Ст30 — конструкционная сталь
    "st30": {
        "vc_r": 110, "vc_f": 140, "vc_a": 120, "vc_hr": 105, "vc_ha": 95, "vc_s": 115,
        "fz_r": 0.06, "fz_f": 0.03, "fz_a": 0.045, "fz_hr": 0.045, "fz_ha": 0.032, "fz_s": 0.05,
    },
    # Ст45 — выше прочность, режимы чуть ниже Ст30
    "st45": {
        "vc_r": 95, "vc_f": 125, "vc_a": 105, "vc_hr": 90, "vc_ha": 80, "vc_s": 100,
        "fz_r": 0.05, "fz_f": 0.025, "fz_a": 0.038, "fz_hr": 0.038, "fz_ha": 0.028, "fz_s": 0.042,
    },
    # 12Х18Н9Т — нержавеющая аустенитная
    "x18h9t": {
        "vc_r": 50, "vc_f": 70, "vc_a": 55, "vc_hr": 48, "vc_ha": 42, "vc_s": 52,
        "fz_r": 0.03, "fz_f": 0.014, "fz_a": 0.022, "fz_hr": 0.02, "fz_ha": 0.014, "fz_s": 0.024,
    },
}


def _fmt_decimal(v: Decimal | None) -> str:
    if v is None:
        return ""
    s = format(v, "f").rstrip("0").rstrip(".")
    return s or "0"


def _fmt_num(v: float | int, digits: int = 2) -> str:
    n = float(v)
    s = f"{n:.{digits}f}".rstrip("0").rstrip(".")
    return s or "0"


def _diameter_key(d: float) -> str:
    if abs(d - round(d)) < 1e-9:
        return str(int(round(d)))
    return _fmt_num(d, 2)


def _flutes_for_diameter(d: float) -> int:
    if d >= 8:
        return 4
    if d >= 3:
        return 3
    return 2


def _spindle_n(vc: float, d: float) -> int:
    """Обороты по Vc, с округлением и потолком под типичный шпиндель."""
    if d <= 0:
        return 0
    raw = (1000.0 * vc) / (math.pi * d)
    step = 100 if raw >= 5000 else 50
    n = int(round(raw / step) * step)
    if d < 2:
        cap = 24000
    elif d < 4:
        cap = 18000
    elif d < 8:
        cap = 14000
    else:
        cap = 10000
    return max(800, min(n, cap))


def _mill_op_geometry(d: float, op: str) -> tuple[float, float, float]:
    """ae, ap, припуск (мм) для операции.

    Винтовое (как в NX): два варианта —
      helical_rad — радиальное: ae радиальная глубина, ap малый шаг по Z;
      helical_ax  — осевое: ae радиальное врезание в отверстии, ap шаг винта/оборот.
    Спираль: ae — stepover, ap — глубина слоя.
    """
    if op == "rough":
        ae = 0.4 * d
        ap = 0.7 * d
        allowance = 0.3 if d >= 6 else (0.2 if d >= 2.5 else 0.1)
    elif op == "finish":
        ae = min(0.5, max(0.05, 0.05 * d))
        ap = d
        allowance = 0.0
    elif op in ("helical_rad", "helical"):
        # Радиальное винтовое (NX helical / radial emphasis): снятие по ae, осторожный спуск.
        ae = 0.35 * d
        ap = 0.05 * d if d >= 3 else max(0.04, 0.06 * d)
        allowance = 0.2 if d >= 4 else 0.1
    elif op == "helical_ax":
        # Осевое винтовое (открытие отверстия / helical pitch): шаг по оси, умеренное ae.
        ae = 0.1 * d
        ap = 0.12 * d if d >= 3 else max(0.05, 0.1 * d)
        allowance = 0.2 if d >= 4 else 0.1
    elif op == "spiral":
        ae = 0.3 * d
        ap = 0.55 * d
        allowance = 0.2 if d >= 4 else 0.1
    else:  # adaptive
        ae = 0.08 * d
        ap = min(1.5 * d, 12.0)
        allowance = 0.2 if d >= 4 else 0.1
    return ae, ap, allowance


def _baseline_entry(d: float, op: str, vc: float, fz: float) -> dict[str, str]:
    z = _flutes_for_diameter(d)
    n = _spindle_n(vc, d)
    feed = max(1, int(round(n * z * fz)))
    ae, ap, allowance = _mill_op_geometry(d, op)
    return {
        "flutes": str(z),
        "n": str(n),
        "feed": str(feed),
        "ae": _fmt_num(ae, 2),
        "ap": _fmt_num(ap, 2),
        "allowance": _fmt_num(allowance, 2),
        "vc": str(int(round(vc))),
        "fz": _fmt_num(fz, 3),
    }


def _op_cut_keys(op: str) -> tuple[str, str]:
    if op == "finish":
        return "vc_f", "fz_f"
    if op == "adaptive":
        return "vc_a", "fz_a"
    if op in ("helical_rad", "helical"):
        return "vc_hr", "fz_hr"
    if op == "helical_ax":
        return "vc_ha", "fz_ha"
    if op == "spiral":
        return "vc_s", "fz_s"
    return "vc_r", "fz_r"


def build_end_mill_baselines() -> dict[str, dict[str, dict[str, dict[str, str]]]]:
    """
    Материал → Ø → операция → параметры (n, F, ae, ap, припуск, Z, Vc, fz).
    Базовые ориентиры для концевых фрез; правьте под свой инструмент/СОЖ.
    """
    out: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    op_ids = [oid for oid, _lbl in MILL_OPERATION_TYPES]
    for mat_id, p in _MAT_CUT_PARAMS.items():
        by_d: dict[str, dict[str, dict[str, str]]] = {}
        for d in END_MILL_BASELINE_DIAMETERS:
            key = _diameter_key(d)
            ops: dict[str, dict[str, str]] = {}
            for op in op_ids:
                vc_key, fz_key = _op_cut_keys(op)
                ops[op] = _baseline_entry(d, op, p[vc_key], p[fz_key])
            # Совместимость со старыми строками «helical».
            ops["helical"] = ops["helical_rad"]
            by_d[key] = ops
        out[mat_id] = by_d
    return out


END_MILL_BASELINES = build_end_mill_baselines()


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
    diameters = [_diameter_key(d) for d in END_MILL_BASELINE_DIAMETERS]

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
            "hint": (
                "Базовые режимы для Ø"
                + ", ".join(diameters)
                + ". Винтовое как в NX: радиальное (ae) и осевое (ap = шаг винта). "
                "Спираль: ae = stepover."
            ),
            "form": CUTTING_MODE_END_MILL,
            "tool_types": mill_types,
            "operation_types": [{"id": oid, "label": lbl} for oid, lbl in MILL_OPERATION_TYPES],
            "tool_presets": warehouse_end_mill_presets(),
            "diameters": diameters,
            "baselines": END_MILL_BASELINES,
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
