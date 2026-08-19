"""Кандидаты на замену иконок (SVG из Figma → static/icons/candidates/)."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

from biota_shifts.icon_registry import DEFAULT_ICON_REGISTRY
from biota_shifts.icons import get_icon
from biota_shifts.hugeicons_map import (
    HUGICONS_STROKE_ROUNDED,
    icon_page_url,
    render_hugeicons_html,
    slug_for_key,
)

CANDIDATES_DIR = Path(settings.BASE_DIR) / "static" / "icons" / "candidates"


def _candidate_path(key: str) -> Path:
    safe = key.replace("/", "_")
    return CANDIDATES_DIR / f"{safe}.svg"


def candidate_exists(key: str) -> bool:
    return _candidate_path(key).is_file()


def candidate_static_url(key: str) -> str:
    if not candidate_exists(key):
        return ""
    safe = key.replace("/", "_")
    return static(f"icons/candidates/{safe}.svg")


def list_preview_rows() -> list[dict]:
    rows: list[dict] = []
    for key in sorted(DEFAULT_ICON_REGISTRY.keys()):
        spec = get_icon(key)
        default = DEFAULT_ICON_REGISTRY[key]
        has_candidate = candidate_exists(key)
        slug = slug_for_key(key)
        rows.append(
            {
                "key": key,
                "label": spec["label"],
                "group": spec["group"],
                "current_kind": spec["kind"],
                "current_value": spec["value"],
                "default_kind": default["kind"],
                "default_value": default["value"],
                "has_candidate": has_candidate,
                "candidate_url": candidate_static_url(key) if has_candidate else "",
                "hugeicons_slug": slug,
                "hugeicons_url": icon_page_url(slug) if slug else "",
                "hugeicons_html": str(render_hugeicons_html(slug)) if slug else "",
            }
        )
    return rows


def candidates_count() -> int:
    return sum(1 for key in DEFAULT_ICON_REGISTRY if candidate_exists(key))


SITE_ICONS_DIR = Path(settings.BASE_DIR) / "static" / "icons" / "site"


def apply_all_candidates() -> int:
    import shutil

    from biota_shifts.icon_settings import get_effective_overrides, save_icon_settings

    SITE_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    overrides = dict(get_effective_overrides())
    applied = 0
    for key in DEFAULT_ICON_REGISTRY:
        src = _candidate_path(key)
        if not src.is_file():
            continue
        safe = key.replace("/", "_")
        dest = SITE_ICONS_DIR / f"{safe}.svg"
        shutil.copy2(src, dest)
        overrides[key] = {"kind": "svg_static", "value": f"icons/site/{safe}.svg"}
        applied += 1
    save_icon_settings(overrides)
    return applied


def figma_inventory() -> list[dict]:
    """Подсказки для страницы Figma «Новые иконки» (Hugeicons Stroke Rounded)."""
    hints = {
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
        "action.delete": "delete-02",
        "action.quick_edit": "edit-01",
        "action.quick_edit_save": "floppy-disk",
        "setup.load_to_machine": "upload-01",
        "setup.tool_note_view": "view",
        "nav.calculator": "calculator-01",
        "pdf.export_specs": "file-01",
        "pdf.export_photos": "grid-view",
        "ui.close": "cancel-01",
        "ui.lock": "square-lock-01",
        "ui.unlock": "square-unlock-01",
        "ui.refresh": "refresh-01",
    }
    rows = list_preview_rows()
    for row in rows:
        row["figma_hint"] = hints.get(row["key"], HUGICONS_STROKE_ROUNDED.get(row["key"], row["label"]))
    return rows

