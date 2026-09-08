"""Нормализация обозначений размера режущего инструмента.

Кириллическая «М»/«м» и латинская «M» в метчиках (М6 vs M6) считаются одним
и тем же — иначе в фильтрах склада появляются дубликаты размеров.
"""

from __future__ import annotations


def normalize_cutting_size_label(raw) -> str:
    """Приводит size_label к каноническому виду: trim + кириллическая М → латинская M."""
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.replace("М", "M").replace("м", "M")


def size_label_match_variants(raw) -> list[str]:
    """Варианты для фильтра по уже существующим «грязным» данным (M и М)."""
    norm = normalize_cutting_size_label(raw)
    if not norm:
        return []
    cyr = norm.replace("M", "М")
    out: list[str] = []
    for v in (norm, cyr, str(raw or "").strip()):
        if v and v not in out:
            out.append(v)
    return out
