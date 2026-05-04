"""Личный кабинет: профиль и пароль (пользователи), имя и права (админ) — логика как в Streamlit."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from biota_shifts import db as biota_db
from biota_shifts.auth import (
    ADMIN_USERNAME,
    NAV_KEYS,
    NAV_LABELS_RU,
    USER_ROLE_CHOICES,
    USER_ROLE_EXECUTOR,
    USER_ROLE_MANAGER,
    _nav_department_filters_map,
    _access_scope_description,
    _approve_registration,
    _change_password_registered,
    _distinct_area_tokens,
    _is_admin,
    _load_users_store,
    _resolve_registered_user,
    _set_user_privileges,
    _update_registered_profile,
    nav_permissions_for_user,
    user_role_for_username,
)
from .department_order import apply_department_order, load_department_order, save_department_order
from .position_order import apply_position_order, load_position_order, save_position_order
from .db_health import collect_system_health

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
                target_role = (request.POST.get("priv_role") or USER_ROLE_MANAGER).strip()
                sel_nav = request.POST.getlist("priv_nav")
                nav_map = {k: (k in sel_nav) for k in NAV_KEYS}
                dep_opts = sorted(employees_full["department_name"].unique().tolist()) if not employees_full.empty else []
                allowed_dep_set = set(dep_opts)
                nav_dep_filters: dict[str, list[str]] = {}
                for k in NAV_KEYS:
                    if not nav_map.get(k, True):
                        continue
                    if k == "products":
                        continue
                    picked = [d for d in request.POST.getlist(f"priv_nav_dep__{k}") if d in allowed_dep_set]
                    nav_dep_filters[k] = picked
                ok, err = _set_user_privileges(
                    target,
                    None,
                    [],
                    [],
                    nav=nav_map,
                    nav_dep_filters=nav_dep_filters,
                    role=target_role,
                )
                if ok:
                    messages.success(request, "Права сохранены.")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
            if action == "admin_approve_registration":
                target = (request.POST.get("approve_login") or "").strip()
                ok, err = _approve_registration(target)
                if ok:
                    messages.success(request, f"Регистрация подтверждена: {target}")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
            if action == "admin_dept_order":
                raw = request.POST.get("dept_order_text") or ""
                parts = [p.strip() for p in raw.replace("\r", "\n").replace(",", "\n").split("\n")]
                dep_opts = sorted(employees_full["department_name"].unique().tolist()) if not employees_full.empty else []
                allowed = set(dep_opts)
                cleaned = [p for p in parts if p and p in allowed]
                save_department_order(cleaned)
                messages.success(request, "Порядок отделов сохранен.")
                return redirect("cabinet")
            if action == "admin_pos_order":
                raw = request.POST.get("pos_order_text") or ""
                parts = [p.strip() for p in raw.replace("\r", "\n").replace(",", "\n").split("\n")]
                pos_opts = sorted(employees_full["position_name"].unique().tolist()) if not employees_full.empty else []
                allowed = set(pos_opts)
                cleaned = [p for p in parts if p and p in allowed]
                save_position_order(cleaned)
                messages.success(request, "Порядок должностей сохранен.")
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
        ctx["system_health"] = collect_system_health()
        priv_store = _load_users_store()
        ctx["pending_registrations"] = sorted(
            [k for k, v in priv_store.items() if not v.get("approved", True)],
            key=lambda x: str(x).lower(),
        )
        ctx["admin_display_name"] = (request.session.get("admin_display_name") or "").strip()
        ctx["priv_users"] = sorted(priv_store.keys())
        dep_opts = sorted(employees_full["department_name"].unique().tolist()) if not employees_full.empty else []
        dep_order = apply_department_order(dep_opts, load_department_order())
        pos_opts = sorted(employees_full["position_name"].unique().tolist()) if not employees_full.empty else []
        pos_order = apply_position_order(pos_opts, load_position_order())
        area_opts = _distinct_area_tokens(employees_full["area_name"]) if not employees_full.empty else []
        ctx["dep_opts"] = dep_opts
        ctx["dep_order_current"] = dep_order
        ctx["dep_order_text"] = "\n".join(dep_order)
        ctx["pos_opts"] = pos_opts
        ctx["pos_order_current"] = pos_order
        ctx["pos_order_text"] = "\n".join(pos_order)
        ctx["area_opts"] = area_opts
        sel = (request.GET.get("priv_user") or "").strip()
        if sel not in priv_store and ctx["priv_users"]:
            sel = ctx["priv_users"][0]
        ctx["priv_selected"] = sel if sel in priv_store else (ctx["priv_users"][0] if ctx["priv_users"] else "")
        pr = priv_store.get(ctx["priv_selected"], {}) if ctx["priv_selected"] else {}
        _pn = nav_permissions_for_user(ctx["priv_selected"]) if ctx["priv_selected"] else {k: True for k in NAV_KEYS}
        ctx["priv_role"] = user_role_for_username(ctx["priv_selected"]) if ctx["priv_selected"] else USER_ROLE_MANAGER
        ctx["priv_role_choices"] = USER_ROLE_CHOICES
        ctx["priv_role_labels"] = {
            USER_ROLE_MANAGER: "Руководитель",
            USER_ROLE_EXECUTOR: "Исполнитель (только просмотр/скачивание)",
        }
        ctx["priv_nav"] = _pn
        _ndf = _nav_department_filters_map(pr) if ctx["priv_selected"] else {}
        raw_ndf = pr.get("nav_dep_filters") if isinstance(pr.get("nav_dep_filters"), dict) else {}
        ctx["priv_nav_rows"] = []
        for k in NAV_KEYS:
            sel_deps = [d for d in (_ndf.get(k) or []) if d in dep_opts]
            if ctx["priv_selected"] and k == "payroll" and k not in raw_ndf:
                sel_deps = [d for d in (_ndf.get("defects") or []) if d in dep_opts]
            ctx["priv_nav_rows"].append(
                {
                    "key": k,
                    "label": NAV_LABELS_RU.get(k, k),
                    "on": _pn.get(k, True),
                    "locked": False,
                    "dep_selected": sel_deps,
                }
            )
    else:
        rec = _resolve_registered_user(user) or {}
        ctx["profile_login"] = user
        ctx["profile_created"] = rec.get("created_at") or "—"
        ctx["profile_access"] = _access_scope_description(rec)
        role = user_role_for_username(user)
        ctx["profile_role"] = "исполнитель" if role == USER_ROLE_EXECUTOR else "руководитель"
        ctx["profile_display_name"] = (rec.get("display_name") or "").strip()
        ctx["profile_email"] = (rec.get("email") or "").strip()
        ctx["profile_missing"] = not bool(rec)

    return render(request, "shifts/cabinet.html", ctx)
