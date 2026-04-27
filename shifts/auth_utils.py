"""Авторизация Biota (сессия Django, те же пароли что и в Streamlit)."""
from functools import wraps
from urllib.parse import parse_qs, quote, urlparse

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import NoReverseMatch, resolve, reverse

from biota_shifts.auth import (
    NAV_KEYS,
    _is_admin,
    _resolve_registered_user,
    nav_permissions_for_user,
    user_is_executor,
)


def biota_user(request):
    return (request.session.get("biota_username") or "").strip() or None


def _nav_key_for_url_name(url_name: str) -> str | None:
    n = (url_name or "").strip()
    if not n:
        return None
    if n == "home":
        return "home"
    if n.startswith("graph"):
        return "graph"
    if n.startswith("hours"):
        return "hours"
    if n.startswith("skud"):
        return "skud"
    if n == "inventory":
        return "inventory"
    if n.startswith("regulations"):
        return "regulations"
    if n.startswith("product"):
        return "products"
    return None


def _nav_key_for_internal_path(path: str, query: str) -> str | None:
    p = (path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    try:
        match = resolve(p)
    except Exception:
        return None
    key = _nav_key_for_url_name(match.url_name)
    if key == "inventory":
        q = parse_qs(query or "")
        panel_vals = [x for x in (q.get("panel") or []) if x]
        panel = (panel_vals[0] or "").strip() if panel_vals else ""
        if panel == "defects":
            return "defects"
        return "inventory"
    return key


def post_login_redirect(username: str | None, next_path: str | None = None) -> str:
    """Куда отправить пользователя после входа / при отказе в nav-правах (если «Главная» выключена — не зацикливаться на /home/)."""
    u = (username or "").strip()
    perms = nav_permissions_for_user(u) if u else {k: True for k in NAV_KEYS}

    if next_path:
        raw = str(next_path).strip()
        if raw.startswith("/") and not raw.startswith("//"):
            parsed = urlparse(raw)
            nk = _nav_key_for_internal_path(parsed.path, parsed.query)
            if nk is None or perms.get(nk, True):
                return raw

    order = ("home", "graph", "hours", "skud", "inventory", "defects", "regulations", "products")
    for k in order:
        if not perms.get(k, True):
            continue
        try:
            if k == "defects":
                return f"{reverse('inventory')}?panel=defects"
            return reverse(k)
        except NoReverseMatch:
            continue
    return reverse("cabinet")


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


def nav_permission_required(nav_key: str):
    """После biota_login_required: доступ к разделу по полю users.*.nav (админ — всегда да)."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            u = biota_user(request)
            if not u:
                next_url = quote(request.get_full_path(), safe="/")
                return redirect(f"{settings.LOGIN_URL}?next={next_url}")
            if not nav_permissions_for_user(u).get(nav_key, True):
                messages.warning(request, "У вас нет доступа к этому разделу.")
                return redirect(post_login_redirect(u))
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def write_permission_required(view_func):
    """Блокирует изменения для роли executor: только просмотр и скачивание."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        u = biota_user(request)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not _is_admin(u) and user_is_executor(u):
            messages.warning(
                request,
                "У вас роль «исполнитель»: доступны только просмотр и скачивание.",
            )
            return redirect(request.META.get("HTTP_REFERER") or post_login_redirect(u))
        return view_func(request, *args, **kwargs)

    return _wrapped
