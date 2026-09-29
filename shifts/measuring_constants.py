"""Измерительный инструмент: категории склада и виды (3-й уровень)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Ключи ToolItem.category (группа «Измерительный инструмент» в фильтре).
MEASURING_CATEGORIES = (
    "gauge_smooth",
    "gauge_thread",
    "measure_univ",
    "measure_surf",
    "measure_check",
    "measure_mark",
)

MEASURING_CATEGORY_SET = frozenset(MEASURING_CATEGORIES)

MEASURING_CATEGORY_LABELS = {
    "gauge_smooth": "Гладкие калибры",
    "gauge_thread": "Резьбовые калибры",
    "measure_univ": "Универсальный измерительный",
    "measure_surf": "Шероховатость и твёрдость",
    "measure_check": "Поверочная оснастка",
    "measure_mark": "Разметочный инструмент",
}

# Виды внутри категории (как «тип фрезы»).
MEASURING_KINDS_BY_CATEGORY: dict[str, tuple[tuple[str, str], ...]] = {
    "gauge_smooth": (),
    "gauge_thread": (
        ("plug", "Пробка"),
        ("ring", "Кольцо"),
    ),
    "measure_univ": (
        ("caliper", "Штангенциркуль"),
        ("micrometer", "Микрометры"),
        ("bore_gauge", "Нутромеры"),
        ("dial_indicator", "Индикатор часового типа"),
        ("square", "Угольники"),
        ("protractor", "Угломеры"),
        ("feeler", "Щупы"),
        ("gauge_blocks", "Концевые меры длины"),
    ),
    "measure_surf": (
        ("roughness_sample", "Образцы шероховатости"),
        ("profilometer", "Профилометры"),
        ("hardness_tester", "Твердомеры"),
    ),
    "measure_check": (
        ("surface_plate", "Поверочные плиты"),
        ("prism", "Призмы поверочные"),
        ("sine_table", "Синусные столы"),
        ("stand", "Стойки и штативы"),
    ),
    "measure_mark": (
        ("scriber", "Чертилки"),
        ("center_punch", "Кернеры"),
        ("height_gauge", "Рейсмасы"),
        ("marking_compass", "Разметочные циркули"),
    ),
}

MEASURING_KIND_CHOICES: list[tuple[str, str]] = []
_seen_kinds: set[str] = set()
for _pairs in MEASURING_KINDS_BY_CATEGORY.values():
    for code, label in _pairs:
        if code in _seen_kinds:
            continue
        _seen_kinds.add(code)
        MEASURING_KIND_CHOICES.append((code, label))

MEASURING_KIND_LABELS = dict(MEASURING_KIND_CHOICES)

THREAD_GAUGE_GO_NOGO = (
    ("go", "Проходной"),
    ("nogo", "Непроходной"),
    ("set", "Комплект"),
)
THREAD_GAUGE_GO_NOGO_LABELS = dict(THREAD_GAUGE_GO_NOGO)


def measuring_category_needs_kind(category: str) -> bool:
    return bool(MEASURING_KINDS_BY_CATEGORY.get((category or "").strip()))


def normalize_measuring_kind(category: str, raw) -> str:
    cat = (category or "").strip()
    v = str(raw or "").strip()
    allowed = {code for code, _ in MEASURING_KINDS_BY_CATEGORY.get(cat, ())}
    if not allowed:
        return ""
    return v if v in allowed else ""


def measuring_kind_label(kind: str) -> str:
    return MEASURING_KIND_LABELS.get((kind or "").strip(), (kind or "").strip())


def normalize_thread_gauge_go_nogo(raw) -> str:
    v = str(raw or "").strip().lower()
    if v in THREAD_GAUGE_GO_NOGO_LABELS:
        return v
    return ""


def normalize_measuring_pitch(raw) -> Decimal | None:
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        val = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if val <= 0:
        return None
    return val.quantize(Decimal("0.001"))


def build_measuring_display_name(
    *,
    category: str,
    brand: str = "",
    kind: str = "",
    notes: str = "",
    thread_size_label: str = "",
    pitch_mm=None,
    go_nogo: str = "",
    measure_range: str = "",
    accuracy: str = "",
    ip_rating: str = "",
    check_size: str = "",
    check_accuracy_class: str = "",
    length_mm=None,
) -> str:
    cat = (category or "").strip()
    parts: list[str] = []
    brand_s = (brand or "").strip()
    kind_s = measuring_kind_label(kind) if kind else ""
    notes_s = (notes or "").strip()
    size_s = (thread_size_label or "").strip()
    if brand_s:
        parts.append(brand_s)
    if kind_s:
        parts.append(kind_s)
    if size_s:
        pitch_s = ""
        if pitch_mm is not None:
            try:
                pitch_s = format(Decimal(pitch_mm), "f").rstrip("0").rstrip(".")
            except (InvalidOperation, TypeError, ValueError):
                pitch_s = ""
        parts.append(f"{size_s}×{pitch_s}" if pitch_s else size_s)
    go_lab = THREAD_GAUGE_GO_NOGO_LABELS.get((go_nogo or "").strip())
    if go_lab:
        parts.append(go_lab)
    range_s = (measure_range or "").strip()
    if range_s:
        parts.append(range_s)
    acc_s = (accuracy or "").strip()
    if acc_s:
        parts.append(acc_s)
    ip_s = (ip_rating or "").strip()
    if ip_s:
        parts.append(ip_s)
    check_size_s = (check_size or "").strip()
    if check_size_s:
        parts.append(check_size_s)
    check_acc_s = (check_accuracy_class or "").strip()
    if check_acc_s:
        parts.append(check_acc_s)
    if length_mm is not None:
        try:
            length_s = format(Decimal(length_mm), "f").rstrip("0").rstrip(".")
        except (InvalidOperation, TypeError, ValueError):
            length_s = ""
        if length_s:
            parts.append(f"L {length_s}")
    if not parts and notes_s:
        parts.append(notes_s[:80])
    if not parts and cat in MEASURING_CATEGORY_LABELS:
        parts.append(MEASURING_CATEGORY_LABELS[cat])
    name = " · ".join(parts).strip(" ·")
    return (name or MEASURING_CATEGORY_LABELS.get(cat, "Измерительный"))[:180]


def normalize_measuring_length(raw) -> Decimal | None:
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        val = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if val <= 0:
        return None
    return val.quantize(Decimal("0.01"))

