from biota_shifts.auth import NAV_KEYS, _is_admin, nav_permissions_for_user


def biota_session(request):
    """В шапке: для admin — «имя для отображения» из сессии, если задано (как в Streamlit)."""
    u = (request.session.get("biota_username") or "").strip()
    if not u:
        return {"biota_username": "", "biota_nav": {k: True for k in NAV_KEYS}}
    nav = nav_permissions_for_user(u)
    adn = (request.session.get("admin_display_name") or "").strip()
    if _is_admin(u) and adn:
        return {"biota_username": adn, "biota_nav": nav}
    return {"biota_username": u, "biota_nav": nav}
