"""Удлинители инструмента (оснастка)."""

from __future__ import annotations

from decimal import Decimal

TOOL_EXTENSION_CLAMP_TYPES = [
    ("collet", "Цанговый"),
    ("side_clamp", "Боковая фиксация"),
    ("thermal", "Термо"),
]

TOOL_EXTENSION_CLAMP_VALUES = frozenset(k for k, _ in TOOL_EXTENSION_CLAMP_TYPES)
TOOL_EXTENSION_CLAMP_LABELS = dict(TOOL_EXTENSION_CLAMP_TYPES)

# Подсказка / placeholder для поля «подходящие …» по типу зажима
TOOL_EXTENSION_COMPAT_PLACEHOLDERS = {
    "collet": "Цанги: ER32, ER40…",
    "side_clamp": "Винты: M6, M8…",
    "thermal": "Винты / адаптеры…",
}

TOOL_EXTENSION_COMPAT_LABELS = {
    "collet": "Подходящие цанги",
    "side_clamp": "Подходящие винты",
    "thermal": "Подходящие винты",
}


def normalize_tool_extension_clamp(raw) -> str:
    v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "collet_chuck": "collet",
        "er": "collet",
        "цанговый": "collet",
        "цанга": "collet",
        "side": "side_clamp",
        "sideclamp": "side_clamp",
        "lateral": "side_clamp",
        "боковая": "side_clamp",
        "боковая_фиксация": "side_clamp",
        "термо": "thermal",
        "shrink": "thermal",
        "shrink_fit": "thermal",
        "термозажим": "thermal",
    }
    v = aliases.get(v, v)
    if v in TOOL_EXTENSION_CLAMP_VALUES:
        return v
    return ""


def build_tool_extension_display_name(
    *,
    brand: str = "",
    clamp_type: str = "",
    main_diameter_mm=None,
    overall_length_mm=None,
    compatible_parts: str = "",
) -> str:
    clamp = TOOL_EXTENSION_CLAMP_LABELS.get(
        normalize_tool_extension_clamp(clamp_type), (clamp_type or "").strip()
    )
    parts = ["Удлинитель"]
    if clamp:
        parts.append(clamp)

    def _fmt_mm(raw) -> str:
        try:
            d = Decimal(str(raw))
        except Exception:
            return str(raw)
        s = format(d, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s or "0"

    if main_diameter_mm is not None and str(main_diameter_mm) != "":
        parts.append(f"Dосн Ø{_fmt_mm(main_diameter_mm)}")
    if overall_length_mm is not None and str(overall_length_mm) != "":
        parts.append(f"L {_fmt_mm(overall_length_mm)}")
    compat = (compatible_parts or "").strip()
    if compat:
        parts.append(compat)
    br = (brand or "").strip()
    if br:
        parts.append(br)
    return " · ".join(parts)[:180]
