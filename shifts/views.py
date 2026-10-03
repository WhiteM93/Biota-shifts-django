from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts import db as biota_db
from biota_shifts.auth import (
    ADMIN_USERNAME,
    USER_ROLE_CHOICES,
    _credentials_match,
    _is_admin,
    _register_user,
    _resolve_registered_user,
)

from .auth_utils import (
    PREVIEW_ROLE_SESSION_KEY,
    biota_login_required,
    biota_user,
    can_preview_role,
    is_real_admin,
    post_login_redirect,
    request_can_edit,
    request_is_executor,
    write_permission_required,
)
from .email_verification import (
    email_uses_console_backend,
    login_block_reason,
    send_verification_email,
    verify_email_token,
)


@require_http_methods(["GET", "HEAD", "POST"])
def login_view(request):
    from .qr_login import create_qr_login_token

    u0 = biota_user(request)
    if u0:
        return redirect(post_login_redirect(u0))
    err = ""
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    remember_me = request.method == "POST" and request.POST.get("remember_me") == "1"
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        if _credentials_match(username, password):
            if not _is_admin(username):
                rec = _resolve_registered_user(username)
                block = login_block_reason(rec)
                if block == "email_unverified":
                    err = (
                        "Подтвердите email по ссылке из письма. "
                        "Если письма нет — запросите повторную отправку ниже."
                    )
                elif block == "admin_pending" or not rec:
                    err = (
                        "Учётная запись ожидает подтверждения администратором. "
                        "После подтверждения email и одобрения администратора вы сможете войти."
                    )
                elif block:
                    err = "Вход временно недоступен для этой учётной записи."
                else:
                    request.session["biota_username"] = username
                    if remember_me:
                        request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
                    else:
                        request.session.set_expiry(0)  # browser session only
                    return redirect(post_login_redirect(username, next_url))
            else:
                request.session["biota_username"] = ADMIN_USERNAME
                if remember_me:
                    request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
                else:
                    request.session.set_expiry(0)  # browser session only
                return redirect(post_login_redirect(ADMIN_USERNAME, next_url))
        if not err:
            err = "Неверный логин или пароль"
    qr = create_qr_login_token(request, next_url=next_url)
    return render(
        request,
        "shifts/login.html",
        {
            "error": err,
            "next_url": next_url,
            "remember_me": remember_me,
            "hide_nav": True,
            "auth_page": True,
            "qr_token": qr.get("token") or "",
            "qr_svg": qr.get("qr_svg") or "",
            "qr_url": qr.get("url") or "",
            "qr_is_localhost": bool(qr.get("is_localhost")),
            "qr_status_url": reverse("qr_login_status"),
        },
    )


@require_http_methods(["GET"])
def qr_login_status_view(request):
    """Polling с компьютера: ждёт подтверждения с телефона."""
    from .qr_login import claim_qr_login, create_qr_login_token, get_qr_login

    if biota_user(request):
        return JsonResponse({"ok": True, "status": "logged_in", "redirect": post_login_redirect(biota_user(request))})

    token = (request.GET.get("token") or "").strip()
    if not token:
        return JsonResponse({"ok": False, "error": "Нет токена"}, status=400)
    data = get_qr_login(token)
    if not data:
        fresh = create_qr_login_token(request, next_url=request.GET.get("next") or "")
        return JsonResponse(
            {
                "ok": True,
                "status": "expired",
                "token": fresh.get("token") or "",
                "qr_svg": fresh.get("qr_svg") or "",
                "url": fresh.get("url") or "",
                "is_localhost": bool(fresh.get("is_localhost")),
            }
        )
    status = (data.get("status") or "pending").strip()
    if status == "pending":
        return JsonResponse({"ok": True, "status": "pending"})
    if status == "approved":
        ok, err, redirect_to = claim_qr_login(request, token)
        if ok:
            return JsonResponse({"ok": True, "status": "ready", "redirect": redirect_to or "/"})
        if not err:
            return JsonResponse({"ok": True, "status": "pending"})
        return JsonResponse({"ok": False, "status": "error", "error": err})
    return JsonResponse({"ok": True, "status": status})


@require_http_methods(["GET", "HEAD", "POST"])
def qr_login_confirm_view(request, token: str):
    """Страница на телефоне после сканирования QR."""
    from .qr_login import approve_qr_login, get_qr_login

    tok = (token or "").strip()
    data = get_qr_login(tok)
    if not data:
        return render(
            request,
            "shifts/qr_login_confirm.html",
            {
                "hide_nav": True,
                "auth_page": True,
                "expired": True,
                "error": "Код устарел или не найден. Обновите QR на компьютере и отсканируйте снова.",
            },
        )

    status = (data.get("status") or "").strip()
    if status in ("approved", "consumed"):
        return render(
            request,
            "shifts/qr_login_confirm.html",
            {
                "hide_nav": True,
                "auth_page": True,
                "done": True,
                "message": "Вход подтверждён. Можно вернуться к компьютеру.",
            },
        )

    err = ""
    phone_user = biota_user(request)

    if request.method == "POST":
        action = (request.POST.get("action") or "confirm").strip()
        if action == "login":
            username = (request.POST.get("username") or "").strip()
            password = request.POST.get("password") or ""
            if not _credentials_match(username, password):
                err = "Неверный логин или пароль"
            else:
                ok, msg = approve_qr_login(tok, username)
                if ok:
                    # заодно войти на телефоне
                    if _is_admin(username):
                        request.session["biota_username"] = ADMIN_USERNAME
                    else:
                        request.session["biota_username"] = username
                    request.session.set_expiry(0)
                    return render(
                        request,
                        "shifts/qr_login_confirm.html",
                        {
                            "hide_nav": True,
                            "auth_page": True,
                            "done": True,
                            "message": msg,
                        },
                    )
                err = msg
        else:
            # confirm as already logged-in phone user
            if not phone_user:
                err = "Сначала войдите на телефоне."
            else:
                ok, msg = approve_qr_login(tok, phone_user)
                if ok:
                    return render(
                        request,
                        "shifts/qr_login_confirm.html",
                        {
                            "hide_nav": True,
                            "auth_page": True,
                            "done": True,
                            "message": msg,
                        },
                    )
                err = msg

    return render(
        request,
        "shifts/qr_login_confirm.html",
        {
            "hide_nav": True,
            "auth_page": True,
            "token": tok,
            "error": err,
            "phone_user": phone_user,
            "expired": False,
            "done": False,
        },
    )


def _register_form_context(*, err: str, form_values: dict | None = None) -> dict:
    vals = form_values or {}
    return {
        "error": err,
        "hide_nav": True,
        "auth_page": True,
        "form_username": vals.get("username", ""),
        "form_email": vals.get("email", ""),
    }


@require_http_methods(["GET", "HEAD", "POST"])
def register_view(request):
    err = ""
    form_values: dict[str, str] = {}
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip()
        p1 = request.POST.get("password") or ""
        p2 = request.POST.get("password2") or ""
        form_values = {"username": username, "email": email}
        if p1 != p2:
            err = "Пароли не совпадают"
        else:
            ok, msg = _register_user(username, p1, email=email, require_email=True)
            if ok:
                sent_ok, send_err, _debug_link = send_verification_email(username, request=request)
                request.session["register_pending_user"] = username
                request.session["register_email_sent"] = sent_ok
                request.session["register_email_error"] = "" if sent_ok else send_err
                request.session.pop("register_verify_debug_link", None)
                return redirect("register_pending")
            err = msg
    return render(
        request,
        "shifts/register.html",
        _register_form_context(err=err, form_values=form_values),
    )


@require_http_methods(["GET", "HEAD"])
def register_pending_view(request):
    username = (request.session.pop("register_pending_user", None) or "").strip()
    email_sent = request.session.pop("register_email_sent", False)
    email_error = (request.session.pop("register_email_error", None) or "").strip()
    request.session.pop("register_verify_debug_link", None)
    if not username:
        return redirect("login")
    rec = _resolve_registered_user(username)
    email_display = (rec.get("email") or "").strip() if rec else ""
    return render(
        request,
        "shifts/register_pending.html",
        {
            "hide_nav": True,
            "auth_page": True,
            "pending_username": username,
            "pending_email": email_display,
            "email_sent": email_sent,
            "email_error": email_error,
            "email_console_only": email_uses_console_backend(),
        },
    )


@require_http_methods(["GET", "HEAD"])
def verify_email_view(request, token: str):
    ok, msg = verify_email_token(token)
    return render(
        request,
        "shifts/verify_email.html",
        {
            "hide_nav": True,
            "auth_page": True,
            "verified_ok": ok,
            "message": msg if not ok else "Email подтверждён. После одобрения администратором можно войти в систему.",
        },
    )


def logout_view(request):
    request.session.flush()
    return redirect(settings.LOGIN_URL)


@biota_login_required
@require_POST
def preview_role_view(request):
    """Админ и руководители могут смотреть сайт как исполнитель, не выходя из аккаунта."""
    if not can_preview_role(request):
        messages.warning(request, "Переключение роли доступно руководителям.")
        return redirect(request.META.get("HTTP_REFERER") or post_login_redirect(biota_user(request)))
    role = (request.POST.get("role") or "").strip().lower()
    if role not in USER_ROLE_CHOICES:
        messages.warning(request, "Неизвестная роль.")
        return redirect(request.META.get("HTTP_REFERER") or "/")
    request.session[PREVIEW_ROLE_SESSION_KEY] = role
    nxt = (request.POST.get("next") or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    ref = (request.META.get("HTTP_REFERER") or "").strip()
    if ref:
        return redirect(ref)
    return redirect("/")


@biota_login_required
def home_view(request):
    """Старый адрес сводки: сразу в первый доступный раздел."""
    return redirect(post_login_redirect(biota_user(request)))


@biota_login_required
@write_permission_required
@require_POST
def refresh_db_cache(request):
    biota_db.clear_biota_db_cache()
    return redirect(request.META.get("HTTP_REFERER") or "/")


def _normalize_cutting_mode_rows(raw) -> list[dict]:
    """Ограничить и очистить строки режимов резания перед записью в общую базу."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:500]:
        if not isinstance(item, dict):
            continue
        row: dict = {}
        for k, v in item.items():
            key = str(k).strip()[:40]
            if not key:
                continue
            if v is None:
                row[key] = ""
            elif isinstance(v, bool):
                row[key] = v
            elif isinstance(v, (int, float)):
                row[key] = v
            else:
                row[key] = str(v)[:200]
        out.append(row)
    return out


def _calculator_shared_modes_payload() -> dict:
    from .models import CalculatorModesState

    row = CalculatorModesState.objects.filter(pk=1).first()
    by_mode: dict = {}
    updated_at = ""
    updated_by = ""
    if row and isinstance(row.payload, dict):
        raw_by = row.payload.get("by_mode")
        if isinstance(raw_by, dict):
            for mid, rows in raw_by.items():
                key = str(mid).strip()[:40]
                if not key:
                    continue
                by_mode[key] = _normalize_cutting_mode_rows(rows)
        updated_at = row.updated_at.strftime("%d.%m.%Y %H:%M") if row.updated_at else ""
        updated_by = (row.updated_by or "").strip()
    return {"by_mode": by_mode, "updated_at": updated_at, "updated_by": updated_by}


def _calculator_save_cutting_modes(request):
    import json as _json

    from .models import CalculatorModesState

    u = biota_user(request)
    if request_is_executor(request):
        return JsonResponse(
            {"ok": False, "error": "У вас роль «исполнитель»: изменение общей базы режимов недоступно."},
            status=403,
        )

    mode_id = ""
    rows_raw = None
    if (request.content_type or "").startswith("application/json"):
        try:
            body = _json.loads(request.body.decode("utf-8") or "{}")
        except (_json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)
        mode_id = str(body.get("mode_id") or "").strip()
        rows_raw = body.get("rows")
    else:
        mode_id = (request.POST.get("mode_id") or "").strip()
        rows_json = request.POST.get("rows_json") or "[]"
        try:
            rows_raw = _json.loads(rows_json)
        except _json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Некорректный JSON строк."}, status=400)

    if mode_id not in {"thread", "end_mill", "drill"}:
        return JsonResponse({"ok": False, "error": "Неизвестный режим."}, status=400)

    rows = _normalize_cutting_mode_rows(rows_raw)
    state, _created = CalculatorModesState.objects.get_or_create(pk=1)
    payload = state.payload if isinstance(state.payload, dict) else {}
    by_mode = payload.get("by_mode") if isinstance(payload.get("by_mode"), dict) else {}
    by_mode = dict(by_mode)
    by_mode[mode_id] = rows
    payload = {**payload, "by_mode": by_mode}
    state.payload = payload
    state.updated_by = (u or "").strip() or "?"
    state.save(update_fields=["payload", "updated_at", "updated_by"])
    return JsonResponse(
        {
            "ok": True,
            "mode_id": mode_id,
            "count": len(rows),
            "updated_at": state.updated_at.strftime("%d.%m.%Y %H:%M"),
            "updated_by": state.updated_by,
        }
    )


def _leveling_card_to_dict(card) -> dict:
    from decimal import Decimal

    def _num(v):
        if v is None:
            return None
        if isinstance(v, Decimal):
            s = format(v, "f").rstrip("0").rstrip(".")
            return s or "0"
        return str(v)

    hist = card.measurements if isinstance(card.measurements, list) else []
    wf = card.workflow if isinstance(card.workflow, dict) else {}
    feet = card.feet_positions if isinstance(card.feet_positions, list) else []
    return {
        "id": card.pk,
        "name": card.name or "",
        "serial_number": card.serial_number or "",
        "weight_kg": _num(card.weight_kg),
        "feet_count": int(card.feet_count or len(feet) or 8),
        "foot_layout": card.foot_layout or "custom",
        "bed_width_mm": int(card.bed_width_mm or 1200),
        "bed_length_mm": int(card.bed_length_mm or 2200),
        "thread_pitch_mm": _num(card.thread_pitch_mm) or "1.5",
        "table_span_x_mm": int(card.table_span_x_mm or 850),
        "table_span_y_mm": int(card.table_span_y_mm or 500),
        "feet_positions": feet,
        "workflow": wf,
        "notes": card.notes or "",
        "measurements": hist[-40:],
        "updated_by": card.updated_by or "",
        "updated_at": card.updated_at.strftime("%d.%m.%Y %H:%M") if card.updated_at else "",
    }


def _calculator_leveling_cards_payload() -> list:
    from .models import MachineLevelingCard

    return [_leveling_card_to_dict(c) for c in MachineLevelingCard.objects.all()[:200]]


def _calculator_parse_json_body(request):
    import json as _json

    if (request.content_type or "").startswith("application/json"):
        try:
            return _json.loads(request.body.decode("utf-8") or "{}")
        except (_json.JSONDecodeError, UnicodeDecodeError):
            return None
    return None


def _calculator_save_leveling_card(request):
    from decimal import Decimal, InvalidOperation

    from .models import MachineLevelingCard

    u = biota_user(request)
    if request_is_executor(request):
        return JsonResponse(
            {"ok": False, "error": "У вас роль «исполнитель»: сохранение карточки станка недоступно."},
            status=403,
        )

    body = _calculator_parse_json_body(request)
    if body is None and (request.content_type or "").startswith("application/json"):
        return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)
    src = body if isinstance(body, dict) else request.POST

    def _s(key, maxlen=120):
        return str(src.get(key) or "").strip()[:maxlen]

    def _dec(key, default=None):
        raw = str(src.get(key) or "").strip().replace(",", ".")
        if not raw:
            return default
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return default

    def _int(key, default=0):
        raw = str(src.get(key) or "").strip()
        try:
            return int(float(raw.replace(",", ".")))
        except (TypeError, ValueError):
            return default

    card_id = _int("id", 0)
    name = _s("name", 120)
    if not name:
        return JsonResponse({"ok": False, "error": "Укажите название станка."}, status=400)

    if card_id > 0:
        card = MachineLevelingCard.objects.filter(pk=card_id).first()
        if not card:
            return JsonResponse({"ok": False, "error": "Карточка не найдена."}, status=404)
    else:
        card = MachineLevelingCard()

    layout = _s("foot_layout", 16) or MachineLevelingCard.LAYOUT_CUSTOM
    if layout not in {
        MachineLevelingCard.LAYOUT_CUSTOM,
        MachineLevelingCard.LAYOUT_RECT4,
        MachineLevelingCard.LAYOUT_RECT6,
        MachineLevelingCard.LAYOUT_RECT8,
    }:
        layout = MachineLevelingCard.LAYOUT_CUSTOM

    card.name = name
    card.serial_number = _s("serial_number", 80)
    card.weight_kg = _dec("weight_kg")
    card.foot_layout = layout
    card.bed_width_mm = max(100, min(20000, _int("bed_width_mm", 1200) or 1200))
    card.bed_length_mm = max(100, min(20000, _int("bed_length_mm", 2200) or 2200))
    pitch = _dec("thread_pitch_mm", Decimal("1.50"))
    if pitch is None or pitch <= 0:
        pitch = Decimal("1.50")
    card.thread_pitch_mm = pitch
    card.table_span_x_mm = max(50, min(20000, _int("table_span_x_mm", card.bed_width_mm) or card.bed_width_mm))
    card.table_span_y_mm = max(50, min(20000, _int("table_span_y_mm", card.bed_length_mm) or card.bed_length_mm))
    card.notes = _s("notes", 400)
    card.updated_by = (u or "").strip() or "?"

    feet_raw = src.get("feet_positions")
    if isinstance(feet_raw, str):
        import json as _json

        try:
            feet_raw = _json.loads(feet_raw)
        except _json.JSONDecodeError:
            feet_raw = []
    if isinstance(feet_raw, list) and feet_raw:
        card.feet_positions = feet_raw
        card.foot_layout = MachineLevelingCard.LAYOUT_CUSTOM
    elif layout != MachineLevelingCard.LAYOUT_CUSTOM:
        card.feet_positions = MachineLevelingCard.default_feet_template(
            layout, card.bed_width_mm, card.bed_length_mm
        )
    elif not isinstance(card.feet_positions, list) or not card.feet_positions:
        card.feet_positions = MachineLevelingCard.default_feet_template(
            MachineLevelingCard.LAYOUT_RECT8, card.bed_width_mm, card.bed_length_mm
        )

    wf = src.get("workflow")
    if isinstance(wf, str):
        import json as _json

        try:
            wf = _json.loads(wf)
        except _json.JSONDecodeError:
            wf = None
    if isinstance(wf, dict):
        card.workflow = wf

    card.save()
    return JsonResponse({"ok": True, "card": _leveling_card_to_dict(card)})


def _calculator_delete_leveling_card(request):
    from .models import MachineLevelingCard

    u = biota_user(request)
    if request_is_executor(request):
        return JsonResponse(
            {"ok": False, "error": "У вас роль «исполнитель»: удаление карточки недоступно."},
            status=403,
        )

    body = _calculator_parse_json_body(request)
    src = body if isinstance(body, dict) else request.POST
    try:
        card_id = int(str(src.get("id") or "0").strip() or "0")
    except (TypeError, ValueError):
        card_id = 0
    if card_id <= 0:
        return JsonResponse({"ok": False, "error": "Не указана карточка."}, status=400)
    deleted, _ = MachineLevelingCard.objects.filter(pk=card_id).delete()
    if not deleted:
        return JsonResponse({"ok": False, "error": "Карточка не найдена."}, status=404)
    return JsonResponse({"ok": True, "id": card_id})


def _calculator_save_leveling_measurement(request):
    from datetime import datetime

    from .models import MachineLevelingCard

    u = biota_user(request)
    if request_is_executor(request):
        return JsonResponse(
            {"ok": False, "error": "У вас роль «исполнитель»: сохранение замера недоступно."},
            status=403,
        )

    body = _calculator_parse_json_body(request)
    if body is None and (request.content_type or "").startswith("application/json"):
        return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)
    src = body if isinstance(body, dict) else request.POST

    try:
        card_id = int(str(src.get("id") or "0").strip() or "0")
    except (TypeError, ValueError):
        card_id = 0
    card = MachineLevelingCard.objects.filter(pk=card_id).first() if card_id > 0 else None
    if not card:
        return JsonResponse({"ok": False, "error": "Карточка не найдена."}, status=404)

    def _f(key):
        raw = str(src.get(key) or "").strip().replace(",", ".")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    entry = {
        "kind": str(src.get("kind") or "static").strip()[:24] or "static",
        "level_x": _f("level_x"),
        "level_y": _f("level_y"),
        "fl": _f("fl"),
        "fr": _f("fr"),
        "bl": _f("bl"),
        "br": _f("br"),
        "pos_mm": _f("pos_mm"),
        "axis": str(src.get("axis") or "").strip()[:8],
        "unit": str(src.get("unit") or "mm_m").strip()[:16] or "mm_m",
        "ts": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "author": (u or "").strip() or "?",
    }
    hist = list(card.measurements) if isinstance(card.measurements, list) else []
    hist.append(entry)
    card.measurements = hist[-40:]
    card.updated_by = (u or "").strip() or "?"
    card.save(update_fields=["measurements", "updated_at", "updated_by"])
    return JsonResponse({"ok": True, "card": _leveling_card_to_dict(card)})


@biota_login_required
@require_http_methods(["GET", "POST"])
def calculator_view(request):
    from decimal import Decimal, InvalidOperation

    from .models import Product, ProductSetup, ProductSetupPieceNorm
    import json as _json

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if not action and (request.content_type or "").startswith("application/json"):
            try:
                body = _json.loads(request.body.decode("utf-8") or "{}")
                action = str(body.get("action") or "").strip()
            except (_json.JSONDecodeError, UnicodeDecodeError):
                action = ""
        if action == "save_cutting_modes":
            return _calculator_save_cutting_modes(request)
        if action == "save_leveling_card":
            return _calculator_save_leveling_card(request)
        if action == "delete_leveling_card":
            return _calculator_delete_leveling_card(request)
        if action == "save_leveling_measurement":
            return _calculator_save_leveling_measurement(request)
        if action != "save_piece_norm":
            return JsonResponse({"ok": False, "error": "Неизвестное действие."}, status=400)
        if request_is_executor(request):
            return JsonResponse(
                {"ok": False, "error": "У вас роль «исполнитель»: сохранение нормы недоступно."},
                status=403,
            )
        setup_id_raw = (request.POST.get("setup_id") or "").strip()
        setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
        setup = (
            ProductSetup.objects.select_related("product")
            .filter(pk=setup_id, product__catalog_section=Product.CATALOG_NALADKI)
            .first()
        )
        if not setup:
            return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)

        def _dec(name, default=None):
            raw = (request.POST.get(name) or "").strip().replace(",", ".")
            if raw == "":
                return default
            try:
                return Decimal(raw)
            except (InvalidOperation, ValueError):
                return None

        tsht_norm = _dec("tsht_norm")
        tsht_min = _dec("tsht_min")
        if tsht_norm is None or tsht_min is None or tsht_norm < 0 or tsht_min < 0:
            return JsonResponse({"ok": False, "error": "Сначала рассчитайте Тшт."}, status=400)
        comment = (request.POST.get("comment") or "").strip()[:500]
        if not comment:
            return JsonResponse(
                {"ok": False, "error": "Укажите комментарий — зачем изменилась норма."},
                status=400,
            )
        k_raw = (request.POST.get("k_parts") or "1").strip()
        k_parts = int(k_raw) if k_raw.isdigit() and int(k_raw) >= 1 else 1
        prev = setup.piece_norms.order_by("-created_at", "-id").first()
        u = biota_user(request)
        entry = ProductSetupPieceNorm.objects.create(
            setup=setup,
            tsht_norm=tsht_norm,
            tsht_min=tsht_min,
            previous_tsht_norm=prev.tsht_norm if prev else None,
            comment=comment,
            author=(u or "").strip() or "?",
            t_auto=_dec("t_auto"),
            k_parts=k_parts,
            a_pct=_dec("a_pct"),
            t_ust=_dec("t_ust"),
            t_izm=_dec("t_izm"),
        )
        product_url = reverse("product_detail", kwargs={"pk": setup.product_id})
        return JsonResponse(
            {
                "ok": True,
                "id": entry.pk,
                "setup_id": setup.pk,
                "product_id": setup.product_id,
                "product_url": f"{product_url}?tab=setup-{setup.pk}",
                "tsht_norm": str(entry.tsht_norm),
                "tsht_min": str(entry.tsht_min),
                "comment": entry.comment,
                "author": entry.author,
                "created_at": entry.created_at.strftime("%d.%m.%Y %H:%M"),
                "previous_tsht_norm": str(entry.previous_tsht_norm) if entry.previous_tsht_norm is not None else None,
            }
        )

    products_qs = Product.objects.filter(
        catalog_section=Product.CATALOG_NALADKI,
    ).prefetch_related(
        "setups__tools"
    ).order_by("name")

    products_data = []
    for product in products_qs:
        setups_data = []
        for setup in product.setups.all():
            tools_data = []
            for tool in setup.tools.all():
                tools_data.append({
                    "id": tool.pk,
                    "number": tool.tool_number,
                    "name": tool.name,
                    "type": tool.tool_type,
                    "diameter": tool.diameter,
                    "overhang": tool.overhang,
                })
            setups_data.append({
                "id": setup.pk,
                "name": setup.name,
                "tools": tools_data,
            })
        products_data.append({
            "id": product.pk,
            "name": product.name,
            "setups": setups_data,
        })

    # Attach latest norms without N+1: one query
    setup_ids = [s["id"] for p in products_data for s in p["setups"]]
    latest_by_setup: dict[int, dict] = {}
    if setup_ids:
        for n in ProductSetupPieceNorm.objects.filter(setup_id__in=setup_ids).order_by(
            "setup_id", "-created_at", "-id"
        ):
            if n.setup_id in latest_by_setup:
                continue
            latest_by_setup[n.setup_id] = {
                "tsht_norm": str(n.tsht_norm),
                "tsht_min": str(n.tsht_min),
                "comment": n.comment or "",
            }
        for p in products_data:
            for s in p["setups"]:
                s["latest_norm"] = latest_by_setup.get(s["id"])

    from .calculator_modes import cutting_modes_payload

    u = biota_user(request)
    can_edit_modes = bool(u) and request_can_edit(request)
    shared_modes = _calculator_shared_modes_payload()
    leveling_cards = _calculator_leveling_cards_payload()

    return render(request, "shifts/calculator.html", {
        "products_json": _json.dumps(products_data, ensure_ascii=False),
        "cutting_modes_json": _json.dumps(cutting_modes_payload(), ensure_ascii=False),
        "shared_modes_json": _json.dumps(shared_modes, ensure_ascii=False),
        "leveling_cards_json": _json.dumps(leveling_cards, ensure_ascii=False),
        "can_edit_modes": can_edit_modes,
        "can_edit_leveling": can_edit_modes,
    })