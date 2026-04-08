"""Авторизация Biota (сессия Django, те же пароли что и в Streamlit)."""
from functools import wraps
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect


def biota_user(request):
    return (request.session.get("biota_username") or "").strip() or None


def biota_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not biota_user(request):
            next_url = quote(request.get_full_path(), safe="/")
            return redirect(f"{settings.LOGIN_URL}?next={next_url}")
        return view_func(request, *args, **kwargs)

    return _wrapped
