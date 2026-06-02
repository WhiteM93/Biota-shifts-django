"""Подтверждение email при регистрации (письмо со ссылкой)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from biota_shifts.auth import (
    _find_username_by_email,
    _load_users_store,
    _normalize_email,
    _resolve_registered_user,
    _save_users_store,
)
from biota_shifts.config import _config_str
from biota_shifts.constants import MSK

logger = logging.getLogger(__name__)

VERIFY_TOKEN_TTL_HOURS = 48


def email_uses_console_backend() -> bool:
    """True — письма не уходят в интернет, только в лог/консоль Django."""
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    return "console" in backend
RESEND_COOLDOWN_MINUTES = 2


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _site_base_url(request=None) -> str:
    if request is not None:
        try:
            return request.build_absolute_uri("/").rstrip("/")
        except Exception:
            pass
    explicit = (_config_str("BIOTA_SITE_URL", "") or getattr(settings, "BIOTA_SITE_URL", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    return "http://127.0.0.1:8000"


def email_verification_required(rec: dict | None) -> bool:
    if not rec:
        return False
    return bool(_normalize_email(rec.get("email") or ""))


def email_is_verified(rec: dict | None) -> bool:
    if not rec:
        return True
    if not email_verification_required(rec):
        return True
    return bool(rec.get("email_verified", True))


def login_block_reason(rec: dict | None) -> str | None:
    """None — вход разрешён (по email/approved); иначе код причины."""
    if not rec:
        return "not_found"
    if email_verification_required(rec) and not email_is_verified(rec):
        return "email_unverified"
    if not rec.get("approved", True):
        return "admin_pending"
    return None


def _find_username_by_token(token: str) -> str | None:
    th = _token_hash(token)
    store = _load_users_store()
    for login, rec in store.items():
        if (rec.get("email_verify_token_hash") or "") == th:
            return str(login)
    return None


def verify_email_token(token: str) -> tuple[bool, str]:
    raw = (token or "").strip()
    if not raw or len(raw) < 20:
        return False, "Некорректная или устаревшая ссылка."
    login = _find_username_by_token(raw)
    if not login:
        return False, "Ссылка недействительна или уже использована."
    store = _load_users_store()
    rec = store.get(login)
    if not rec:
        return False, "Учётная запись не найдена."
    exp = (rec.get("email_verify_expires_at") or "").strip()
    if exp:
        try:
            exp_dt = datetime.strptime(exp, "%Y-%m-%d %H:%M")
            if datetime.now(MSK).replace(tzinfo=None) > exp_dt:
                return False, "Срок действия ссылки истёк. Запросите новое письмо на странице входа."
        except ValueError:
            pass
    rec["email_verified"] = True
    rec["email_verified_at"] = datetime.now(MSK).strftime("%Y-%m-%d %H:%M")
    rec["email_verify_token_hash"] = ""
    rec["email_verify_expires_at"] = ""
    store[login] = rec
    _save_users_store(store)
    return True, ""


def _can_resend(rec: dict) -> tuple[bool, str]:
    sent = (rec.get("email_verify_sent_at") or "").strip()
    if not sent:
        return True, ""
    try:
        sent_dt = datetime.strptime(sent, "%Y-%m-%d %H:%M")
    except ValueError:
        return True, ""
    delta = datetime.now(MSK).replace(tzinfo=None) - sent_dt
    if delta < timedelta(minutes=RESEND_COOLDOWN_MINUTES):
        wait = RESEND_COOLDOWN_MINUTES - int(delta.total_seconds() // 60)
        return False, f"Повторная отправка будет доступна через {max(1, wait)} мин."
    return True, ""


def send_verification_email(username: str, request=None) -> tuple[bool, str, str]:
    login = (username or "").strip()
    if not login:
        return False, "Не указан логин.", ""
    store = _load_users_store()
    if login not in store:
        ul = login.casefold()
        for k in store:
            if str(k).strip().casefold() == ul:
                login = str(k)
                break
    rec = store.get(login)
    if not rec:
        return False, "Пользователь не найден.", ""
    if not email_verification_required(rec):
        return False, "Для этой учётной записи подтверждение email не требуется.", ""
    if email_is_verified(rec):
        return False, "Email уже подтверждён.", ""

    ok_resend, resend_err = _can_resend(rec)
    if not ok_resend:
        return False, resend_err, ""

    token = secrets.token_urlsafe(32)
    expires = datetime.now(MSK) + timedelta(hours=VERIFY_TOKEN_TTL_HOURS)
    rec["email_verify_token_hash"] = _token_hash(token)
    rec["email_verify_expires_at"] = expires.strftime("%Y-%m-%d %H:%M")
    rec["email_verify_sent_at"] = datetime.now(MSK).strftime("%Y-%m-%d %H:%M")
    store[login] = rec
    _save_users_store(store)

    path = reverse("verify_email", kwargs={"token": token})
    link = f"{_site_base_url(request)}{path}"
    em_to = _normalize_email(rec.get("email") or "")
    subject = "Подтверждение регистрации — Biota"
    body = (
        f"Здравствуйте!\n\n"
        f"Вы зарегистрировались в системе Biota (логин: {login}).\n"
        f"Подтвердите адрес email, перейдя по ссылке (действует {VERIFY_TOKEN_TTL_HOURS} ч.):\n\n"
        f"{link}\n\n"
        f"Если вы не регистрировались — проигнорируйте это письмо.\n"
        f"После подтверждения email администратор всё ещё должен одобрить учётную запись для входа.\n"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"

    try:
        send_mail(
            subject,
            body,
            from_email,
            [em_to],
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("verify email send failed for %s", login)
        return False, f"Не удалось отправить письмо: {exc}", ""

    if settings.DEBUG or email_uses_console_backend():
        logger.info("Email verification link for %s: %s", login, link)

    return True, "", ""


def send_verification_by_email_address(email: str, request=None) -> tuple[bool, str]:
    ok, em_or_err = _validate_email_format_public(email)
    if not ok:
        return False, em_or_err
    login = _find_username_by_email(em_or_err)
    if not login:
        return True, ""
    sent_ok, err, _link = send_verification_email(login, request=request)
    return sent_ok, err


def _validate_email_format_public(email: str) -> tuple[bool, str]:
    from biota_shifts.auth import _validate_email_format

    return _validate_email_format(email)
