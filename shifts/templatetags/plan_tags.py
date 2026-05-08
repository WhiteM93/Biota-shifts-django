"""Шаблоны раздела «План»: оформление названий позиций."""

from django import template

from shifts.models import PlanContract
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


def _contract_pk_from_plan_request(request) -> int | None:
    if request is None:
        return None
    raw = (request.GET.get("contract") or "").strip()
    if not raw.isdigit():
        return None
    cid = int(raw)
    return cid if PlanContract.objects.filter(pk=cid).exists() else None


def _plan_contract_scope_context(request) -> dict:
    sel: int | None = None
    if request is not None:
        sel = _contract_pk_from_plan_request(request)
    return {
        "contracts_for_rail": list(PlanContract.objects.order_by("deadline", "-id")),
        "plan_rail_selected_contract_pk": sel,
    }


@register.inclusion_tag(
    "shifts/plan/includes/plan_contract_scope_select.html",
    takes_context=True,
)
def plan_contract_scope_select(context):
    request = context.get("request")
    return _plan_contract_scope_context(request)


@register.inclusion_tag(
    "shifts/plan/includes/plan_rail_department_buttons.html",
    takes_context=True,
)
def plan_rail_department_buttons(context):
    request = context.get("request")
    sel: int | None = None
    if request is not None:
        sel = _contract_pk_from_plan_request(request)
    return {"items": plan_rail_department_link_items(), "plan_rail_selected_contract_pk": sel}


@register.inclusion_tag("shifts/plan/includes/planned_product_name_heading.html")
def planned_product_heading(name: str):
    code, title = _plan_name_parts(name or "")
    return {
        "code": code,
        "title": title,
        "full": (name or "").strip(),
    }
