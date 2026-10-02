"""Вход по QR: компьютер показывает код, телефон подтверждает сессию."""
from __future__ import annotations

import secrets
import time
from typing import Any

from django.core.cache import caches
from django.http import HttpRequest
from django.urls import reverse

from biota_shifts.auth import ADMIN_USERNAME, _is_admin, _resolve_registered_user
from shifts.email_verification import login_block_reason
from shifts.setup_share import qr_svg_markup, setup_url_is_localhost

QR_TTL_SEC = 240
_CACHE_ALIAS = "qrlogin"
_KEY_PREFIX = "biota_qr_login:"


def _cache():
    return caches[_CACHE_ALIAS]


def _key(token: str) -> str:
    return f"{_KEY_PREFIX}{(token or '').strip()}"


def create_qr_login_token(request: HttpRequest, *, next_url: str = "") -> dict[str, Any]:
    """Создать pending-токен, привязанный к сессии браузера на компьютере."""
    if not request.session.session_key:
        request.session.save()
    token = secrets.token_urlsafe(24)
    payload = {
        "status": "pending",
        "desktop_session_key": request.session.session_key,
        "next": (next_url or "").strip()[:500],
        "username": "",
        "created": time.time(),
    }
    _cache().set(_key(token), payload, timeout=QR_TTL_SEC)
    path = reverse("qr_login_confirm", kwargs={"token": token})
    url = request.build_absolute_uri(path)
    return {
        "token": token,
        "url": url,
        "qr_svg": qr_svg_markup(url),
        "expires_in": QR_TTL_SEC,
        "is_localhost": setup_url_is_localhost(url),
    }


def get_qr_login(token: str) -> dict[str, Any] | None:
    raw = _cache().get(_key(token))
    if not isinstance(raw, dict):
        return None
    created = float(raw.get("created") or 0)
    if created and (time.time() - created) > QR_TTL_SEC:
        _cache().delete(_key(token))
        return None
    return raw


def approve_qr_login(token: str, username: str) -> tuple[bool, str]:
    """Телефон подтвердил вход под username."""
    data = get_qr_login(token)
    if not data:
        return False, "Код устарел или не найден. Обновите QR на компьютере."
    status = (data.get("status") or "").strip()
    if status == "consumed":
        return False, "Этот код уже использован."
    if status == "approved":
        return True, "Вход уже подтверждён — подождите на компьютере."
    if status != "pending":
        return False, "Код недоступен."

    user = (username or "").strip()
    if not user:
        return False, "Не указан пользователь."
    if not _is_admin(user):
        rec = _resolve_registered_user(user)
        block = login_block_reason(rec)
        if block == "email_unverified":
            return False, "Сначала подтвердите email."
        if block == "admin_pending" or not rec:
            return False, "Учётная запись ещё не одобрена администратором."
        if block:
            return False, "Вход временно недоступен для этой учётной записи."
        data["username"] = user
    else:
        data["username"] = ADMIN_USERNAME

    data["status"] = "approved"
    data["approved_at"] = time.time()
    left = max(30, QR_TTL_SEC - int(time.time() - float(data.get("created") or time.time())))
    _cache().set(_key(token), data, timeout=left)
    return True, "Готово. На компьютере откроется сайт."


def claim_qr_login(request: HttpRequest, token: str) -> tuple[bool, str, str]:
    """
    Компьютер забирает подтверждённый вход в свою сессию.
    Returns (ok, error_or_empty, redirect_path).
    """
    from shifts.auth_utils import post_login_redirect

    data = get_qr_login(token)
    if not data:
        return False, "Код устарел. Обновите страницу входа.", ""
    if data.get("desktop_session_key") != request.session.session_key:
        return False, "Этот QR принадлежит другой вкладке браузера.", ""
    status = (data.get("status") or "").strip()
    if status == "pending":
        return False, "", ""  # ещё ждём — не ошибка
    if status == "consumed":
        return False, "Код уже использован.", ""
    if status != "approved":
        return False, "Код недоступен.", ""
    username = (data.get("username") or "").strip()
    if not username:
        return False, "Подтверждение без пользователя.", ""

    data["status"] = "consumed"
    _cache().set(_key(token), data, timeout=60)
    request.session["biota_username"] = username
    request.session.set_expiry(0)
    next_url = (data.get("next") or "").strip()
    return True, "", post_login_redirect(username, next_url)
