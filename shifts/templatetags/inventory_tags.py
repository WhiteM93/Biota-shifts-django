from django import template
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from shifts.insert_constants import INSERT_MACHINING_APPLICATIONS
from shifts.models import COATING_TYPES, COATING_TYPE_TOOLTIPS
from shifts.size_label_normalize import normalize_cutting_size_label

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


_MACH_LABELS = dict(INSERT_MACHINING_APPLICATIONS)


@register.filter
def insert_machining_tooltip(code):
    """Подсказка для вида обработки пластины (1, 2, 3)."""
    c = (code or "").strip()
    return _MACH_LABELS.get(c, c)


@register.filter
def size_norm(value):
    """Размер метчика/зенкера: М→M, запятая→точка."""
    if value in (None, ""):
        return value
    return normalize_cutting_size_label(value)


@register.filter(is_safe=False)
def dotformat(value, arg="-2"):
    """Как floatformat, но всегда с точкой (без русской локали 2,80)."""
    if value in (None, ""):
        return ""
    try:
        d = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return str(value).replace(",", ".")

    places_raw = str(arg or "-2").strip()
    try:
        places = int(places_raw)
    except ValueError:
        places = -2

    if places < 0:
        max_places = abs(places)
        q = Decimal("1").scaleb(-max_places)
        d = d.quantize(q, rounding=ROUND_HALF_UP)
        s = format(d, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s or "0"

    q = Decimal("1").scaleb(-places) if places else Decimal("1")
    d = d.quantize(q, rounding=ROUND_HALF_UP)
    return format(d, f".{places}f") if places else format(d, "f").split(".")[0]
