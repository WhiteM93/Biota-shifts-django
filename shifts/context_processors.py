def biota_session(request):
    return {"biota_username": (request.session.get("biota_username") or "").strip()}
