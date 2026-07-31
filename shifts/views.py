from datetime import date, datetime

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts import db as biota_db
from biota_shifts import logic as biota_logic
from biota_shifts.auth import (
    ADMIN_USERNAME,
    _credentials_match,
    employees_df_for_nav,
    _is_admin,
    _register_user,
    _resolve_registered_user,
    nav_permissions_for_user,
)
from biota_shifts.config import APP_DIR
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts import schedule as biota_schedule
from biota_shifts.schedule import employee_label_row

from .auth_utils import biota_login_required, biota_user, post_login_redirect, write_permission_required
from .email_verification import (
    email_uses_console_backend,
    login_block_reason,
    send_verification_email,
    verify_email_token,
)


def _df_columns_rows(df: pd.DataFrame):
    if df is None or df.empty:
        return [], []
    cols = [str(c) for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        rows.append(["" if pd.isna(r[c]) else str(r[c]) for c in df.columns])
    return cols, rows


def _fmt_minutes_human(v) -> str:
    """Минуты -> человекочитаемый формат для главной."""
    try:
        mins = int(v)
    except (TypeError, ValueError):
        mins = 0
    mins = max(0, mins)
    if mins < 60:
        return f"{mins} мин"
    return f"{mins // 60} ч {mins % 60} мин"


@require_http_methods(["GET", "HEAD", "POST"])
def login_view(request):
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
    return render(
        request,
        "shifts/login.html",
        {
            "error": err,
            "next_url": next_url,
            "remember_me": remember_me,
            "hide_nav": True,
            "auth_page": True,
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
def home_view(request):
    user = biota_user(request)
    if user and not nav_permissions_for_user(user).get("home", True):
        messages.warning(request, "У вас нет доступа к разделу «Главная (сводка)».")
        return redirect(post_login_redirect(user))

    cfg = biota_db.db_config()
    try:
        employees_df = biota_db.load_employees(cfg)
    except Exception as exc:
        return render(
            request,
            "shifts/error.html",
            {"title": "Ошибка БД", "message": str(exc)},
        )
    employees_df = employees_df_for_nav(user, "home", employees_df)

    ctx = {
        "username": user,
        "emp_count": len(employees_df),
        "app_dir": str(APP_DIR),
        "dashboard_error": None,
        "by_area_columns": [],
        "by_area_rows": [],
        "top10_columns": [],
        "top10_rows": [],
        "month_name": "",
        "dash_year": datetime.now().year,
        "dash_month": datetime.now().month,
        "year_options": [],
        "month_choices": [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)],
    }

    def _render_home():
        return render(request, "shifts/home.html", ctx)

    if employees_df.empty:
        ctx["dashboard_error"] = (
            "Нет сотрудников для сводки — проверьте права доступа или справочник в БД."
        )
        return _render_home()

    ref_emp = biota_logic.normalize_emp_code(employees_df.iloc[0]["emp_code"]) or str(
        employees_df.iloc[0]["emp_code"]
    ).strip()
    year_options = biota_db.merged_year_options(cfg, ref_emp)
    if not year_options:
        ctx["dashboard_error"] = "Не удалось получить список годов (графики и БД)."
        return _render_home()

    now = datetime.now()
    try:
        y = int(request.GET.get("year") or now.year)
    except (TypeError, ValueError):
        y = now.year
    try:
        m = int(request.GET.get("month") or now.month)
    except (TypeError, ValueError):
        m = now.month
    y = max(2000, min(2100, y))
    m = max(1, min(12, m))
    if y not in year_options:
        y = year_options[0]

    ctx["year_options"] = year_options
    ctx["dash_year"] = y
    ctx["dash_month"] = m
    ctx["month_name"] = MONTH_NAMES_RU[m]

    if not nav_permissions_for_user(user or "").get("skud", True):
        return _render_home()

    _month_home = date(y, m, 1)
    _sd_h, _ed_h = biota_schedule.month_bounds(_month_home)
    try:
        _sched_home = biota_schedule.load_schedule_table(employees_df, y, m)
    except Exception as exc:
        ctx["dashboard_error"] = f"Не удалось загрузить график: {exc}"
        return _render_home()

    _emp_m = employees_df.copy()
    _emp_m["emp_code"] = _emp_m["emp_code"].map(biota_logic.normalize_emp_code)
    _emp_m = _emp_m[_emp_m["emp_code"] != ""].drop_duplicates(subset=["emp_code"], keep="first")
    _emp_m["label"] = _emp_m.apply(employee_label_row, axis=1)
    _codes_all = _emp_m["emp_code"].tolist()
    if not _codes_all:
        ctx["dashboard_error"] = "Нет ни одного кода сотрудника после нормализации — проверьте emp_code в БД."
        return _render_home()

    try:
        _per_emp = biota_logic.late_early_minutes_per_employee_month(
            cfg, _codes_all, _sched_home, _sd_h, _ed_h
        )
    except Exception as exc:
        ctx["dashboard_error"] = f"Не удалось построить сводку: {exc}"
        return _render_home()

    _merged = _emp_m.merge(_per_emp, on="emp_code", how="left")
    _merged["Опоздания (мин)"] = _merged["Опоздания (мин)"].fillna(0).astype(int)
    _merged["Ранний уход (мин)"] = _merged["Ранний уход (мин)"].fillna(0).astype(int)
    _by_area = (
        _merged.groupby("department_name", as_index=False)
        .agg({"Опоздания (мин)": "sum", "Ранний уход (мин)": "sum"})
        .rename(columns={"department_name": "Отдел"})
        .sort_values("Отдел")
        .reset_index(drop=True)
    )
    _by_area["Всего (мин)"] = _by_area["Опоздания (мин)"] + _by_area["Ранний уход (мин)"]
    _merged["Всего (мин)"] = _merged["Опоздания (мин)"] + _merged["Ранний уход (мин)"]
    _top_src = _merged[_merged["Всего (мин)"] > 0]
    _top10 = (
        _top_src.nlargest(10, "Всего (мин)")[
            ["label", "emp_code", "Опоздания (мин)", "Ранний уход (мин)", "Всего (мин)"]
        ]
        .rename(columns={"label": "Сотрудник", "emp_code": "Код"})
        .reset_index(drop=True)
    )
    for _c in ("Опоздания (мин)", "Ранний уход (мин)", "Всего (мин)"):
        _by_area[_c] = _by_area[_c].map(_fmt_minutes_human)
        _top10[_c] = _top10[_c].map(_fmt_minutes_human)

    ac, ar = _df_columns_rows(_by_area)
    tc, tr = _df_columns_rows(_top10)
    ctx["by_area_columns"] = ac
    ctx["by_area_rows"] = ar
    ctx["top10_columns"] = tc
    ctx["top10_rows"] = tr
    ctx["top10_empty"] = _top10.empty

    return _render_home()


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

    from biota_shifts.auth import user_is_executor

    from .models import CalculatorModesState

    u = biota_user(request)
    if u and not _is_admin(u) and user_is_executor(u):
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
        if action != "save_piece_norm":
            return JsonResponse({"ok": False, "error": "Неизвестное действие."}, status=400)
        u = biota_user(request)
        from biota_shifts.auth import user_is_executor

        if u and not _is_admin(u) and user_is_executor(u):
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

    from biota_shifts.auth import user_is_executor

    from .calculator_modes import cutting_modes_payload

    u = biota_user(request)
    can_edit_modes = bool(u) and (_is_admin(u) or not user_is_executor(u))
    shared_modes = _calculator_shared_modes_payload()

    return render(request, "shifts/calculator.html", {
        "products_json": _json.dumps(products_data, ensure_ascii=False),
        "cutting_modes_json": _json.dumps(cutting_modes_payload(), ensure_ascii=False),
        "shared_modes_json": _json.dumps(shared_modes, ensure_ascii=False),
        "can_edit_modes": can_edit_modes,
    })