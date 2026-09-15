"""Нормализация обозначений размера режущего инструмента.

Кириллическая «М»/«м» и латинская «M», а также десятичная запятая и точка
(М2,5 / M2.5) считаются одним размером — иначе в фильтрах появляются дубликаты.

Голое число для метрической резьбы (8, 2.5) приводится к M8 / M2.5.
"""

from __future__ import annotations

import re

_METRIC_BARE_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_METRIC_M_NUM_RE = re.compile(r"^M(\d+)(?:\.(\d+))?$", re.IGNORECASE)
_METRIC_SIZE_RE = re.compile(r"^M(\d+(?:\.\d+)?)", re.IGNORECASE)


def normalize_cutting_size_label(raw) -> str:
    """Канонический size_label: trim, М→M, запятая→точка, 8→M8, M08→M8."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("М", "M").replace("м", "M").replace(",", ".")
    # m8 / M8 → единый префикс
    if len(text) >= 2 and text[0] in "mM" and text[1].isdigit():
        text = "M" + text[1:]
    # просто число → M{число}
    if _METRIC_BARE_NUM_RE.fullmatch(text):
        text = "M" + text
    # M08 → M8, M08.5 → M8.5 (ведущие нули только в целой части)
    m = _METRIC_M_NUM_RE.fullmatch(text)
    if m:
        int_part = str(int(m.group(1)))
        frac = m.group(2)
        text = "M" + int_part + (("." + frac) if frac is not None else "")
    return text


def size_label_match_variants(raw) -> list[str]:
    """Варианты для фильтра по уже существующим «грязным» данным (M/М, ./,, без M)."""
    norm = normalize_cutting_size_label(raw)
    if not norm:
        return []
    cyr = norm.replace("M", "М")
    comma = norm.replace(".", ",")
    cyr_comma = cyr.replace(".", ",")
    out: list[str] = []
    for v in (norm, cyr, comma, cyr_comma, str(raw or "").strip()):
        if v and v not in out:
            out.append(v)
    # M8 ↔ 8 (старые записи без префикса)
    m = _METRIC_M_NUM_RE.fullmatch(norm)
    if m:
        bare = m.group(1) + (("." + m.group(2)) if m.group(2) is not None else "")
        if bare not in out:
            out.append(bare)
        bare_comma = bare.replace(".", ",")
        if bare_comma not in out:
            out.append(bare_comma)
    return out


def size_label_sort_key(label: str):
    """Сортировка метрических размеров по числу: M2, M2.5, M3… M10."""
    text = normalize_cutting_size_label(label)
    m = _METRIC_SIZE_RE.match(text)
    if m:
        try:
            return (0, float(m.group(1)), text.casefold())
        except ValueError:
            pass
    return (1, 0.0, text.casefold())
