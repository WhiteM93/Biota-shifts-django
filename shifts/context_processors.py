from biota_shifts.auth import NAV_KEYS, _is_admin, nav_permissions_for_user, user_is_executor


def biota_session(request):
    """В шапке: для admin — «имя для отображения» из сессии, если задано (как в Streamlit)."""
    u = (request.session.get("biota_username") or "").strip()
    if not u:
        return {"biota_username": "", "biota_nav": {k: True for k in NAV_KEYS}, "biota_is_executor": False, "biota_can_edit": True}
    nav = nav_permissions_for_user(u)
    adn = (request.session.get("admin_display_name") or "").strip()
    is_admin = _is_admin(u)
    is_executor = user_is_executor(u) and not is_admin
    payload = {"biota_nav": nav, "biota_is_executor": is_executor, "biota_can_edit": is_admin or not is_executor}
    if is_admin and adn:
        return {"biota_username": adn, **payload}
    return {"biota_username": u, **payload}
