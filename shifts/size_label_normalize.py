"""Нормализация обозначений размера режущего инструмента.

Кириллическая «М»/«м» и латинская «M», а также десятичная запятая и точка
(М2,5 / M2.5) считаются одним размером — иначе в фильтрах появляются дубликаты.
"""

from __future__ import annotations

import re


def normalize_cutting_size_label(raw) -> str:
    """Канонический size_label: trim, М→M, запятая→точка."""
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.replace("М", "M").replace("м", "M").replace(",", ".")


def size_label_match_variants(raw) -> list[str]:
    """Варианты для фильтра по уже существующим «грязным» данным (M/М, ./,)."""
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
    return out


_METRIC_SIZE_RE = re.compile(r"^M(\d+(?:\.\d+)?)", re.IGNORECASE)


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
