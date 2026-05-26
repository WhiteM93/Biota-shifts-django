"""Справочники ISO 1832 для сменных пластин (фрезерные/токарные)."""
from __future__ import annotations

from decimal import Decimal

# Форма пластины (1-я буква маркировки ISO)
INSERT_SHAPES = [
    ("C", "C — ромб 80°"),
    ("D", "D — ромб 55°"),
    ("H", "H — шестигранник"),
    ("K", "K — параллелограмм 55°"),
    ("L", "L — прямоугольник"),
    ("M", "M — ромб 86°"),
    ("O", "O — восьмиугольник"),
    ("P", "P — пятиугольник"),
    ("R", "R — круглая"),
    ("S", "S — квадрат"),
    ("T", "T — треугольник"),
    ("V", "V — ромб 35°"),
    ("W", "W — треугольник 80° (W)"),
]

INSERT_RELIEF_ANGLES = [
    ("N", "N — 0°"),
    ("A", "A — 3°"),
    ("B", "B — 5°"),
    ("C", "C — 7°"),
    ("P", "P — 11°"),
    ("D", "D — 15°"),
    ("E", "E — 20°"),
    ("F", "F — 25°"),
    ("G", "G — 30°"),
    ("O", "O — 10°"),
]

INSERT_TOLERANCE_CLASSES = [
    ("M", "M — средний"),
    ("G", "G — точный"),
    ("E", "E — точный (E)"),
    ("U", "U — грубый"),
    ("F", "F — точный (F)"),
]

INSERT_MOUNTING_CHIP = [
    ("N", "N — без отверстия"),
    ("G", "G — с отверстием, стружколом"),
    ("M", "M — с отверстием"),
    ("A", "A — с отверстием, односторонний СЛ"),
    ("W", "W — с отверстием, паз"),
    ("T", "T — с отверстием, односторонний"),
    ("Q", "Q — с отверстием, двусторонний"),
    ("X", "X — специальное"),
]

# Код длины режущей кромки (поз. 5 ISO) → типовой размер, мм
INSERT_EDGE_LENGTH_CODES = [
    ("03", "03"),
    ("04", "04"),
    ("05", "05"),
    ("06", "06"),
    ("07", "07"),
    ("09", "09"),
    ("12", "12"),
    ("16", "16"),
    ("19", "19"),
    ("20", "20"),
    ("25", "25"),
    ("32", "32"),
]

# Код толщины (поз. 6 ISO) → мм (стандарт ISO 1832)
INSERT_THICKNESS_CODE_MM: dict[str, Decimal] = {
    "01": Decimal("1.98"),
    "02": Decimal("2.38"),
    "03": Decimal("3.18"),
    "04": Decimal("4.76"),
    "05": Decimal("5.56"),
    "06": Decimal("6.35"),
    "07": Decimal("7.94"),
    "09": Decimal("9.52"),
    "12": Decimal("12.70"),
}

INSERT_THICKNESS_CODES = [(k, f"{k} ({v} мм)") for k, v in sorted(INSERT_THICKNESS_CODE_MM.items())]

# Код радиуса при вершине (поз. 7) → мм (×0.1 мм для двузначного кода)
INSERT_NOSE_RADIUS_CODE_MM: dict[str, Decimal] = {
    "00": Decimal("0"),
    "02": Decimal("0.2"),
    "04": Decimal("0.4"),
    "08": Decimal("0.8"),
    "12": Decimal("1.2"),
    "16": Decimal("1.6"),
    "20": Decimal("2.0"),
    "24": Decimal("2.4"),
    "32": Decimal("3.2"),
}

INSERT_NOSE_RADIUS_CODES = [(k, f"{k} ({v} мм)") for k, v in sorted(INSERT_NOSE_RADIUS_CODE_MM.items())]

# Семейства пластин для фрез (каталоги поставщиков, в т.ч. cncmagazine.ru)
INSERT_FAMILY_OTHER = "OTHER"

# Вид обработки (геометрия стружколома): 1 чистовая, 2 получистовая, 3 черновая
INSERT_MACHINING_APPLICATIONS = [
    ("1", "Чистовая"),
    ("2", "Получистовая"),
    ("3", "Черновая"),
]

INSERT_MACHINING_APPLICATION_VALUES = frozenset(k for k, _ in INSERT_MACHINING_APPLICATIONS)
INSERT_MACHINING_APP_ORDER = tuple(k for k, _ in INSERT_MACHINING_APPLICATIONS)


def normalize_insert_machining_apps(raw) -> str:
    """Один или несколько видов обработки: «1», «1,3» (порядок 1,2,3)."""
    if isinstance(raw, (list, tuple)):
        parts = [str(x).strip() for x in raw]
    else:
        parts = [p.strip() for p in str(raw or "").replace(" ", "").split(",") if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in INSERT_MACHINING_APPLICATION_VALUES or p in seen:
            continue
        seen.add(p)
        out.append(p)
    out.sort(key=lambda x: INSERT_MACHINING_APP_ORDER.index(x))
    return ",".join(out)

# Марки сплава / покрытия пластин (каталог для прихода и фильтров склада)
INSERT_GRADE_OTHER = "OTHER"

INSERT_CHIPBREAKER_GRADES = (
    "1DA44",
    "2MI40",
    "C10",
    "CA130",
    "CA5020",
    "CA5220",
    "CA5220A",
    "CA6535",
    "CAC315",
    "CAC316",
    "CAD126",
    "CAG216",
    "CAG219",
    "CAG219H",
    "CAG226",
    "CAG316",
    "CAM227",
    "CAM325",
    "CAS317",
    "CH530",
    "CH550",
    "CK3210",
    "CM200",
    "CM930",
    "CP100",
    "CP130",
    "CP200",
    "CPM130",
    "CS308",
    "CT200",
    "CT5320",
    "CT5420",
    "CT7320",
    "CT7420",
    "CT8320",
    "CT8420",
    "CY250",
    "DC6018",
    "DC6028",
    "DC6028S",
    "DF618",
    "DM215",
    "HC844",
    "HR52522B",
    "HS5120",
    "HS5130",
    "IA6325",
    "IA6330",
    "IA6525",
    "IA9015",
    "IC328",
    "IC808",
    "IC830",
    "IC908",
    "IC928",
    "IH6015",
    "IH6025",
    "IK5015",
    "IK6025",
    "IM5040",
    "IM6035",
    "IM6140",
    "IN8025",
    "IP5015",
    "IP5120",
    "IP5150",
    "IP5520",
    "IP6325",
    "IP7120",
    "IP90M",
    "IPC7120",
    "IPD5520",
    "IPM2020",
    "IPM8520",
    "IPMM7510",
    "IR1210",
    "IR1225",
    "IR1230",
    "IS6030",
    "ISM2030",
    "JT1025",
    "K10",
    "L10",
    "LDA",
    "LF6018",
    "LF6018P",
    "LF6028",
    "MK330",
    "MK35",
    "MK613A",
    "MP6120",
    "MP6130",
    "MP7030",
    "NZ5501",
    "NZ5502",
    "NZ5503",
    "PMK",
    "PR1225",
    "TC1025",
    "TC1225",
    "TC4340",
    "TF618",
    "TR250",
    "VP15TF",
    "VP201",
    "VP30RT",
    "WS5130",
    "YB602",
    "YF154",
    "YG012",
    "YG50",
    "YG500",
    "YG501",
    "YG5020",
    "YG602",
    "YG603",
    "YG612",
    "YG613",
    "YG622",
    "YG712",
    "YG713",
    "YKF640",
    "YKH855",
    "YKT64Y",
    "YKT64Y-1",
    "YKT65Y",
    "YKT742",
    "YKT742-1",
    "YT5",
    "ZC25",
    "ZK01",
    "ZM36",
    "ZM36H",
    "ZM886",
    "ZP1320",
    "ZP15",
    "ZP150",
    "ZP152",
    "ZP153",
    "ZP163",
    "ВК8",
    "Т15К6",
    "Т5К10",
)


def merge_insert_chipbreaker_grades(*extra_lists: list[str] | None) -> list[str]:
    """Каталог марок + уникальные значения из БД, без дублей."""
    seen: set[str] = set()
    out: list[str] = []
    for v in INSERT_CHIPBREAKER_GRADES:
        s = (v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    for lst in extra_lists:
        for v in lst or []:
            s = (v or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
    return out


# Подсказки к столбцам и полям пластинок (приход, склад, фильтры)
INSERT_COLUMN_TOOLTIPS = {
    "iso": "Полная маркировка ISO 1832",
    "family": "Семейство пластины (APKT, APMT, SEHT и др.)",
    "shape": "Форма пластины по ISO 1832 (C, D, T…)",
    "relief": "Задний угол (рельеф) пластины",
    "tolerance": "Класс допуска по ISO",
    "edge_l": "Длина пластинки — код L по ISO 1832",
    "thickness_s": "Толщина пластинки — код S по ISO 1832",
    "radius_r": "Радиус пластинки — код R по ISO 1832",
    "grade": "Сплав / марка пластины (YG501, ВК8, TC1225 и др.)",
    "machining_application": "Вид обработки (можно несколько): чистовая, получистовая, черновая",
    "tool_material": "Сплав / марка пластины (YG501, ВК8, TC1225 и др.)",
    "coating": "Покрытие пластины",
    "work_material": "Группы обрабатываемого материала (можно несколько: P, M, K, N, S, H, PW)",
    "quantity": "Количество в приходе, шт.",
    "stock_qty": "Остаток на складе, шт.",
    "row_remove": "Удалить строку прихода",
    "delete": "Удалить позицию со склада",
}

MILLING_INSERT_FAMILIES = [
    ("", "— не указано —"),
    ("APKT", "APKT — пластина 80°"),
    ("APMT", "APMT"),
    ("APHT", "APHT"),
    ("ADKT", "ADKT"),
    ("SEKT", "SEKT"),
    ("SEHT", "SEHT"),
    ("SNHT", "SNHT"),
    ("SPGT", "SPGT"),
    ("SPHT", "SPHT"),
    ("RPMT", "RPMT"),
    ("R390", "R390"),
    ("CNMG", "CNMG (токарная)"),
    ("WNMG", "WNMG (токарная)"),
    ("TNMG", "TNMG (токарная)"),
    ("SNMG", "SNMG (токарная)"),
    ("CCMT", "CCMT"),
    ("DCMT", "DCMT"),
    ("VCMT", "VCMT"),
    (INSERT_FAMILY_OTHER, "Другое"),
]

MILLING_INSERT_FAMILY_VALUES = frozenset(k for k, _ in MILLING_INSERT_FAMILIES if k and k != INSERT_FAMILY_OTHER)


def normalize_milling_family(value: str) -> str:
    """Семейство пластины всегда в верхнем регистре; OTHER и пусто — не сохраняем."""
    v = (value or "").strip()
    if not v or v == INSERT_FAMILY_OTHER:
        return ""
    return v.upper()[:24]


INSERT_SHAPE_VALUES = frozenset(k for k, _ in INSERT_SHAPES)
INSERT_RELIEF_VALUES = frozenset(k for k, _ in INSERT_RELIEF_ANGLES)
INSERT_TOLERANCE_VALUES = frozenset(k for k, _ in INSERT_TOLERANCE_CLASSES)
INSERT_MOUNTING_VALUES = frozenset(k for k, _ in INSERT_MOUNTING_CHIP)


def edge_length_mm_from_code(code: str) -> Decimal | None:
    c = (code or "").strip()
    if not c:
        return None
    try:
        return Decimal(c)
    except Exception:
        return None


def thickness_mm_from_code(code: str) -> Decimal | None:
    return INSERT_THICKNESS_CODE_MM.get((code or "").strip())


def nose_radius_mm_from_code(code: str) -> Decimal | None:
    return INSERT_NOSE_RADIUS_CODE_MM.get((code or "").strip())


def build_iso_designation(
    shape: str,
    relief: str,
    tolerance: str,
    mounting: str,
    edge_code: str,
    thickness_code: str,
    nose_code: str,
) -> str:
    s = (shape or "").strip().upper()[:1]
    r = (relief or "").strip().upper()[:1]
    t = (tolerance or "").strip().upper()[:1]
    m = (mounting or "").strip().upper()[:1]
    e = (edge_code or "").strip()
    th = (thickness_code or "").strip()
    n = (nose_code or "").strip()
    if not all([s, r, t, m, e, th, n]):
        return ""
    return f"{s}{r}{t}{m}{e}{th}{n}"


def build_insert_display_name(iso: str, family: str = "", grade: str = "") -> str:
    parts = []
    fam = normalize_milling_family(family or "")
    if fam:
        parts.append(fam)
    iso_s = (iso or "").strip()
    if iso_s:
        parts.append(iso_s)
    gr = (grade or "").strip()
    if gr:
        parts.append(gr)
    return " ".join(parts) if parts else "Пластина"
