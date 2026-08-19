from django import template

from biota_shifts.icons import get_icon, render_icon_html

register = template.Library()


@register.simple_tag
def biota_icon(key: str, css_class: str = "") -> str:
    return render_icon_html(key, css_class)


@register.filter
def biota_icon_value(key: str) -> str:
    return get_icon(key).get("value") or ""
