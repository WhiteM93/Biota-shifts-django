"""Антибот для публичной регистрации: invite, honeypot, тайминг, disposable email."""

from __future__ import annotations

import secrets
import time
from typing import Any

from django.conf import settings

SESSION_ISSUED_AT = "register_form_issued_at"
HONEYPOT_FIELD = "website"
MIN_FILL_SECONDS = 3
MAX_FILL_SECONDS = 2 * 60 * 60

# Популярные одноразовые домены (нижний регистр).
_DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamailblock.com",
        "sharklasers.com",
        "grr.la",
        "guerrillamail.info",
        "guerrillamail.net",
        "guerrillamail.org",
        "tempmail.com",
        "temp-mail.org",
        "temp-mail.io",
        "10minutemail.com",
        "10minutemail.net",
        "yopmail.com",
        "trashmail.com",
        "trashmail.me",
        "dispostable.com",
        "mailnesia.com",
        "maildrop.cc",
        "getnada.com",
        "nada.email",
        "throwaway.email",
        "fakeinbox.com",
        "emailondeck.com",
        "mintemail.com",
        "moakt.com",
        "tempail.com",
        "tmpmail.org",
        "tmpmail.net",
        "trash-mail.com",
        "mytemp.email",
        "mailcatch.com",
        "spamgourmet.com",
        "getairmail.com",
        "mailnull.com",
        "spam4.me",
        "bccto.me",
        "chacuo.net",
        "discard.email",
        "discardmail.com",
        "mailnesia.com",
        "mailinator.net",
        "mailinator.org",
        "tempr.email",
        "emailfake.com",
        "crazymailing.com",
        "inboxkitten.com",
        "harakirimail.com",
    }
)

GENERIC_FAIL = "Не удалось зарегистрироваться. Обновите страницу и попробуйте снова."
CLOSED_MSG = "Регистрация временно закрыта."
INVITE_FAIL = "Неверный код приглашения."
DISPOSABLE_FAIL = "Укажите обычный рабочий email (одноразовые адреса не принимаются)."


def invite_code_configured() -> str:
    return (getattr(settings, "BIOTA_REGISTER_INVITE_CODE", "") or "").strip()


def registration_is_open() -> bool:
    return bool(invite_code_configured())


def mark_form_issued(request) -> None:
    request.session[SESSION_ISSUED_AT] = time.time()


def _extra_disposable_domains() -> set[str]:
    raw = (getattr(settings, "BIOTA_DISPOSABLE_EMAIL_DOMAINS", "") or "").strip()
    if not raw:
        return set()
    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        d = part.strip().casefold()
        if d:
            out.add(d)
    return out


def is_disposable_email(email: str) -> bool:
    em = (email or "").strip().casefold()
    if "@" not in em:
        return False
    domain = em.rsplit("@", 1)[-1].strip()
    if not domain:
        return False
    blocked = _DISPOSABLE_DOMAINS | _extra_disposable_domains()
    if domain in blocked:
        return True
    # поддомены: foo.mailinator.com
    for d in blocked:
        if domain.endswith("." + d):
            return True
    return False


def invite_code_ok(posted: str) -> bool:
    expected = invite_code_configured()
    if not expected:
        return False
    got = (posted or "").strip()
    if not got:
        return False
    # compare_digest требует одинаковой длины — нормализуем через hmac-подобное сравнение
    try:
        return secrets.compare_digest(got, expected)
    except (TypeError, ValueError):
        return False


def check_bot_traps(request) -> tuple[str | None, str | None]:
    """
    (сообщение, reason) — None/None если ок.
    reason: honeypot | timing
    """
    if (request.POST.get(HONEYPOT_FIELD) or "").strip():
        return GENERIC_FAIL, "honeypot"

    issued = request.session.get(SESSION_ISSUED_AT)
    try:
        issued_f = float(issued)
    except (TypeError, ValueError):
        return GENERIC_FAIL, "timing"

    elapsed = time.time() - issued_f
    if elapsed < MIN_FILL_SECONDS or elapsed > MAX_FILL_SECONDS:
        return GENERIC_FAIL, "timing"
    return None, None


def validate_register_post(request, *, invite_posted: str, email: str) -> str | None:
    """Проверки до _register_user. None — можно продолжать."""
    msg, _reason = validate_register_post_detailed(request, invite_posted=invite_posted, email=email)
    return msg


def validate_register_post_detailed(
    request, *, invite_posted: str, email: str
) -> tuple[str | None, str | None]:
    """(сообщение|None, reason|None). reason для журнала безопасности."""
    if not registration_is_open():
        return CLOSED_MSG, "closed"
    trap_msg, trap_reason = check_bot_traps(request)
    if trap_msg:
        return trap_msg, trap_reason
    if not invite_code_ok(invite_posted):
        return INVITE_FAIL, "invite"
    if is_disposable_email(email):
        return DISPOSABLE_FAIL, "disposable"
    return None, None


def register_page_context_extra() -> dict[str, Any]:
    open_ = registration_is_open()
    return {
        "register_open": open_,
        "register_closed_message": CLOSED_MSG if not open_ else "",
        "honeypot_field": HONEYPOT_FIELD,
    }
