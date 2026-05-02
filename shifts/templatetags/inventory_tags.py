from django import template
from shifts.models import COATING_TYPES, COATING_TYPE_TOOLTIPS

register = template.Library()


def _norm_coating(code: object) -> str:
    c = (code or "").strip()
    return c if c else "none"


def _coating_hover_str(code: object) -> str:
    c = _norm_coating(code)
    label = dict(COATING_TYPES).get(c, str(code or ""))
    hint = COATING_TYPE_TOOLTIPS.get(c, "")
    if hint:
        return f"{label} — {hint}"
    return label


@register.simple_tag
def coating_hover(code: object) -> str:
    """Краткая подпись покрытия для title / подсказок (название + пояснение)."""
    return _coating_hover_str(code)


@register.filter
def coating_hover_title(code):
    """То же, что coating_hover, только как filter для цепочки |escapejs."""
    return _coating_hover_str(code)
