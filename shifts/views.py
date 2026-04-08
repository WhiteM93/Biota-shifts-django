from django.conf import settings
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts import db as biota_db
from biota_shifts.auth import (
    ADMIN_USERNAME,
    _credentials_match,
    _filter_employees_for_user,
    _is_admin,
)
from biota_shifts.config import APP_DIR

from .auth_utils import biota_login_required, biota_user


@require_http_methods(["GET", "POST"])
def login_view(request):
    err = ""
    next_url = request.POST.get("next") or request.GET.get("next") or "/"
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        if _credentials_match(username, password):
            request.session["biota_username"] = (
                ADMIN_USERNAME if username.lower() == ADMIN_USERNAME.lower() else username
            )
            return redirect(next_url or "/")
        err = "Неверный логин или пароль"
    return render(request, "shifts/login.html", {"error": err, "next_url": next_url})


def logout_view(request):
    request.session.flush()
    return redirect(settings.LOGIN_URL)


@biota_login_required
def home_view(request):
    cfg = biota_db.db_config()
    try:
        employees_df = biota_db.load_employees(cfg)
    except Exception as exc:
        return render(
            request,
            "shifts/error.html",
            {"title": "Ошибка БД", "message": str(exc)},
        )
    user = biota_user(request)
    if user and not _is_admin(user):
        employees_df = _filter_employees_for_user(employees_df, user)
    return render(
        request,
        "shifts/home.html",
        {
            "username": user,
            "emp_count": len(employees_df),
            "app_dir": str(APP_DIR),
        },
    )


@biota_login_required
def graph_placeholder(request):
    return render(
        request,
        "shifts/placeholder.html",
        {"title": "График", "hint": "Перенос редактора графика из Streamlit — следующий этап."},
    )


@biota_login_required
def hours_placeholder(request):
    return render(
        request,
        "shifts/placeholder.html",
        {"title": "Часы по дням", "hint": "Перенос сетки часов — следующий этап."},
    )


@biota_login_required
def skud_placeholder(request):
    return render(
        request,
        "shifts/placeholder.html",
        {"title": "СКУД", "hint": "Перенос статистики и отметок — следующий этап."},
    )


@biota_login_required
def cabinet_placeholder(request):
    return render(
        request,
        "shifts/placeholder.html",
        {"title": "Личный кабинет", "hint": "Профиль и смена пароля — следующий этап."},
    )


@biota_login_required
@require_POST
def refresh_db_cache(request):
    biota_db.clear_biota_db_cache()
    return redirect(request.META.get("HTTP_REFERER") or "/")
