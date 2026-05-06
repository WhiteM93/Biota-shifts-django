"""Шаблоны раздела «План»: оформление названий позиций."""

from django import template

from shifts.plan_departments import plan_rail_department_link_items

register = template.Library()


def _plan_name_parts(full: str) -> tuple[str, str]:
    """Деление «ВРПЕ.… СБ — Кожух» по первому вхождению « — »."""
    s = (full or "").strip()
    if not s:
        return "", ""
    if " - " not in s:
        return "", s
    code, _, title = s.partition(" - ")
    code, title = code.strip(), title.strip()
    if not title:
        return "", code
    return code, title


@register.inclusion_tag("shifts/plan/includes/planned_product_name_link.html")
def planned_product_link(url: str, name: str, compact: bool = False):
    code, title = _plan_name_parts(name or "")
    return {
        "url": url or "#",
        "code": code,
        "title": title,
        "full": (name or "").strip(),
        "compact": compact,
    }


@register.inclusion_tag("shifts/plan/includes/plan_rail_department_buttons.html")
def plan_rail_department_buttons():
    return {"items": plan_rail_department_link_items()}


@register.inclusion_tag("shifts/plan/includes/planned_product_name_heading.html")
def planned_product_heading(name: str):
    code, title = _plan_name_parts(name or "")
    return {
        "code": code,
        "title": title,
        "full": (name or "").strip(),
    }
