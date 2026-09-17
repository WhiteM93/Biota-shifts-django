"""Хвостовики свёрл."""

from __future__ import annotations

DRILL_SHANK_TYPES = [
    ("morse_1", "Конус Морзе 1"),
    ("morse_2", "Конус Морзе 2"),
    ("morse_3", "Конус Морзе 3"),
    ("morse_4", "Конус Морзе 4"),
    ("morse_5", "Конус Морзе 5"),
    ("morse_6", "Конус Морзе 6"),
    ("cylindrical_same", "Цилиндрический (как основной)"),
    ("cylindrical_other", "Цилиндрический (другой)"),
    ("weldon", "Weldon"),
]

DRILL_SHANK_VALUES = frozenset(k for k, _ in DRILL_SHANK_TYPES)
DRILL_SHANK_LABELS = dict(DRILL_SHANK_TYPES)

DRILL_SHANK_NEEDS_MAIN_DIAMETER = frozenset({"cylindrical_other", "weldon"})
DRILL_SHANK_COPIES_CUTTING = frozenset({"cylindrical_same"})


def normalize_drill_shank(raw) -> str:
    v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "mk1": "morse_1",
        "mk2": "morse_2",
        "mk3": "morse_3",
        "mk4": "morse_4",
        "mk5": "morse_5",
        "mk6": "morse_6",
        "mt1": "morse_1",
        "mt2": "morse_2",
        "mt3": "morse_3",
        "mt4": "morse_4",
        "mt5": "morse_5",
        "mt6": "morse_6",
        "morse1": "morse_1",
        "morse2": "morse_2",
        "morse3": "morse_3",
        "morse4": "morse_4",
        "morse5": "morse_5",
        "morse6": "morse_6",
        "конус_морзе_1": "morse_1",
        "конус_морзе_2": "morse_2",
        "конус_морзе_3": "morse_3",
        "конус_морзе_4": "morse_4",
        "конус_морзе_5": "morse_5",
        "конус_морзе_6": "morse_6",
        "морзе_1": "morse_1",
        "морзе_2": "morse_2",
        "морзе_3": "morse_3",
        "морзе_4": "morse_4",
        "морзе_5": "morse_5",
        "морзе_6": "morse_6",
        "cylindrical": "cylindrical_same",
        "cyl": "cylindrical_same",
        "цилиндр": "cylindrical_same",
        "цилиндрический": "cylindrical_same",
        "цилиндрический_как_основной": "cylindrical_same",
        "цилиндрический_другой": "cylindrical_other",
        "cyl_other": "cylindrical_other",
        "cylindrical_diff": "cylindrical_other",
        "wel": "weldon",
        "weld": "weldon",
    }
    v = aliases.get(v, v)
    if v in DRILL_SHANK_VALUES:
        return v
    return ""


def drill_shank_needs_main_diameter(shank_type: str) -> bool:
    return normalize_drill_shank(shank_type) in DRILL_SHANK_NEEDS_MAIN_DIAMETER


def drill_shank_copies_cutting_diameter(shank_type: str) -> bool:
    return normalize_drill_shank(shank_type) in DRILL_SHANK_COPIES_CUTTING
