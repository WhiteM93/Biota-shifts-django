from datetime import date, datetime

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts import db as biota_db
from biota_shifts import logic as biota_logic
from biota_shifts.auth import (
    ADMIN_USERNAME,
    _credentials_match,
    _filter_employees_for_user,
    _is_admin,
    _register_user,
    _resolve_registered_user,
    nav_permissions_for_user,
)
from biota_shifts.config import APP_DIR
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts import schedule as biota_schedule
from biota_shifts.schedule import employee_label_row

from .auth_utils import biota_login_required, biota_user
from .models import ToolItem


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
    if biota_user(request):
        return redirect("home")
    err = ""
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("home")
    remember_me = request.method == "POST" and request.POST.get("remember_me") == "1"
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        if _credentials_match(username, password):
            if not _is_admin(username):
                rec = _resolve_registered_user(username)
                if not rec or not rec.get("approved", True):
                    err = (
                        "Учётная запись ожидает подтверждения администратором. "
                        "После подтверждения вы сможете войти."
                    )
                else:
                    request.session["biota_username"] = username
                    if remember_me:
                        request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
                    else:
                        request.session.set_expiry(0)  # browser session only
                    return redirect(next_url or reverse("home"))
            else:
                request.session["biota_username"] = ADMIN_USERNAME
                if remember_me:
                    request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
                else:
                    request.session.set_expiry(0)  # browser session only
                return redirect(next_url or reverse("home"))
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


@require_http_methods(["GET", "HEAD", "POST"])
def register_view(request):
    err = ""
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        p1 = request.POST.get("password") or ""
        p2 = request.POST.get("password2") or ""
        if p1 != p2:
            err = "Пароли не совпадают"
        else:
            ok, msg = _register_user(username, p1)
            if ok:
                messages.success(
                    request,
                    "Регистрация принята. Вход будет возможен после подтверждения администратором в личном кабинете.",
                )
                return redirect("login")
            err = msg
    return render(
        request,
        "shifts/register.html",
        {"error": err, "hide_nav": True, "auth_page": True},
    )


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
        "low_stock_items": [],
    }

    can_inventory = nav_permissions_for_user(user or "").get("inventory", True)
    if can_inventory:
        ctx["low_stock_items"] = list(
            ToolItem.objects.filter(quantity__lt=10)
            .select_related("end_mill_spec", "tap_spec")
            .order_by("quantity", "category", "name")[:100]
        )

    if employees_df.empty:
        ctx["dashboard_error"] = (
            "Нет сотрудников для сводки — проверьте права доступа или справочник в БД."
        )
        return render(request, "shifts/home.html", ctx)

    ref_emp = biota_logic.normalize_emp_code(employees_df.iloc[0]["emp_code"]) or str(
        employees_df.iloc[0]["emp_code"]
    ).strip()
    year_options = biota_db.merged_year_options(cfg, ref_emp)
    if not year_options:
        ctx["dashboard_error"] = "Не удалось получить список годов (графики и БД)."
        return render(request, "shifts/home.html", ctx)

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
        return render(request, "shifts/home.html", ctx)

    _month_home = date(y, m, 1)
    _sd_h, _ed_h = biota_schedule.month_bounds(_month_home)
    try:
        _sched_home = biota_schedule.load_schedule_table(employees_df, y, m)
    except Exception as exc:
        ctx["dashboard_error"] = f"Не удалось загрузить график: {exc}"
        return render(request, "shifts/home.html", ctx)

    _emp_m = employees_df.copy()
    _emp_m["emp_code"] = _emp_m["emp_code"].map(biota_logic.normalize_emp_code)
    _emp_m = _emp_m[_emp_m["emp_code"] != ""].drop_duplicates(subset=["emp_code"], keep="first")
    _emp_m["label"] = _emp_m.apply(employee_label_row, axis=1)
    _codes_all = _emp_m["emp_code"].tolist()
    if not _codes_all:
        ctx["dashboard_error"] = "Нет ни одного кода сотрудника после нормализации — проверьте emp_code в БД."
        return render(request, "shifts/home.html", ctx)

    try:
        _per_emp = biota_logic.late_early_minutes_per_employee_month(
            cfg, _codes_all, _sched_home, _sd_h, _ed_h
        )
    except Exception as exc:
        ctx["dashboard_error"] = f"Не удалось построить сводку: {exc}"
        return render(request, "shifts/home.html", ctx)

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

    return render(request, "shifts/home.html", ctx)


@biota_login_required
@require_POST
def refresh_db_cache(request):
    biota_db.clear_biota_db_cache()
    return redirect(request.META.get("HTTP_REFERER") or "/")
