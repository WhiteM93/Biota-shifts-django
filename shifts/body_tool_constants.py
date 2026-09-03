"""Корпусной инструмент — пока только фрезы со сменными пластинами.

Типы фрез с СМП — по каталогу CNC Magazine:
https://cncmagazine.ru/frezy-po-metallu/frezy-so-smennymi-plastinami/
"""

from __future__ import annotations

from decimal import Decimal

# Единственная позиция корпусного инструмента на этом этапе.
BODY_TOOL_FAMILIES = [
    ("indexable_mill", "Фрезы со сменными пластинами"),
]

BODY_TOOL_FAMILY_VALUES = frozenset(k for k, _ in BODY_TOOL_FAMILIES)
BODY_TOOL_FAMILY_LABELS = dict(BODY_TOOL_FAMILIES)

# Типы внутри «Фрезы со сменными пластинами»
INDEXABLE_MILL_CUTTER_TYPES = [
    ("face", "Торцевые насадные фрезы"),
    ("end", "Концевые насадные фрезы"),
    ("chamfer", "Фасочные фрезы"),
    ("high_speed", "Высокоскоростные фрезы"),
    ("round_insert", "Фрезы с круглыми пластинами"),
    ("disc", "Дисковые фрезы"),
    ("ball", "Сферические фрезы"),
    ("modular_head", "Фрезерные головки с пластинами"),
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

# Типичные углы подхода торцевых / концевых насадных фрез
FACE_MILL_ANGLES = [
    ("45", "45°"),
    ("60", "60°"),
    ("75", "75°"),
    ("90", "90°"),
]

BODY_TOOL_SHANK_TYPES = [
    ("", "—"),
    ("mt3", "МТ3"),
    ("mt4", "МТ4"),
    ("weldon", "Weldon"),
    ("bore", "Отверстие (насадная)"),
    ("cylindrical", "Цилиндрический"),
]

BODY_TOOL_SHANK_VALUES = frozenset(k for k, _ in BODY_TOOL_SHANK_TYPES if k)
BODY_TOOL_SHANK_LABELS = {k: lab for k, lab in BODY_TOOL_SHANK_TYPES if k}

# Для концевых — без насадного отверстия и Морзе; для фасочных — все;
# для высокоскоростных — отверстие или цилиндр;
# для сферических — Морзе / Weldon / цилиндр.
END_MILL_SHANK_TYPES = [x for x in BODY_TOOL_SHANK_TYPES if x[0] in ("", "weldon", "cylindrical")]
CHAMFER_MILL_SHANK_TYPES = list(BODY_TOOL_SHANK_TYPES)
HIGH_SPEED_SHANK_TYPES = [x for x in BODY_TOOL_SHANK_TYPES if x[0] in ("", "bore", "cylindrical")]
ROUND_INSERT_SHANK_TYPES = list(BODY_TOOL_SHANK_TYPES)
BALL_MILL_SHANK_TYPES = [
    x for x in BODY_TOOL_SHANK_TYPES if x[0] in ("", "mt3", "mt4", "weldon", "cylindrical")
]

# Резьба крепления фрезерных головок с пластинами
MODULAR_HEAD_THREADS = [
    ("", "—"),
    ("M6", "М6"),
    ("M8", "М8"),
    ("M10", "М10"),
    ("M12", "М12"),
    ("M16", "М16"),
    ("M20", "М20"),
]
MODULAR_HEAD_THREAD_VALUES = frozenset(k for k, _ in MODULAR_HEAD_THREADS if k)
MODULAR_HEAD_THREAD_LABELS = {k: lab for k, lab in MODULAR_HEAD_THREADS if k}

# Тип корпуса: насадная / концевая (высокоскоростные, с круглыми пластинами и т.п.)
HIGH_SPEED_BODY_STYLES = [
    ("", "—"),
    ("shell", "Насадная"),
    ("end", "Концевая"),
]
INDEXABLE_BODY_STYLES = HIGH_SPEED_BODY_STYLES
HIGH_SPEED_BODY_STYLE_VALUES = frozenset(k for k, _ in HIGH_SPEED_BODY_STYLES if k)
HIGH_SPEED_BODY_STYLE_LABELS = {k: lab for k, lab in HIGH_SPEED_BODY_STYLES if k}

# Угол: фиксированный (из FACE_MILL_ANGLES) или переменный
ANGLE_MODE_VARIABLE = "variable"
HIGH_SPEED_ANGLE_OPTIONS = [("", "—")] + list(FACE_MILL_ANGLES) + [(ANGLE_MODE_VARIABLE, "Переменный")]

INSERT_SIZE_OTHER = "OTHER"

BODY_TOOL_COOLANT_CHOICES = [
    (False, "Нет"),
    (True, "Есть"),
]


def normalize_insert_size(raw) -> str:
    v = str(raw or "").strip().upper().replace(" ", "")
    if not v or v == INSERT_SIZE_OTHER:
        return ""
    return v[:24]


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
        "koncevye_nasadnye": "end",
        "end_shell": "end",
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


def normalize_body_tool_shank(raw) -> str:
    v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "wel": "weldon",
        "weld": "weldon",
        "weldon_shank": "weldon",
        "cyl": "cylindrical",
        "cylinder": "cylindrical",
        "cylindrical_shank": "cylindrical",
        "cilindricheskiy": "cylindrical",
        "цилиндр": "cylindrical",
        "цилиндрический": "cylindrical",
        "bore_mount": "bore",
        "shell": "bore",
        "nasadnaya": "bore",
        "otverstie": "bore",
        "отверстие": "bore",
        "насадная": "bore",
        "mt_3": "mt3",
        "morse3": "mt3",
        "morse_3": "mt3",
        "морзе3": "mt3",
        "морзе_3": "mt3",
        "мт3": "mt3",
        "mt_4": "mt4",
        "morse4": "mt4",
        "morse_4": "mt4",
        "морзе4": "mt4",
        "морзе_4": "mt4",
        "мт4": "mt4",
    }
    v = aliases.get(v, v)
    if v in BODY_TOOL_SHANK_VALUES:
        return v
    return ""


def coupling_from_shank(shank_type: str) -> str:
    """Сопоставить тип хвостовика/посадки с полем крепления корпуса."""
    st = normalize_body_tool_shank(shank_type)
    if st == "bore":
        return "bore"
    if st in ("weldon", "cylindrical", "mt3", "mt4"):
        return "shank"
    return ""


def normalize_high_speed_body_style(raw) -> str:
    v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "nasadnaya": "shell",
        "shell_mill": "shell",
        "bore": "shell",
        "насадная": "shell",
        "koncevaya": "end",
        "end_mill": "end",
        "концевая": "end",
    }
    v = aliases.get(v, v)
    if v in HIGH_SPEED_BODY_STYLE_VALUES:
        return v
    return ""


def normalize_modular_head_thread(raw) -> str:
    v = str(raw or "").strip().upper().replace(" ", "").replace("М", "M")
    if v.startswith("M") and v[1:].isdigit():
        v = f"M{v[1:]}"
    aliases = {
        "6": "M6",
        "8": "M8",
        "10": "M10",
        "12": "M12",
        "16": "M16",
        "20": "M20",
    }
    v = aliases.get(v, v)
    if v in MODULAR_HEAD_THREAD_VALUES:
        return v
    return ""


def parse_angle_or_variable(raw) -> tuple:
    """
    Вернуть (approach_angle_deg_str_or_none, variable_angle_bool).
    raw: '', '45', 'variable', …
    """
    v = str(raw or "").strip().lower()
    if not v:
        return None, False
    if v in (ANGLE_MODE_VARIABLE, "var", "переменный"):
        return None, True
    return v, False


def build_body_tool_display_name(
    *,
    family: str = "indexable_mill",
    cutter_type: str = "face",
    diameter_mm=None,
    teeth_count=None,
    insert_family: str = "",
    insert_size: str = "",
    brand: str = "",
) -> str:
    fam = BODY_TOOL_FAMILY_LABELS.get(normalize_body_tool_family(family), "Фрезы со сменными пластинами")
    cut = INDEXABLE_MILL_CUTTER_LABELS.get(
        normalize_indexable_mill_cutter(cutter_type), cutter_type
    )
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
    sz = normalize_insert_size(insert_size)
    if ins and sz:
        parts.append(f"{ins} {sz}")
    elif ins:
        parts.append(ins)
    elif sz:
        parts.append(sz)
    br = (brand or "").strip()
    if br:
        parts.append(br)
    return " · ".join(parts)[:180]
