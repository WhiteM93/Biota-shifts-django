from biota_shifts.auth import _is_admin


def biota_session(request):
    """В шапке: для admin — «имя для отображения» из сессии, если задано (как в Streamlit)."""
    u = (request.session.get("biota_username") or "").strip()
    if not u:
        return {"biota_username": ""}
    adn = (request.session.get("admin_display_name") or "").strip()
    if _is_admin(u) and adn:
        return {"biota_username": adn}
    return {"biota_username": u}
