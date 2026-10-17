"""Подтянуть сотрудников склада из истории движений (Фамилия И.О.)."""

from django.db import migrations


def _format_name(raw: str) -> str:
    import re

    letter_re = re.compile(r"[А-Яа-яЁёA-Za-z]+")
    has_cyr_re = re.compile(r"[А-Яа-яЁё]")
    text = " ".join((raw or "").replace("ё", "е").replace("Ё", "Е").split())
    if not text or not has_cyr_re.search(text):
        return ""
    parts = text.split()
    surname = parts[0].strip(".,;")
    if not surname:
        return ""
    surname = surname[:1].upper() + surname[1:].lower()
    rest = " ".join(parts[1:]).strip().strip(".")
    if not rest:
        return surname[:120]
    compact = re.sub(r"[\s.]+", "", rest)
    dotted_or_spaced = bool(re.search(r"[.\s]", rest))
    all_caps_short = bool(re.fullmatch(r"[А-ЯA-Z]{1,3}", compact))
    if re.fullmatch(r"[А-Яа-яЕеA-Za-z]{1,3}", compact) and (
        len(compact) == 1 or dotted_or_spaced or all_caps_short
    ):
        letters = [c.upper() for c in compact if c.isalpha()][:2]
        initials = ".".join(letters) + "." if letters else ""
    else:
        words = letter_re.findall(rest)
        letters = [w[0].upper() for w in words[:2] if w]
        initials = ".".join(letters) + "." if letters else ""
    if not initials:
        return surname[:120]
    return f"{surname} {initials}"[:120]


def _parse(name: str) -> tuple[str, tuple[str, ...]]:
    formatted = _format_name(name)
    if not formatted:
        return "", ()
    parts = formatted.split()
    surname = parts[0].casefold()
    if len(parts) == 1:
        return surname, ()
    letters = tuple(ch for ch in parts[1] if ch.isalpha())
    return surname, letters


def _resolve(raw_names: list[str]) -> dict[str, str]:
    formatted_by_raw: dict[str, str] = {}
    for raw in raw_names:
        key = (raw or "").strip()
        if not key:
            continue
        formatted = _format_name(key)
        if formatted:
            formatted_by_raw[key] = formatted

    by_surname: dict[str, list[str]] = {}
    for formatted in set(formatted_by_raw.values()):
        surname, _ = _parse(formatted)
        by_surname.setdefault(surname, []).append(formatted)

    canonical_for_formatted: dict[str, str] = {}
    for _surname, variants in by_surname.items():
        variants_sorted = sorted(
            variants,
            key=lambda n: (len(_parse(n)[1]), n),
            reverse=True,
        )
        for v in variants_sorted:
            _, iv = _parse(v)
            if not iv:
                canonical_for_formatted[v] = v
                continue
            chosen = v
            for stronger in variants_sorted:
                _, is_ = _parse(stronger)
                if len(is_) > len(iv) and iv == is_[: len(iv)]:
                    chosen = stronger
                    break
            canonical_for_formatted[v] = chosen

    return {
        raw: canonical_for_formatted.get(formatted, formatted)
        for raw, formatted in formatted_by_raw.items()
    }


def forwards(apps, schema_editor):
    WarehouseEmployee = apps.get_model("shifts", "WarehouseEmployee")
    StockMovement = apps.get_model("shifts", "StockMovement")

    raw_names = list(
        StockMovement.objects.exclude(employee_name="")
        .values_list("employee_name", flat=True)
        .distinct()
    )
    mapping = _resolve(raw_names)
    if not mapping:
        return

    for canonical in sorted(set(mapping.values())):
        WarehouseEmployee.objects.get_or_create(
            name=canonical,
            defaults={"note": "", "is_active": True},
        )

    # Переписать подписи в движениях на канон, чтобы фильтры и список совпадали.
    by_target: dict[str, list[str]] = {}
    for raw, canonical in mapping.items():
        if raw != canonical:
            by_target.setdefault(canonical, []).append(raw)
    for canonical, olds in by_target.items():
        StockMovement.objects.filter(employee_name__in=olds).update(employee_name=canonical)


def backwards(apps, schema_editor):
    # Обратный проход не восстанавливает старые подписи в движениях и не удаляет список.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0194_warehouse_employee"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
