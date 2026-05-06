"""Отделы для маршрута изделий в разделе «План» (фиксированный справочник)."""

# Значение в БД = подпись (как ввели пользователи; «сарка» → Сборка, «покарска» → Покраска).
PLANNED_PRODUCT_DEPARTMENT_CHOICES: tuple[tuple[str, str], ...] = (
    ("Заготовительная", "Заготовительная"),
    ("Лазерный", "Лазерный"),
    ("Гибочный", "Гибочный"),
    ("Сварочный", "Сварочный"),
    ("Фрезерный", "Фрезерный"),
    ("Токарный", "Токарный"),
    ("Гальваника", "Гальваника"),
    ("РТИ", "РТИ"),
    ("Слесарка", "Слесарка"),
    ("Покраска", "Покраска"),
    ("Маркировка", "Маркировка"),
    ("Сборка", "Сборка"),
)

PLANNED_PRODUCT_DEPARTMENT_VALUES: frozenset[str] = frozenset(v for v, _ in PLANNED_PRODUCT_DEPARTMENT_CHOICES)

# Стабильные slug для URL («Планирование по отделам» в шторке).
PLAN_DEPARTMENT_URL_SLUGS: tuple[tuple[str, str], ...] = (
    ("zagotovitelnaya", "Заготовительная"),
    ("lazer", "Лазерный"),
    ("gibochnyj", "Гибочный"),
    ("svarchnyj", "Сварочный"),
    ("frezernyj", "Фрезерный"),
    ("tokarnyj", "Токарный"),
    ("galvanika", "Гальваника"),
    ("rti", "РТИ"),
    ("slesarka", "Слесарка"),
    ("pokraska", "Покраска"),
    ("markirovka", "Маркировка"),
    ("sborka", "Сборка"),
)

PLAN_DEPARTMENT_SLUG_TO_NAME: dict[str, str] = {s: n for s, n in PLAN_DEPARTMENT_URL_SLUGS}

PLAN_RAIL_PKI_SLUG = "pki"


def plan_rail_department_link_items():
    """Кнопки правой шторки: отделы + пункт «ПКИ» (muted)."""
    rows: list[dict] = [
        {"slug": slug, "label": label, "muted": False} for slug, label in PLAN_DEPARTMENT_URL_SLUGS
    ]
    rows.append({"slug": PLAN_RAIL_PKI_SLUG, "label": "ПКИ", "muted": True})
    return rows
