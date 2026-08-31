"""Корпусной инструмент (сборный) — семьи и типы фрез со сменными пластинами.

Подтипы фрез с СМП — по каталогу CNC Magazine:
https://cncmagazine.ru/frezy-po-metallu/frezy-so-smennymi-plastinami/
"""

from __future__ import annotations

from decimal import Decimal

BODY_TOOL_FAMILIES = [
    ("indexable_mill", "Фрезы со сменными пластинами"),
]

BODY_TOOL_FAMILY_VALUES = frozenset(k for k, _ in BODY_TOOL_FAMILIES)
BODY_TOOL_FAMILY_LABELS = dict(BODY_TOOL_FAMILIES)

# Типы корпусных фрез со сменными пластинами (как на CNC Magazine)
INDEXABLE_MILL_CUTTER_TYPES = [
    ("face", "Торцевые насадные"),
    ("end", "Концевые"),
    ("chamfer", "Фасочные"),
    ("high_speed", "Высокоскоростные"),
    ("round_insert", "С круглыми пластинами"),
    ("disc", "Дисковые"),
    ("ball", "Сферические"),
    ("modular_head", "Фрезерные головки"),
]

INDEXABLE_MILL_CUTTER_VALUES = frozenset(k for k, _ in INDEXABLE_MILL_CUTTER_TYPES)
INDEXABLE_MILL_CUTTER_LABELS = dict(INDEXABLE_MILL_CUTTER_TYPES)

# Крепление корпуса
BODY_TOOL_COUPLINGS = [
    ("", "—"),
    ("bore", "Насадные (отверстие)"),
    ("shank", "Хвостовик"),
    ("modular", "Модульная головка"),
]

BODY_TOOL_COUPLING_VALUES = frozenset(k for k, _ in BODY_TOOL_COUPLINGS if k)
BODY_TOOL_COUPLING_LABELS = {k: lab for k, lab in BODY_TOOL_COUPLINGS if k}


def normalize_body_tool_family(raw) -> str:
    v = str(raw or "").strip().lower()
    if v in BODY_TOOL_FAMILY_VALUES:
        return v
    return "indexable_mill"


def normalize_indexable_mill_cutter(raw) -> str:
    v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "face_shell": "face",
        "torcevye": "face",
        "koncevye": "end",
        "fasochnye": "chamfer",
        "vysokoskorostnye": "high_speed",
        "hs": "high_speed",
        "round": "round_insert",
        "kruglye": "round_insert",
        "diskovye": "disc",
        "sfericheskie": "ball",
        "spherical": "ball",
        "golovki": "modular_head",
        "head": "modular_head",
    }
    v = aliases.get(v, v)
    if v in INDEXABLE_MILL_CUTTER_VALUES:
        return v
    return "face"


def normalize_body_tool_coupling(raw) -> str:
    v = str(raw or "").strip().lower()
    if v in BODY_TOOL_COUPLING_VALUES:
        return v
    return ""


def build_body_tool_display_name(
    *,
    family: str = "indexable_mill",
    cutter_type: str = "face",
    diameter_mm=None,
    teeth_count=None,
    insert_family: str = "",
) -> str:
    fam = BODY_TOOL_FAMILY_LABELS.get(normalize_body_tool_family(family), "Корпус")
    cut = INDEXABLE_MILL_CUTTER_LABELS.get(normalize_indexable_mill_cutter(cutter_type), cutter_type)
    parts = [fam, cut]
    if diameter_mm is not None and str(diameter_mm) != "":
        try:
            d = Decimal(str(diameter_mm))
            ds = format(d, "f").rstrip("0").rstrip(".")
        except Exception:
            ds = str(diameter_mm)
        parts.append(f"Ø{ds}")
    if teeth_count is not None and str(teeth_count).strip() != "":
        parts.append(f"Z{teeth_count}")
    ins = (insert_family or "").strip().upper()
    if ins:
        parts.append(ins)
    return " · ".join(parts)[:180]
