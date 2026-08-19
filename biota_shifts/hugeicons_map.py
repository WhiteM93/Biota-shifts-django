"""Hugeicons Stroke Rounded — пресет для реестра иконок Biota (локальные SVG)."""
from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import SafeString, mark_safe

from biota_shifts.icon_registry import DEFAULT_ICON_REGISTRY

HUGICONS_STYLE = "stroke-rounded"
HUGICONS_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HUGICONS_SVG_DIR = Path(settings.BASE_DIR) / "static" / "icons" / "hugeicons" / "svg"

# Ключ реестра → slug (имя SVG-файла в static/icons/hugeicons/svg/)
HUGICONS_STROKE_ROUNDED: dict[str, str] = {
    "cabinet.django_admin": "settings-01",
    "cabinet.schedule_backups": "calendar-01",
    "cabinet.inventory_backups": "package-01",
    "cabinet.regulations_backups": "clipboard-01",
    "cabinet.perf_diagnostics": "timer-01",
    "cabinet.notifications": "notification-01",
    "cabinet.icons": "paint-board",
    "action.upload": "upload-01",
    "action.search": "search-01",
    "action.add_document": "file-add-01",
    "action.add": "plus-sign",
    "action.camera": "camera-01",
    "action.copy": "copy-01",
    "action.plus": "plus-sign-circle",
    "action.calendar": "calendar-03",
    "action.picture": "image-01",
    "nav.home": "home-01",
    "nav.inventory": "package-01",
    "nav.user": "user-01",
    "nav.forms": "task-01",
    "nav.calendar": "calendar-03",
    "nav.hours_skud": "clock-01",
    "nav.hr_payroll": "user-group",
    "nav.machines": "check-list",
    "nav.setups": "wrench-01",
    "nav.calculator": "calculator-01",
    "action.delete": "delete-02",
    "action.quick_edit": "edit-01",
    "action.quick_edit_save": "floppy-disk",
    "pdf.export_specs": "file-01",
    "pdf.export_photos": "grid-view",
    "setup.load_to_machine": "upload-01",
    "setup.tool_note_view": "view",
    "ui.close": "cancel-01",
    "ui.lock": "square-lock-01",
    "ui.unlock": "square-unlock-01",
    "ui.refresh": "refresh-01",
}

HUGICONS_SVG_SOURCE: dict[str, str] = {
    "clipboard-01": "clipboard",
    "file-add-01": "file-add",
    "package-01": "package",
    "refresh-01": "refresh",
    "user-01": "user",
}

FIGMA_PLUGIN_URL = (
    "https://www.figma.com/community/plugin/1209922740177393208/"
    "hugeicons-icon-library-4000-free-icons"
)
FIGMA_FILE_URL = (
    "https://www.figma.com/community/file/1336391869817535178/"
    "4-000-free-icons-open-source-figma-icon-library"
)


def slug_for_key(key: str) -> str:
    return HUGICONS_STROKE_ROUNDED.get(key, "")


def icon_page_url(slug: str) -> str:
    return f"https://hugeicons.com/icon/{slug}-{HUGICONS_STYLE}"


def is_valid_hugeicons_slug(value: str) -> bool:
    return bool(value and HUGICONS_SLUG_RE.match(value))


def hugeicons_svg_relpath(slug: str) -> str:
    return f"icons/hugeicons/svg/{slug}.svg"


def hugeicons_svg_url(slug: str) -> str:
    return static(hugeicons_svg_relpath(slug))


def _normalize_svg(raw: str) -> str:
    svg = re.sub(r"<\?xml[^?]*\?>", "", raw or "").strip()
    svg = svg.replace('stroke="#141B34"', 'stroke="currentColor"')
    svg = svg.replace("stroke='#141B34'", "stroke='currentColor'")
    svg = re.sub(r'\swidth="[^"]*"', "", svg)
    svg = re.sub(r'\sheight="[^"]*"', "", svg)
    return svg


def _inject_svg_classes(svg: str, css_class: str) -> str:
    classes = " ".join(
        p for p in ("biota-icon", "biota-icon--svg", "biota-icon--hgi", css_class) if p
    ).strip()
    if not classes:
        return svg
    if 'class="' in svg:
        return re.sub(
            r'(<svg[^>]*class=")([^"]*)(")',
            lambda m: f'{m.group(1)}{m.group(2)} {html.escape(classes)}{m.group(3)}',
            svg,
            count=1,
        )
    return re.sub(r"<svg", f'<svg class="{html.escape(classes)}"', svg, count=1)


@lru_cache(maxsize=128)
def _load_inline_svg(slug: str) -> str:
    path = HUGICONS_SVG_DIR / f"{slug}.svg"
    if not path.is_file():
        return ""
    return _normalize_svg(path.read_text(encoding="utf-8"))


def render_hugeicons_html(slug: str, css_class: str = "") -> SafeString:
    if not is_valid_hugeicons_slug(slug):
        return mark_safe('<span class="biota-icon biota-icon--missing">?</span>')
    svg = _load_inline_svg(slug)
    if not svg:
        cls = " ".join(
            p for p in ("biota-icon", "biota-icon--svg", "biota-icon--hgi", css_class) if p
        ).strip()
        src = hugeicons_svg_url(slug)
        return mark_safe(
            f'<img class="{html.escape(cls)}" src="{html.escape(src)}" width="16" height="16" alt="" aria-hidden="true" loading="lazy">'
        )
    return mark_safe(_inject_svg_classes(svg, css_class))


def build_hugeicons_overrides() -> dict[str, dict]:
    overrides: dict[str, dict] = {}
    for key, slug in HUGICONS_STROKE_ROUNDED.items():
        if key in DEFAULT_ICON_REGISTRY and slug:
            overrides[key] = {"kind": "hugeicons", "value": slug}
    return overrides


def apply_hugeicons_preset() -> int:
    from biota_shifts.icon_settings import set_icon_preset

    set_icon_preset("hugeicons")
    return preset_count()


def apply_default_icons_preset() -> None:
    from biota_shifts.icon_settings import set_icon_preset

    set_icon_preset("default")


def preset_count() -> int:
    return len(HUGICONS_STROKE_ROUNDED)
