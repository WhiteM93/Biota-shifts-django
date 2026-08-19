from biota_shifts.auth import (
    NAV_KEYS,
    _is_admin,
    machines_quick_edit_for_user,
    nav_permissions_for_user,
    user_is_executor,
)


def biota_session(request):
    """В шапке: для admin — «имя для отображения» из сессии, если задано (как в Streamlit)."""
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
            "biota_machines_quick_edit": False,
            "static_asset_version": static_asset_version,
            "perf_defer_scripts": perf_defer_scripts,
            "perf_diagnostics": perf_diagnostics,
            "perf_diag_ttfb_ms": perf_diag_ttfb_ms,
            "perf_diag_load_ms": perf_diag_load_ms,
            "biota_icons_json": icons_json,
            **icon_ctx,
        }
    nav = nav_permissions_for_user(u)
    adn = (request.session.get("admin_display_name") or "").strip()
    is_admin = _is_admin(u)
    is_executor = user_is_executor(u) and not is_admin
    payload = {
        "biota_nav": nav,
        "biota_is_executor": is_executor,
        "biota_can_edit": is_admin or not is_executor,
        "biota_is_admin": is_admin,
        "biota_machines_quick_edit": machines_quick_edit_for_user(u),
    }
    payload["static_asset_version"] = static_asset_version
    payload["perf_defer_scripts"] = perf_defer_scripts
    payload["perf_diagnostics"] = perf_diagnostics
    payload["perf_diag_ttfb_ms"] = perf_diag_ttfb_ms
    payload["perf_diag_load_ms"] = perf_diag_load_ms
    display = adn if (is_admin and adn) else u
    return {
        "biota_username": display,
        **payload,
        "biota_icons_json": icons_json,
        **icon_ctx,
    }
