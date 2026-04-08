"""Личный кабинет: профиль и пароль (пользователи), имя и права (админ) — логика как в Streamlit."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from biota_shifts import db as biota_db
from biota_shifts.auth import (
    ADMIN_USERNAME,
    _access_scope_description,
    _allowed_areas_list,
    _allowed_departments_list,
    _change_password_registered,
    _distinct_area_tokens,
    _is_admin,
    _load_users_store,
    _resolve_registered_user,
    _set_user_privileges,
    _update_registered_profile,
    _user_access_scope_value,
)

from .auth_utils import biota_login_required, biota_user


def _canonical_store_username(username: str) -> str | None:
    store = _load_users_store()
    u = (username or "").strip()
    if not u:
        return None
    if u in store:
        return u
    ul = u.lower()
    for k in store:
        if str(k).strip().lower() == ul:
            return str(k)
    return None


_SCOPE_OPTIONS = ("none", "all", "department", "area")
_SCOPE_LABELS = {
    "none": "Нет доступа",
    "all": "Вся организация",
    "department": "Только выбранные цехи (отделы)",
    "area": "Только выбранные участки",
}


@biota_login_required
@require_http_methods(["GET", "POST"])
def cabinet_view(request):
    user = biota_user(request)
    if not user:
        return redirect("login")

    cfg = biota_db.db_config()
    try:
        employees_full = biota_db.load_employees(cfg)
    except Exception as exc:
        return render(request, "shifts/error.html", {"title": "Ошибка БД", "message": str(exc)})

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if _is_admin(user):
            if action == "admin_display_name":
                dn = (request.POST.get("admin_display_name") or "").strip()
                request.session["admin_display_name"] = dn
                messages.success(request, "Имя для отображения сохранено.")
                return redirect("cabinet")
            if action == "admin_privileges":
                target = (request.POST.get("priv_user") or "").strip()
                scope = (request.POST.get("priv_scope") or "none").strip()
                if scope not in _SCOPE_OPTIONS:
                    scope = "none"
                deps = request.POST.getlist("priv_dep")
                areas = request.POST.getlist("priv_area")
                ok, err = _set_user_privileges(target, scope, deps, areas)
                if ok:
                    messages.success(request, "Права сохранены.")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
        else:
            if action == "profile":
                dn = request.POST.get("display_name") or ""
                em = request.POST.get("email") or ""
                key = _canonical_store_username(user)
                if not key:
                    messages.error(request, "Профиль не найден.")
                else:
                    ok, err = _update_registered_profile(key, dn, em)
                    if ok:
                        messages.success(request, "Профиль сохранён.")
                    else:
                        messages.error(request, err)
                return redirect("cabinet")
            if action == "password":
                old_pw = request.POST.get("password_old") or ""
                new_pw = request.POST.get("password_new") or ""
                new2 = request.POST.get("password_new2") or ""
                key = _canonical_store_username(user)
                if new_pw != new2:
                    messages.error(request, "Новые пароли не совпадают.")
                elif not key:
                    messages.error(request, "Пользователь не найден.")
                else:
                    ok, err = _change_password_registered(key, old_pw, new_pw)
                    if ok:
                        messages.success(request, "Пароль обновлён.")
                    else:
                        messages.error(request, err)
                return redirect("cabinet")

    ctx: dict = {
        "is_admin": _is_admin(user),
        "admin_username": ADMIN_USERNAME,
    }

    if _is_admin(user):
        ctx["admin_display_name"] = (request.session.get("admin_display_name") or "").strip()
        priv_store = _load_users_store()
        ctx["priv_users"] = sorted(priv_store.keys())
        dep_opts = sorted(employees_full["department_name"].unique().tolist()) if not employees_full.empty else []
        area_opts = _distinct_area_tokens(employees_full["area_name"]) if not employees_full.empty else []
        ctx["dep_opts"] = dep_opts
        ctx["area_opts"] = area_opts
        sel = (request.GET.get("priv_user") or "").strip()
        if sel not in priv_store and ctx["priv_users"]:
            sel = ctx["priv_users"][0]
        ctx["priv_selected"] = sel if sel in priv_store else (ctx["priv_users"][0] if ctx["priv_users"] else "")
        pr = priv_store.get(ctx["priv_selected"], {}) if ctx["priv_selected"] else {}
        psc = _user_access_scope_value(pr)
        if psc not in _SCOPE_OPTIONS:
            psc = "none"
        ctx["priv_scope_current"] = psc
        ctx["priv_dep_selected"] = [x for x in _allowed_departments_list(pr) if x in dep_opts]
        ctx["priv_area_selected"] = [x for x in _allowed_areas_list(pr) if x in area_opts]
        ctx["scope_choices"] = [(s, _SCOPE_LABELS[s]) for s in _SCOPE_OPTIONS]
    else:
        rec = _resolve_registered_user(user) or {}
        ctx["profile_login"] = user
        ctx["profile_created"] = rec.get("created_at") or "—"
        ctx["profile_access"] = _access_scope_description(rec)
        ctx["profile_display_name"] = (rec.get("display_name") or "").strip()
        ctx["profile_email"] = (rec.get("email") or "").strip()
        ctx["profile_missing"] = not bool(rec)

    return render(request, "shifts/cabinet.html", ctx)
