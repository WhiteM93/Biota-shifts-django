"""Нормализация подписей сотрудников склада: «Фамилия И.О.»."""
from __future__ import annotations

import re

_LETTER_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")
_HAS_CYR_RE = re.compile(r"[А-Яа-яЁё]")


def format_warehouse_employee_name(raw: str) -> str:
    """Приводит подпись к виду «Фамилия И.О.» (или «Фамилия И.» / «Фамилия»)."""
    text = " ".join((raw or "").replace("ё", "е").replace("Ё", "Е").split())
    if not text or not _HAS_CYR_RE.search(text):
        return ""
    parts = text.split()
    surname = parts[0].strip(".,;")
    if not surname:
        return ""
    surname = surname[:1].upper() + surname[1:].lower()
    initials = _extract_initials(" ".join(parts[1:]))
    if not initials:
        return surname[:120]
    return f"{surname} {initials}"[:120]


def _extract_initials(rest: str) -> str:
    rest = (rest or "").strip().strip(".")
    if not rest:
        return ""
    compact = re.sub(r"[\s.]+", "", rest)
    dotted_or_spaced = bool(re.search(r"[.\s]", rest))
    all_caps_short = bool(re.fullmatch(r"[А-ЯA-Z]{1,3}", compact))
    if re.fullmatch(r"[А-Яа-яЕеA-Za-z]{1,3}", compact) and (
        len(compact) == 1 or dotted_or_spaced or all_caps_short
    ):
        letters = [c.upper() for c in compact if c.isalpha()][:2]
        return ".".join(letters) + "." if letters else ""

    words = _LETTER_RE.findall(rest)
    letters = [w[0].upper() for w in words[:2] if w]
    if not letters:
        return ""
    return ".".join(letters) + "."


def _parse_formatted(name: str) -> tuple[str, tuple[str, ...]]:
    formatted = format_warehouse_employee_name(name)
    if not formatted:
        return "", ()
    parts = formatted.split()
    surname = parts[0].casefold()
    if len(parts) == 1:
        return surname, ()
    letters = tuple(ch for ch in parts[1] if ch.isalpha())
    return surname, letters


def prefer_warehouse_employee_name(a: str, b: str) -> str:
    """Из двух нормализованных подписей выбирает более полную (больше инициалов)."""
    fa = format_warehouse_employee_name(a)
    fb = format_warehouse_employee_name(b)
    if not fa:
        return fb
    if not fb:
        return fa
    _, ia = _parse_formatted(fa)
    _, ib = _parse_formatted(fb)
    if len(ib) > len(ia) and ia == ib[: len(ia)]:
        return fb
    if len(ia) > len(ib) and ib == ia[: len(ib)]:
        return fa
    return fa if len(ia) >= len(ib) else fb


def resolve_warehouse_employee_names(raw_names: list[str] | tuple[str, ...]) -> dict[str, str]:
    """
    raw → каноническая «Фамилия И.О.».
    Одинаковая фамилия: короткие инициалы схлопываются в более полные (М. → М.С.).
    Фамилия без инициалов не подменяется вариантом с инициалами (может быть другой человек).
    """
    formatted_by_raw: dict[str, str] = {}
    for raw in raw_names:
        key = (raw or "").strip()
        if not key:
            continue
        formatted = format_warehouse_employee_name(key)
        if formatted:
            formatted_by_raw[key] = formatted

    by_surname: dict[str, list[str]] = {}
    for formatted in set(formatted_by_raw.values()):
        surname, _ = _parse_formatted(formatted)
        by_surname.setdefault(surname, []).append(formatted)

    canonical_for_formatted: dict[str, str] = {}
    for surname, variants in by_surname.items():
        # Сначала самые полные инициалы.
        variants_sorted = sorted(
            variants,
            key=lambda n: (len(_parse_formatted(n)[1]), n),
            reverse=True,
        )
        for v in variants_sorted:
            _, iv = _parse_formatted(v)
            if not iv:
                canonical_for_formatted[v] = v
                continue
            chosen = v
            for stronger in variants_sorted:
                _, is_ = _parse_formatted(stronger)
                if len(is_) > len(iv) and iv == is_[: len(iv)]:
                    chosen = stronger
                    break
            canonical_for_formatted[v] = chosen

    return {
        raw: canonical_for_formatted.get(formatted, formatted)
        for raw, formatted in formatted_by_raw.items()
    }
