from django import template
from shifts.insert_constants import INSERT_MACHINING_APPLICATIONS
from shifts.models import COATING_TYPES, COATING_TYPE_TOOLTIPS, WORK_MATERIAL_TYPES

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


_WM_LABELS = dict(WORK_MATERIAL_TYPES)
_MACH_LABELS = dict(INSERT_MACHINING_APPLICATIONS)


@register.filter
def work_material_tooltip(code):
    """Подсказка для одного кода материала обработки (P, M, K…)."""
    c = (code or "").strip().upper()
    return _WM_LABELS.get(c, c)


@register.filter
def insert_machining_tooltip(code):
    """Подсказка для вида обработки пластины (1, 2, 3)."""
    c = (code or "").strip()
    return _MACH_LABELS.get(c, c)
