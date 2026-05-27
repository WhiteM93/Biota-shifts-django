"""Справочники цангов для склада и прихода."""
from __future__ import annotations

COLLET_TYPES = [
    ("er", "ER"),
    ("er_g", "ER G"),
    ("ers", "ERS"),
    ("eoc", "EOC"),
    ("sc", "SC"),
    ("sk", "SK"),
    ("threading", "Резьбонарезная"),
    ("cc", "CC"),
    ("dc", "DC"),
    ("phc_hc", "PHC/HC"),
    ("ter", "TER"),
]

COLLET_TYPE_VALUES = frozenset(k for k, _ in COLLET_TYPES)

COLLET_TYPE_TOOLTIPS = {
    "er": "Стандартные цанги ISO (ER08…ER50), диапазон зажима Ø, опция AA — высокоточная.",
    "er_g": "Цанга ER G: размер гнезда ER (ER16, ER32…) и внутренний диаметр зажима, мм.",
    "ers": "Герметичные цанги ERS.",
    "eoc": "Цанги EOC.",
    "sc": "Цанги SC.",
    "sk": "Цанги SK.",
    "threading": "Резьбонарезная цанга: серия (TC820, GT12…), назначение (метчики / плашки), стандарт DIN/ISO/JIS.",
    "cc": "Цанги CC.",
    "dc": "Цанги DC.",
    "phc_hc": "Цанги PHC/HC.",
    "ter": "Цанги TER.",
}

ER_COLLET_SIZES = [
    ("ER08", "ER08"),
    ("ER11", "ER11"),
    ("ER16", "ER16"),
    ("ER20", "ER20"),
    ("ER25", "ER25"),
    ("ER32", "ER32"),
    ("ER40", "ER40"),
    ("ER50", "ER50"),
]

ER_COLLET_SIZE_VALUES = frozenset(k for k, _ in ER_COLLET_SIZES)

# Типовые диапазоны зажима для ER-цанг (мм)
ER_CLAMP_RANGES = tuple(
    (f"{lo}-{hi}", f"{lo}–{hi} мм") for lo, hi in zip(range(1, 26), range(2, 27))
)

ER_CLAMP_RANGE_VALUES = frozenset(k for k, _ in ER_CLAMP_RANGES)

# Внутренний диаметр для цанг ER G (мм)
COLLET_ER_G_INNER_DIAMETERS = [
    ("2.8", "2,8"),
    ("3", "3"),
    ("3.15", "3,15"),
    ("3.5", "3,5"),
    ("3.55", "3,55"),
    ("4", "4"),
    ("4.5", "4,5"),
    ("5", "5"),
    ("5.5", "5,5"),
    ("6", "6"),
    ("6.2", "6,2"),
    ("6.3", "6,3"),
    ("7", "7"),
    ("8", "8"),
    ("8.5", "8,5"),
    ("9", "9"),
    ("10", "10"),
    ("10.5", "10,5"),
    ("11", "11"),
    ("11.2", "11,2"),
    ("12", "12"),
    ("12.5", "12,5"),
    ("13", "13"),
    ("14", "14"),
    ("15", "15"),
    ("16", "16"),
    ("17", "17"),
    ("18", "18"),
    ("19", "19"),
    ("20", "20"),
    ("2-13", "2–13"),
    ("2-16", "2–16"),
    ("3-10", "3–10"),
    ("3-20", "3–20"),
]

COLLET_ER_G_INNER_DIAMETER_VALUES = frozenset(k for k, _ in COLLET_ER_G_INNER_DIAMETERS)

# Устаревшие ключи квадрата → внутренний Ø (для старых записей)
_ER_G_SQUARE_TO_INNER = {
    "2.8x2.8": "2.8",
    "3x3": "3",
    "3.15x3.15": "3.15",
    "3.5x3.5": "3.5",
    "3.55x3.55": "3.55",
    "4x4": "4",
    "4.5x4.5": "4.5",
    "5x5": "5",
    "5.5x5.5": "5.5",
    "6x6": "6",
    "6.2x6.2": "6.2",
    "6.3x6.3": "6.3",
    "7x7": "7",
    "8x8": "8",
    "9x9": "9",
    "10x10": "10",
    "11x11": "11",
    "11.2x11.2": "11.2",
    "12x12": "12",
    "12.5x12.5": "12.5",
    "13x13": "13",
    "15x15": "15",
    "17x17": "17",
}

COLLET_THREAD_STANDARDS = [
    ("din371", "DIN 371"),
    ("din376", "DIN 376"),
    ("iso", "ISO"),
    ("jis", "JIS"),
    ("ns", "NS"),
    ("fes", "FES"),
]

COLLET_THREAD_STANDARD_VALUES = frozenset(k for k, _ in COLLET_THREAD_STANDARDS)

# Серии резьбонарезных цанг
COLLET_THREADING_SERIES = [
    ("tc820", "TC820"),
    ("gt12", "GT12"),
    ("gt24", "GT24"),
    ("gt42", "GT42"),
    ("gt12_die", "GT12 под плашки"),
    ("tc820_die", "TC820 под плашки"),
]

COLLET_THREADING_SERIES_VALUES = frozenset(k for k, _ in COLLET_THREADING_SERIES)

COLLET_THREADING_USE = [
    ("tap", "Для метчиков"),
    ("die", "Для плашек"),
]

COLLET_THREADING_USE_VALUES = frozenset(k for k, _ in COLLET_THREADING_USE)

_COLLET_TYPE_LABELS = dict(COLLET_TYPES)
_ER_SIZE_LABELS = dict(ER_COLLET_SIZES)
_ER_G_INNER_LABELS = dict(COLLET_ER_G_INNER_DIAMETERS)
_THREAD_STD_LABELS = dict(COLLET_THREAD_STANDARDS)
_THREADING_SERIES_LABELS = dict(COLLET_THREADING_SERIES)
_THREADING_USE_LABELS = dict(COLLET_THREADING_USE)


def normalize_collet_type(raw) -> str:
    v = (raw or "").strip().lower()
    return v if v in COLLET_TYPE_VALUES else ""


def normalize_er_collet_size(raw) -> str:
    v = (raw or "").strip().upper().replace(" ", "")
    return v if v in ER_COLLET_SIZE_VALUES else ""


def normalize_er_clamp_range(raw) -> str:
    v = (raw or "").strip().replace("–", "-").replace(" ", "")
    return v if v in ER_CLAMP_RANGE_VALUES else ""


def normalize_collet_er_g_inner_diameter(raw) -> str:
    v = (raw or "").strip().lower().replace(",", ".").replace("×", "x").replace(" ", "")
    v = v.replace("–", "-")
    if v in _ER_G_SQUARE_TO_INNER:
        v = _ER_G_SQUARE_TO_INNER[v]
    return v if v in COLLET_ER_G_INNER_DIAMETER_VALUES else ""


def normalize_collet_square_size(raw) -> str:
    """Устаревшее поле; для ER G используйте inner_diameter."""
    return normalize_collet_er_g_inner_diameter(raw)


def normalize_collet_thread_standard(raw) -> str:
    v = (raw or "").strip().lower()
    if v == "iso529":
        return "iso"
    return v if v in COLLET_THREAD_STANDARD_VALUES else ""


def normalize_collet_threading_series(raw) -> str:
    v = (raw or "").strip().lower().replace(" ", "_")
    aliases = {
        "gt12_под_плашки": "gt12_die",
        "tc820_под_плашки": "tc820_die",
    }
    v = aliases.get(v, v)
    return v if v in COLLET_THREADING_SERIES_VALUES else ""


def normalize_collet_threading_use(raw) -> str:
    v = (raw or "").strip().lower()
    if v in ("метчики", "метчик", "tap"):
        return "tap"
    if v in ("плашки", "плашка", "die"):
        return "die"
    return v if v in COLLET_THREADING_USE_VALUES else ""


def collet_type_display(code: str) -> str:
    return _COLLET_TYPE_LABELS.get((code or "").strip(), code or "—")


def build_collet_display_name(
    *,
    collet_type: str,
    er_size: str = "",
    clamp_range: str = "",
    high_precision_aa: bool = False,
    square_size: str = "",
    inner_diameter: str = "",
    thread_standard: str = "",
    threading_use: str = "",
    threading_series: str = "",
    thread_size_label: str = "",
    diameter_mm=None,
    size_label: str = "",
) -> str:
    ct = collet_type_display(collet_type)
    parts = [ct]
    if collet_type == "er":
        if er_size:
            parts.append(er_size)
        if clamp_range:
            parts.append(f"Ø {clamp_range.replace('-', '–')} мм")
        if high_precision_aa:
            parts.append("AA")
    elif collet_type == "er_g":
        if er_size:
            parts.append(er_size)
        id_key = inner_diameter or normalize_collet_er_g_inner_diameter(square_size)
        if id_key:
            label = _ER_G_INNER_LABELS.get(id_key, id_key)
            parts.append(f"Øвнутр. {label} мм")
    elif collet_type == "threading":
        if threading_use:
            parts.append(_THREADING_USE_LABELS.get(threading_use, threading_use))
        if threading_series:
            parts.append(_THREADING_SERIES_LABELS.get(threading_series, threading_series))
        if thread_standard:
            parts.append(_THREAD_STD_LABELS.get(thread_standard, thread_standard))
        if thread_size_label:
            parts.append(thread_size_label)
    else:
        if size_label:
            parts.append(size_label)
        elif er_size:
            parts.append(er_size)
    return " / ".join(parts)
