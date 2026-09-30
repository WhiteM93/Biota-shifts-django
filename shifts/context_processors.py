from biota_shifts.auth import (
    NAV_KEYS,
    account_label_for_username,
    machines_quick_edit_for_user,
    nav_permissions_for_user,
)
from shifts.auth_utils import (
    can_preview_role,
    inventory_stock_manage_for_user,
    is_real_admin,
    preview_role,
    request_can_edit,
    request_is_admin_ui,
    request_is_executor,
)
from shifts.site_updates import effective_site_updates_seen_id, unread_site_updates_count
from shifts.site_updates_views import SITE_UPDATES_SEEN_SESSION_KEY

_NON_WAREHOUSE_PANELS = frozenset({"defects", "payroll", "employees"})


def _site_updates_unread(request) -> int:
    try:
        url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
        if url_name == "site_updates":
            return 0
        u = (request.session.get("biota_username") or "").strip()
        session_seen = int(request.session.get(SITE_UPDATES_SEEN_SESSION_KEY) or 0)
        seen = effective_site_updates_seen_id(u, session_seen)
        return unread_site_updates_count(seen)
    except Exception:
        return 0


def _stock_addr_fab_context(request, *, username: str) -> dict:
    """Кнопка «Адреса» на всех вкладках склада и на визуальном складе."""
    empty = {
        "show_stock_addr_fab": False,
        "stock_address_hints": [],
        "stock_address_furniture": [],
        "can_manage_stock": False,
    }
    try:
        url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
        panel = (request.GET.get("panel") or "").strip()
        if url_name == "visual_warehouse":
            show = True
            include_stock = True
        elif url_name == "inventory":
            if not panel:
                panel = "stock"
            if panel in _NON_WAREHOUSE_PANELS:
                return empty
            show = True
            include_stock = panel != "arrival"
        else:
            return empty
        if not show:
            return empty

        from shifts.visual_warehouse_address import build_address_hint_rows

        hints = build_address_hint_rows(include_stock=include_stock)
        furniture = []
        seen: set[int] = set()
        for row in hints:
            try:
                fid = int(row.get("furniture_id") or 0)
            except (TypeError, ValueError):
                fid = 0
            if fid <= 0 or fid in seen:
                continue
            seen.add(fid)
            furniture.append(
                {
                    "id": fid,
                    "code": (row.get("furniture_code") or "").strip(),
                    "name": (row.get("furniture") or "").strip() or f"Мебель {fid}",
                }
            )
        furniture.sort(key=lambda x: ((x.get("code") or ""), (x.get("name") or "").casefold()))

        is_admin_user = request_is_admin_ui(request)
        can_manage = is_admin_user or (
            inventory_stock_manage_for_user(username) and not is_real_admin(request)
        )
        return {
            "show_stock_addr_fab": True,
            "stock_address_hints": hints,
            "stock_address_furniture": furniture,
            "can_manage_stock": can_manage,
        }
    except Exception:
        return empty


def biota_session(request):
    """В шапке: имя/фамилия аккаунта, если заданы; для admin — имя из сессии."""
    try:
        from django.conf import settings

        static_asset_version = getattr(settings, "STATIC_ASSET_VERSION", "1")
        perf_defer_scripts = getattr(settings, "BIOTA_PERF_DEFER_SCRIPTS", False)
        perf_diagnostics = getattr(settings, "BIOTA_PERF_DIAGNOSTICS", False)
        perf_diag_ttfb_ms = getattr(settings, "BIOTA_PERF_DIAG_TTFB_MS", 2500)
        perf_diag_load_ms = getattr(settings, "BIOTA_PERF_DIAG_LOAD_MS", 5000)
    except Exception:
        static_asset_version = "1"
        perf_defer_scripts = False
        perf_diagnostics = False
        perf_diag_ttfb_ms = 2500
        perf_diag_load_ms = 5000
    try:
        from biota_shifts.icon_settings import get_icon_preset
        from biota_shifts.icons import icons_json_for_template

        icons_json = icons_json_for_template()
        icon_preset = get_icon_preset()
    except Exception:
        icons_json = "{}"
        icon_preset = "default"
    icon_ctx = {
        "icon_preset": icon_preset,
        "icon_preset_is_hugeicons": icon_preset == "hugeicons",
    }
    u = (request.session.get("biota_username") or "").strip()
    if not u:
        return {
            "biota_username": "",
            "biota_nav": {k: True for k in NAV_KEYS},
            "biota_is_executor": False,
            "biota_can_edit": True,
            "biota_is_admin": False,
            "biota_is_real_admin": False,
            "biota_can_preview_role": False,
            "biota_preview_role": "",
            "site_updates_unread": 0,
            "biota_machines_quick_edit": False,
            "static_asset_version": static_asset_version,
            "perf_defer_scripts": perf_defer_scripts,
            "perf_diagnostics": perf_diagnostics,
            "perf_diag_ttfb_ms": perf_diag_ttfb_ms,
            "perf_diag_load_ms": perf_diag_load_ms,
            "biota_icons_json": icons_json,
            "show_stock_addr_fab": False,
            "stock_address_hints": [],
            "stock_address_furniture": [],
            "can_manage_stock": False,
            **icon_ctx,
        }
    nav = nav_permissions_for_user(u)
    adn = (request.session.get("admin_display_name") or "").strip()
    real_admin = is_real_admin(request)
    is_executor = request_is_executor(request)
    payload = {
        "biota_nav": nav,
        "biota_is_executor": is_executor,
        "biota_can_edit": request_can_edit(request),
        "biota_is_admin": request_is_admin_ui(request),
        "biota_is_real_admin": real_admin,
        "biota_can_preview_role": can_preview_role(request),
        "biota_preview_role": preview_role(request) or "",
        "biota_machines_quick_edit": machines_quick_edit_for_user(u) and not is_executor,
        "site_updates_unread": _site_updates_unread(request),
    }
    payload["static_asset_version"] = static_asset_version
    payload["perf_defer_scripts"] = perf_defer_scripts
    payload["perf_diagnostics"] = perf_diagnostics
    payload["perf_diag_ttfb_ms"] = perf_diag_ttfb_ms
    payload["perf_diag_load_ms"] = perf_diag_load_ms
    if real_admin and adn:
        display = adn
    else:
        try:
            display = account_label_for_username(u) or u
        except Exception:
            display = u
    addr_fab = (
        _stock_addr_fab_context(request, username=u)
        if nav.get("inventory")
        else {
            "show_stock_addr_fab": False,
            "stock_address_hints": [],
            "stock_address_furniture": [],
            "can_manage_stock": False,
        }
    )
    return {
        "biota_username": display,
        **payload,
        "biota_icons_json": icons_json,
        **icon_ctx,
        **addr_fab,
    }
