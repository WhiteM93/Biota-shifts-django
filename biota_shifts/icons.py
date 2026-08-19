"""Разрешение и рендер иконок."""
from __future__ import annotations

import html

from django.template.loader import render_to_string
from django.utils.safestring import SafeString, mark_safe

from biota_shifts.icon_registry import DEFAULT_ICON_REGISTRY
from biota_shifts.icon_settings import get_effective_overrides, load_icon_settings
from biota_shifts.hugeicons_map import hugeicons_svg_url, render_hugeicons_html


def get_icon(key: str) -> dict:
    base = DEFAULT_ICON_REGISTRY.get(key)
    if not base:
        return {
            "key": key,
            "label": key,
            "group": "Неизвестно",
            "kind": "text",
            "value": "?",
        }
    out = dict(base)
    out["key"] = key
    override = get_effective_overrides().get(key) or {}
    if override.get("kind"):
        out["kind"] = override["kind"]
    if override.get("value"):
        out["value"] = override["value"]
    return out


def list_icons_grouped() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for key in sorted(DEFAULT_ICON_REGISTRY.keys()):
        spec = get_icon(key)
        groups.setdefault(spec["group"], []).append(spec)
    return [{"group": g, "items": groups[g]} for g in sorted(groups.keys())]


def icons_for_js() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key in DEFAULT_ICON_REGISTRY:
        spec = get_icon(key)
        if spec["kind"] in ("flaticon", "emoji", "text", "svg_static", "hugeicons"):
            val = spec["value"]
            if spec["kind"] == "svg_static":
                from django.templatetags.static import static

                val = static(val)
            elif spec["kind"] == "hugeicons":
                slug = val
                val = hugeicons_svg_url(slug)
                entry: dict = {"kind": spec["kind"], "value": val}
                inline = render_hugeicons_html(slug, "")
                if inline:
                    entry["inline"] = str(inline)
                out[key] = entry
                continue
            out[key] = {"kind": spec["kind"], "value": val}
    return out


def _join_classes(*parts: str) -> str:
    return " ".join(p for p in parts if p).strip()


def render_icon_html(key: str, css_class: str = "") -> SafeString:
    spec = get_icon(key)
    kind = spec.get("kind") or "text"
    value = spec.get("value") or ""
    extra = _join_classes("biota-icon", css_class)

    if kind == "partial":
        try:
            return mark_safe(render_to_string(value, {}))
        except Exception:
            return mark_safe(f'<span class="{extra} biota-icon--missing">?</span>')

    if kind == "flaticon":
        cls = _join_classes(value, extra, "biota-icon--fi")
        return mark_safe(f'<i class="{html.escape(cls)}" aria-hidden="true"></i>')

    if kind == "hugeicons":
        return render_hugeicons_html(value, extra)

    if kind == "svg_static":
        from django.templatetags.static import static

        src = static(value)
        cls = _join_classes(extra, "biota-icon", "biota-icon--svg")
        return mark_safe(
            f'<img class="{html.escape(cls)}" src="{html.escape(src)}" alt="" aria-hidden="true" loading="lazy">'
        )

    if kind == "emoji":
        cls = _join_classes(extra, "biota-icon--emoji")
        return mark_safe(f'<span class="{html.escape(cls)}" aria-hidden="true">{html.escape(value)}</span>')

    cls = _join_classes(extra, "biota-icon--text")
    return mark_safe(f'<span class="{html.escape(cls)}" aria-hidden="true">{html.escape(value)}</span>')


def icons_json_for_template() -> str:
    import json

    return json.dumps(icons_for_js(), ensure_ascii=False)
