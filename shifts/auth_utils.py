"""Авторизация Biota (сессия Django, те же пароли что и в Streamlit)."""
from functools import wraps
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from biota_shifts.auth import _is_admin, _resolve_registered_user


def biota_user(request):
    return (request.session.get("biota_username") or "").strip() or None


def biota_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        u = biota_user(request)
        if not u:
            next_url = quote(request.get_full_path(), safe="/")
            return redirect(f"{settings.LOGIN_URL}?next={next_url}")
        if not _is_admin(u):
            rec = _resolve_registered_user(u)
            if not rec or not rec.get("approved", True):
                request.session.flush()
                messages.warning(
                    request,
                    "Вход невозможен: учётная запись ожидает подтверждения администратором или удалена.",
                )
                return redirect(f"{settings.LOGIN_URL}?next={quote(request.get_full_path(), safe='/')}")
        return view_func(request, *args, **kwargs)

    return _wrapped
