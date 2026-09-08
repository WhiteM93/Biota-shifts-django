"""ÐÐ¸ÑÐ½ÑÐ¹ ÐºÐ°Ð±Ð¸Ð½ÐµÑ: Ð¿ÑÐ¾ÑÐ¸Ð»Ñ Ð¸ Ð¿Ð°ÑÐ¾Ð»Ñ (Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ð¸), Ð¸Ð¼Ñ Ð¸ Ð¿ÑÐ°Ð²Ð° (Ð°Ð´Ð¼Ð¸Ð½) â Ð»Ð¾Ð³Ð¸ÐºÐ° ÐºÐ°Ðº Ð² Streamlit."""
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import shutil

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse

from biota_shifts import db as biota_db
from biota_shifts.config import INVENTORY_BACKUP_DIR, REGULATIONS_BACKUP_DIR, SCHEDULE_DIR
from biota_shifts.auth import (
    ADMIN_USERNAME,
    NAV_KEYS,
    NAV_LABELS_RU,
    NAV_LABELS_SHORT,
    USER_ROLE_CHOICES,
    USER_ROLE_EXECUTOR,
    USER_ROLE_MANAGER,
    NAV_KEYS_NO_DEPT_FILTER,
    _access_scope_description,
    _nav_department_filters_map,
    _approve_registration,
    _change_password_registered,
    _delete_registered_user,
    _distinct_area_tokens,
    _is_admin,
    _load_users_store,
    _compose_display_name,
    _person_name_parts,
    _resolve_registered_user,
    _set_user_privileges,
    _update_registered_names,
    _update_registered_profile,
    account_label_for_username,
    nav_permissions_for_user,
    user_role_for_username,
)
from shifts.models import InventoryStockEvent
from .department_order import apply_department_order, load_department_order
from .position_order import apply_position_order, load_position_order
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
        return render(request, "shifts/error.html", {"title": "ÐÑÐ¸Ð±ÐºÐ° ÐÐ", "message": str(exc)})

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if _is_admin(user):
            if action == "admin_display_name":
                dn = (request.POST.get("admin_display_name") or "").strip()
                request.session["admin_display_name"] = dn
                messages.success(request, "ÐÐ¼Ñ Ð´Ð»Ñ Ð¾ÑÐ¾Ð±ÑÐ°Ð¶ÐµÐ½Ð¸Ñ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ð¾.")
                return redirect("cabinet")
            if action == "admin_privileges":
                target = (request.POST.get("priv_user") or "").strip()
                target_role = (request.POST.get("priv_role") or USER_ROLE_MANAGER).strip()
                sel_nav = request.POST.getlist("priv_nav")
                nav_map = {k: (k in sel_nav) for k in NAV_KEYS}
                dep_opts = sorted(employees_full["department_name"].unique().tolist()) if not employees_full.empty else []
                allowed_dep_set = set(dep_opts)
                if dep_opts:
                    nav_dep_filters: dict[str, list[str]] = {}
                    for k in NAV_KEYS:
                        if not nav_map.get(k, True):
                            continue
                        if k in NAV_KEYS_NO_DEPT_FILTER:
                            continue
                        picked = [d for d in request.POST.getlist(f"priv_nav_dep__{k}") if d in allowed_dep_set]
                        nav_dep_filters[k] = picked
                else:
                    nav_dep_filters = None
                store_before = _load_users_store()
                old_inv = bool((store_before.get(target) or {}).get("inventory_stock_manage"))
                inv_flag = (request.POST.get("priv_inventory_stock_manage") or "0").strip() == "1"
                mqe_flag = (request.POST.get("priv_machines_quick_edit") or "0").strip() == "1"
                ok, err = _set_user_privileges(
                    target,
                    None,
                    [],
                    [],
                    nav=nav_map,
                    nav_dep_filters=nav_dep_filters,
                    role=target_role,
                    inventory_stock_manage=inv_flag,
                    machines_quick_edit=mqe_flag,
                )
                if ok:
                    messages.success(request, "ÐÑÐ°Ð²Ð° ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ñ.")
                    if old_inv != inv_flag:
                        InventoryStockEvent.objects.create(
                            actor_username=user,
                            event_type=InventoryStockEvent.EVENT_PRIVILEGE,
                            summary=(
                                f"Ð£ÑÑÑÐ½Ð°Ñ Ð·Ð°Ð¿Ð¸ÑÑ Â«{target}Â»: Ð¿ÑÐ°Ð²Ð¾ ÑÐµÐ´Ð°ÐºÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð¸Ñ Ð¸ ÑÐ´Ð°Ð»ÐµÐ½Ð¸Ñ Ð½Ð° ÑÐºÐ»Ð°Ð´Ðµ "
                                f"{'Ð²ÐºÐ»ÑÑÐµÐ½Ð¾' if inv_flag else 'Ð²ÑÐºÐ»ÑÑÐµÐ½Ð¾'}"
                            ),
                            details={"target_user": target, "enabled": inv_flag},
                        )
                else:
                    messages.error(request, err)
                return redirect(
                    f"{reverse('cabinet')}?priv_user={quote(target)}&priv_saved=1#cabinet-privileges"
                )
            if action == "admin_approve_registration":
                target = (request.POST.get("approve_login") or "").strip()
                ok, err = _approve_registration(target)
                if ok:
                    messages.success(request, f"Ð ÐµÐ³Ð¸ÑÑÑÐ°ÑÐ¸Ñ Ð¿Ð¾Ð´ÑÐ²ÐµÑÐ¶Ð´ÐµÐ½Ð°: {target}")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
            if action == "admin_user_names":
                target = (request.POST.get("names_login") or "").strip()
                first = (request.POST.get("first_name") or "").strip()
                last = (request.POST.get("last_name") or "").strip()
                ok, err = _update_registered_names(target, first, last)
                if ok:
                    label = account_label_for_username(target)
                    messages.success(
                        request,
                        f"ÐÐ¼Ñ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ð¾: {label}" if label != target else f"ÐÐ¼Ñ Ð´Ð»Ñ Â«{target}Â» Ð¾ÑÐ¸ÑÐµÐ½Ð¾.",
                    )
                else:
                    messages.error(request, err)
                return redirect(
                    f"{reverse('cabinet')}?priv_user={quote(target)}#cabinet-privileges"
                )
            if action == "admin_delete_user":
                target = (request.POST.get("delete_login") or "").strip()
                ok, err = _delete_registered_user(target)
                if ok:
                    messages.success(request, f"Ð£ÑÑÑÐ½Ð°Ñ Ð·Ð°Ð¿Ð¸ÑÑ ÑÐ´Ð°Ð»ÐµÐ½Ð°: {target}")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
        else:
            if action == "profile":
                first = (request.POST.get("first_name") or "").strip()
                last = (request.POST.get("last_name") or "").strip()
                em = request.POST.get("email") or ""
                key = _canonical_store_username(user)
                if not key:
                    messages.error(request, "ÐÑÐ¾ÑÐ¸Ð»Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½.")
                else:
                    ok, err = _update_registered_profile(
                        key, email=em, first_name=first, last_name=last
                    )
                    if ok:
                        messages.success(request, "ÐÑÐ¾ÑÐ¸Ð»Ñ ÑÐ¾ÑÑÐ°Ð½ÑÐ½.")
                    else:
                        messages.error(request, err)
                return redirect("cabinet")
            if action == "password":
                old_pw = request.POST.get("password_old") or ""
                new_pw = request.POST.get("password_new") or ""
                new2 = request.POST.get("password_new2") or ""
                key = _canonical_store_username(user)
                if new_pw != new2:
                    messages.error(request, "ÐÐ¾Ð²ÑÐµ Ð¿Ð°ÑÐ¾Ð»Ð¸ Ð½Ðµ ÑÐ¾Ð²Ð¿Ð°Ð´Ð°ÑÑ.")
                elif not key:
                    messages.error(request, "ÐÐ¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½.")
                else:
                    ok, err = _change_password_registered(key, old_pw, new_pw)
                    if ok:
                        messages.success(request, "ÐÐ°ÑÐ¾Ð»Ñ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐ½.")
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
            [
                {
                    "login": k,
                    "email": (v.get("email") or "").strip(),
                    "email_verified": not (v.get("email") or "").strip()
                    or bool(v.get("email_verified", True)),
                    "label": account_label_for_username(k),
                }
                for k, v in priv_store.items()
                if not v.get("approved", True)
            ],
            key=lambda x: str(x["login"]).lower(),
        )
        ctx["admin_display_name"] = (request.session.get("admin_display_name") or "").strip()
        priv_user_rows = []
        for login in sorted(priv_store.keys(), key=lambda s: str(s).casefold()):
            rec = priv_store.get(login) or {}
            first, last = _person_name_parts(rec)
            label = _compose_display_name(first, last) or ""
            priv_user_rows.append(
                {
                    "login": login,
                    "first_name": first,
                    "last_name": last,
                    "label": label,
                    "title": f"{label} ({login})" if label else login,
                }
            )
        ctx["priv_user_rows"] = priv_user_rows
        ctx["priv_users"] = [r["login"] for r in priv_user_rows]
        dep_opts = sorted(employees_full["department_name"].unique().tolist()) if not employees_full.empty else []
        dep_opts = apply_department_order(dep_opts, load_department_order())
        pos_opts = sorted(employees_full["position_name"].unique().tolist()) if not employees_full.empty else []
        pos_opts = apply_position_order(pos_opts, load_position_order())
        area_opts = _distinct_area_tokens(employees_full["area_name"]) if not employees_full.empty else []
        ctx["dep_opts"] = dep_opts
        ctx["pos_opts"] = pos_opts
        ctx["area_opts"] = area_opts
        sel = (request.GET.get("priv_user") or "").strip()
        if sel not in priv_store and ctx["priv_users"]:
            sel = ctx["priv_users"][0]
        ctx["priv_selected"] = sel if sel in priv_store else (ctx["priv_users"][0] if ctx["priv_users"] else "")
        pr = priv_store.get(ctx["priv_selected"], {}) if ctx["priv_selected"] else {}
        priv_first, priv_last = _person_name_parts(pr)
        ctx["priv_first_name"] = priv_first
        ctx["priv_last_name"] = priv_last
        ctx["priv_selected_label"] = _compose_display_name(priv_first, priv_last)
        _pn = nav_permissions_for_user(ctx["priv_selected"]) if ctx["priv_selected"] else {k: True for k in NAV_KEYS}
        ctx["priv_role"] = user_role_for_username(ctx["priv_selected"]) if ctx["priv_selected"] else USER_ROLE_MANAGER
        ctx["priv_role_choices"] = USER_ROLE_CHOICES
        ctx["priv_role_labels"] = {
            USER_ROLE_MANAGER: "Ð ÑÐºÐ¾Ð²Ð¾Ð´Ð¸ÑÐµÐ»Ñ",
            USER_ROLE_EXECUTOR: "ÐÑÐ¿Ð¾Ð»Ð½Ð¸ÑÐµÐ»Ñ (ÑÐ¾Ð»ÑÐºÐ¾ Ð¿ÑÐ¾ÑÐ¼Ð¾ÑÑ/ÑÐºÐ°ÑÐ¸Ð²Ð°Ð½Ð¸Ðµ)",
        }
        ctx["priv_nav"] = _pn
        _ndf = _nav_department_filters_map(pr) if ctx["priv_selected"] else {}
        raw_ndf = pr.get("nav_dep_filters") if isinstance(pr.get("nav_dep_filters"), dict) else {}
        ctx["priv_stock_manage"] = bool(pr.get("inventory_stock_manage"))
        ctx["priv_machines_quick_edit"] = bool(pr.get("machines_quick_edit"))
        ctx["priv_nav_rows"] = []
        for k in NAV_KEYS:
            sel_deps = [d for d in (_ndf.get(k) or []) if d in dep_opts]
            if ctx["priv_selected"] and k == "payroll" and k not in raw_ndf:
                sel_deps = [d for d in (_ndf.get("defects") or []) if d in dep_opts]
            has_dept_picker = bool(dep_opts and k not in NAV_KEYS_NO_DEPT_FILTER)
            extra_toggle = None
            if k == "inventory":
                extra_toggle = {
                    "field": "priv_inventory_stock_manage",
                    "label": "Ð ÐµÐ´Ð°ÐºÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð¸Ðµ ÑÐºÐ»Ð°Ð´Ð°",
                    "on": ctx["priv_stock_manage"],
                }
            elif k == "machines":
                extra_toggle = {
                    "field": "priv_machines_quick_edit",
                    "label": "ÐÑÑÑÑÐ¾Ðµ ÑÐµÐ´Ð°ÐºÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð¸Ðµ",
                    "on": ctx["priv_machines_quick_edit"],
                }
            ctx["priv_nav_rows"].append(
                {
                    "key": k,
                    "label": NAV_LABELS_SHORT.get(k, NAV_LABELS_RU.get(k, k)),
                    "on": _pn.get(k, True),
                    "locked": False,
                    "dep_selected": sel_deps,
                    "dep_count": len(sel_deps),
                    "has_dept_picker": has_dept_picker,
                    "no_dept_filter": k in NAV_KEYS_NO_DEPT_FILTER,
                    "extra_toggle": extra_toggle,
                }
            )
    else:
        rec = _resolve_registered_user(user) or {}
        ctx["profile_login"] = user
        ctx["profile_created"] = rec.get("created_at") or "â"
        ctx["profile_access"] = _access_scope_description(rec)
        role = user_role_for_username(user)
        ctx["profile_role"] = "Ð¸ÑÐ¿Ð¾Ð»Ð½Ð¸ÑÐµÐ»Ñ" if role == USER_ROLE_EXECUTOR else "ÑÑÐºÐ¾Ð²Ð¾Ð´Ð¸ÑÐµÐ»Ñ"
        profile_first, profile_last = _person_name_parts(rec)
        ctx["profile_first_name"] = profile_first
        ctx["profile_last_name"] = profile_last
        ctx["profile_display_name"] = account_label_for_username(user) if rec else ""
        ctx["profile_email"] = (rec.get("email") or "").strip()
        ctx["profile_email_verified"] = not (rec.get("email") or "").strip() or bool(
            rec.get("email_verified", True)
        )
        ctx["profile_missing"] = not bool(rec)

    return render(request, "shifts/cabinet.html", ctx)


@biota_login_required
@require_http_methods(["GET", "POST"])
def schedule_backups_view(request):
    """Ð£Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐµÐ·ÐµÑÐ²Ð½ÑÐ¼Ð¸ ÐºÐ¾Ð¿Ð¸ÑÐ¼Ð¸ Ð³ÑÐ°ÑÐ¸ÐºÐ¾Ð²."""
    # ÐÑÐ¾Ð²ÐµÑÑÐµÐ¼, ÑÑÐ¾ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ Ð°Ð´Ð¼Ð¸Ð½
    if not _is_admin(biota_user(request)):
        messages.error(request, "ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½")
        return redirect("/cabinet/")

    backups_dir = SCHEDULE_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        # ÐÐ°Ð³ÑÑÐ·Ð¸ÑÑ ÑÐ°Ð¹Ð» ÑÐµÐ·ÐµÑÐ²Ð½Ð¾Ð¹ ÐºÐ¾Ð¿Ð¸Ð¸
        if action == "upload":
            uploaded_file = request.FILES.get("backup_file")
            if not uploaded_file:
                messages.error(request, "ÐÑÐ±ÐµÑÐ¸ÑÐµ ÑÐ°Ð¹Ð» Ð´Ð»Ñ Ð·Ð°Ð³ÑÑÐ·ÐºÐ¸")
                return redirect("/cabinet/backups/")

            if not uploaded_file.name.endswith(".xlsx"):
                messages.error(request, "Ð¤Ð°Ð¹Ð» Ð´Ð¾Ð»Ð¶ÐµÐ½ Ð±ÑÑÑ Ð² ÑÐ¾ÑÐ¼Ð°ÑÐµ .xlsx")
                return redirect("/cabinet/backups/")

            try:
                # Ð¡Ð¾ÑÑÐ°Ð½ÑÐµÐ¼ Ð·Ð°Ð³ÑÑÐ¶ÐµÐ½Ð½ÑÐ¹ ÑÐ°Ð¹Ð» Ð² Ð¿Ð°Ð¿ÐºÑ Ð±ÑÐºÐ°Ð¿Ð¾Ð²
                backup_path = backups_dir / uploaded_file.name
                with open(backup_path, "wb") as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

                messages.success(request, f"Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ Ð·Ð°Ð³ÑÑÐ¶ÐµÐ½Ð°: {uploaded_file.name}")
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ Ð·Ð°Ð³ÑÑÐ·ÐºÐµ: {exc}")

            return redirect("/cabinet/backups/")

        # Ð¡Ð¾Ð·Ð´Ð°ÑÑ ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ñ Ð²ÑÐµÑ Ð³ÑÐ°ÑÐ¸ÐºÐ¾Ð²
        elif action == "backup_all":
            try:
                # ÐÐ°ÑÐ¾Ð´Ð¸Ð¼ Ð²ÑÐµ ÑÐ°Ð¹Ð»Ñ schedule_*.xlsx Ð² Ð¾ÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ð¿Ð°Ð¿ÐºÐµ
                main_dir = SCHEDULE_DIR
                backup_count = 0

                for schedule_file in main_dir.glob("schedule_*.xlsx"):
                    if schedule_file.is_file():
                        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð¸Ð¼Ñ Ð´Ð»Ñ Ð±ÑÐºÐ°Ð¿Ð° Ñ Ð²ÑÐµÐ¼ÐµÐ½Ð½Ð¾Ð¹ Ð¼ÐµÑÐºÐ¾Ð¹
                        now = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_name = f"{schedule_file.stem}_{now}.xlsx"
                        backup_path = backups_dir / backup_name

                        # ÐÐ¾Ð¿Ð¸ÑÑÐµÐ¼ ÑÐ°Ð¹Ð»
                        shutil.copy2(schedule_file, backup_path)
                        backup_count += 1

                messages.success(request, f"Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¾ {backup_count} ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ð¹ Ð³ÑÐ°ÑÐ¸ÐºÐ¾Ð²")
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ð¸ ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ð¹: {exc}")

            return redirect("/cabinet/backups/")

        # ÐÐ¾ÑÑÑÐ°Ð½Ð¾Ð²Ð¸ÑÑ Ð¸Ð· ÑÐµÐ·ÐµÑÐ²Ð½Ð¾Ð¹ ÐºÐ¾Ð¿Ð¸Ð¸
        elif action == "restore":
            backup_filename = request.POST.get("backup_filename", "").strip()
            if not backup_filename or ".." in backup_filename:
                messages.error(request, "ÐÐµÐºÐ¾ÑÑÐµÐºÑÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÑÐ°Ð¹Ð»Ð°")
                return redirect("/cabinet/backups/")

            backup_path = backups_dir / backup_filename
            if not backup_path.exists() or not backup_path.is_file():
                messages.error(request, "Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°")
                return redirect("/cabinet/backups/")

            try:
                # ÐÐ·Ð²Ð»ÐµÐºÐ°ÐµÐ¼ Ð¸Ð¼Ñ Ð¸ÑÑÐ¾Ð´Ð½Ð¾Ð³Ð¾ ÑÐ°Ð¹Ð»Ð° (ÑÐ´Ð°Ð»ÑÐµÐ¼ Ð²ÑÐµÐ¼ÐµÐ½Ð½ÑÑ Ð¼ÐµÑÐºÑ)
                # schedule_2026_05_20260521_101450.xlsx -> schedule_2026_05.xlsx
                parts = backup_filename.replace(".xlsx", "").split("_")
                if len(parts) >= 4:  # schedule, year, month, Ð¸ Ð´Ð°ÑÐ°
                    original_name = f"{parts[0]}_{parts[1]}_{parts[2]}.xlsx"
                else:
                    original_name = backup_filename

                original_path = SCHEDULE_DIR / original_name

                # ÐÐ¾Ð¿Ð¸ÑÑÐµÐ¼ Ð±ÑÐºÐ°Ð¿ Ð¾Ð±ÑÐ°ÑÐ½Ð¾
                shutil.copy2(backup_path, original_path)
                messages.success(request, f"ÐÑÐ°ÑÐ¸Ðº Ð²Ð¾ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½ Ð¸Ð· ÑÐµÐ·ÐµÑÐ²Ð½Ð¾Ð¹ ÐºÐ¾Ð¿Ð¸Ð¸: {backup_filename}")
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ Ð²Ð¾ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ð¸: {exc}")

            return redirect("/cabinet/backups/")

    # ÐÐ¾Ð»ÑÑÐ¸ÑÑ ÑÐ¿Ð¸ÑÐ¾Ðº ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ð¹, Ð¾ÑÑÐ¾ÑÑÐ¸ÑÐ¾Ð²Ð°Ð½Ð½ÑÐ¹ Ð¿Ð¾ Ð´Ð°ÑÐµ (Ð½Ð¾Ð²ÑÐµ ÑÐ²ÐµÑÑÑ)
    backups = []
    if backups_dir.exists():
        for backup_file in sorted(backups_dir.glob("schedule_*.xlsx"),
                                  key=lambda p: p.stat().st_mtime,
                                  reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size": f"{stat.st_size / 1024:.1f} KB",
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })

    ctx = {
        "backups": backups,
        "backups_count": len(backups),
    }

    return render(request, "shifts/schedule_backups.html", ctx)


@biota_login_required
@require_http_methods(["GET"])
def schedule_backup_download(request, filename: str):
    """Ð¡ÐºÐ°ÑÐ°ÑÑ ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ñ Ð³ÑÐ°ÑÐ¸ÐºÐ°."""
    from biota_shifts.config import SCHEDULE_DIR

    # ÐÑÐ¾Ð²ÐµÑÑÐµÐ¼, ÑÑÐ¾ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ Ð°Ð´Ð¼Ð¸Ð½
    if not _is_admin(biota_user(request)):
        return HttpResponse("ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½", status=403)

    # ÐÑÐ¾Ð²ÐµÑÑÐµÐ¼ Ð¸Ð¼Ñ ÑÐ°Ð¹Ð»Ð° (Ð·Ð°ÑÐ¸ÑÐ° Ð¾Ñ directory traversal)
    if ".." in filename or "/" in filename or "\\" in filename:
        return HttpResponse("ÐÐµÐºÐ¾ÑÑÐµÐºÑÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÑÐ°Ð¹Ð»Ð°", status=400)

    backup_path = SCHEDULE_DIR / "backups" / filename

    if not backup_path.exists() or not backup_path.is_file():
        return HttpResponse("Ð¤Ð°Ð¹Ð» Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", status=404)

    # ÐÑÐ¿ÑÐ°Ð²Ð»ÑÐµÐ¼ ÑÐ°Ð¹Ð»
    with open(backup_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


@biota_login_required
@require_http_methods(["GET", "POST"])
def inventory_backups_view(request):
    """Ð£Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐµÐ·ÐµÑÐ²Ð½ÑÐ¼Ð¸ ÐºÐ¾Ð¿Ð¸ÑÐ¼Ð¸ ÑÐºÐ»Ð°Ð´Ð° (JSON)."""
    from shifts.inventory_backup import (
        InventoryBackupError,
        backup_filename_now,
        export_inventory_payload,
        is_safe_backup_filename,
        list_backup_files,
        parse_inventory_backup_bytes,
        restore_inventory_from_payload,
        write_backup_file,
    )

    if not _is_admin(biota_user(request)):
        messages.error(request, "ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½")
        return redirect("/cabinet/")

    backups_dir = INVENTORY_BACKUP_DIR

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "upload":
            uploaded_file = request.FILES.get("backup_file")
            if not uploaded_file:
                messages.error(request, "ÐÑÐ±ÐµÑÐ¸ÑÐµ ÑÐ°Ð¹Ð» Ð´Ð»Ñ Ð·Ð°Ð³ÑÑÐ·ÐºÐ¸")
                return redirect("/cabinet/inventory-backups/")

            if not uploaded_file.name.endswith(".json"):
                messages.error(request, "Ð¤Ð°Ð¹Ð» Ð´Ð¾Ð»Ð¶ÐµÐ½ Ð±ÑÑÑ Ð² ÑÐ¾ÑÐ¼Ð°ÑÐµ .json")
                return redirect("/cabinet/inventory-backups/")

            try:
                raw = uploaded_file.read()
                parse_inventory_backup_bytes(raw)
                safe_name = uploaded_file.name
                if not is_safe_backup_filename(safe_name):
                    safe_name = backup_filename_now()
                backup_path = backups_dir / safe_name
                backup_path.write_bytes(raw)
                messages.success(request, f"Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ Ð·Ð°Ð³ÑÑÐ¶ÐµÐ½Ð°: {safe_name}")
            except InventoryBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ Ð·Ð°Ð³ÑÑÐ·ÐºÐµ: {exc}")

            return redirect("/cabinet/inventory-backups/")

        if action == "backup_now":
            try:
                path = write_backup_file(backups_dir)
                payload = export_inventory_payload()
                tools_n = len(payload["tool_items"])
                messages.success(
                    request,
                    f"Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ ÑÐºÐ»Ð°Ð´Ð° ÑÐ¾Ð·Ð´Ð°Ð½Ð°: {path.name} ({tools_n} Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¹ Ð¸Ð½ÑÑÑÑÐ¼ÐµÐ½ÑÐ°)",
                )
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ð¸ ÑÐµÐ·ÐµÑÐ²Ð½Ð¾Ð¹ ÐºÐ¾Ð¿Ð¸Ð¸: {exc}")

            return redirect("/cabinet/inventory-backups/")

        if action == "restore":
            backup_filename = request.POST.get("backup_filename", "").strip()
            if not is_safe_backup_filename(backup_filename):
                messages.error(request, "ÐÐµÐºÐ¾ÑÑÐµÐºÑÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÑÐ°Ð¹Ð»Ð°")
                return redirect("/cabinet/inventory-backups/")

            backup_path = backups_dir / backup_filename
            if not backup_path.exists() or not backup_path.is_file():
                messages.error(request, "Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°")
                return redirect("/cabinet/inventory-backups/")

            try:
                write_backup_file(backups_dir, filename=f"inventory_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                raw = backup_path.read_bytes()
                payload = parse_inventory_backup_bytes(raw)
                stats = restore_inventory_from_payload(payload)
                messages.success(
                    request,
                    "Ð¡ÐºÐ»Ð°Ð´ Ð²Ð¾ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½ Ð¸Ð· ÑÐµÐ·ÐµÑÐ²Ð½Ð¾Ð¹ ÐºÐ¾Ð¿Ð¸Ð¸: "
                    f"{stats['tools']} Ð¿Ð¾Ð·Ð¸ÑÐ¸Ð¹, {stats['movements']} Ð´Ð²Ð¸Ð¶ÐµÐ½Ð¸Ð¹, "
                    f"{stats['purchases']} Ð·Ð°ÑÐ²Ð¾Ðº Ð½Ð° Ð·Ð°ÐºÑÐ¿ÐºÑ.",
                )
            except InventoryBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ Ð²Ð¾ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ð¸: {exc}")

            return redirect("/cabinet/inventory-backups/")

    backups = list_backup_files(backups_dir)
    ctx = {
        "backups": backups,
        "backups_count": len(backups),
        "backups_dir": str(backups_dir.resolve()),
    }
    return render(request, "shifts/inventory_backups.html", ctx)


@biota_login_required
@require_http_methods(["GET"])
def inventory_backup_download(request, filename: str):
    """Ð¡ÐºÐ°ÑÐ°ÑÑ ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ñ ÑÐºÐ»Ð°Ð´Ð° Ð½Ð° Ð´Ð¸ÑÐº / ÑÐ»ÐµÑÐºÑ."""
    from shifts.inventory_backup import is_safe_backup_filename

    if not _is_admin(biota_user(request)):
        return HttpResponse("ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½", status=403)

    if not is_safe_backup_filename(filename):
        return HttpResponse("ÐÐµÐºÐ¾ÑÑÐµÐºÑÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÑÐ°Ð¹Ð»Ð°", status=400)

    backup_path = INVENTORY_BACKUP_DIR / filename
    if not backup_path.exists() or not backup_path.is_file():
        return HttpResponse("Ð¤Ð°Ð¹Ð» Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", status=404)

    with open(backup_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


@biota_login_required
@require_http_methods(["GET", "POST"])
def regulations_backups_view(request):
    """Ð£Ð¿ÑÐ°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐµÐ·ÐµÑÐ²Ð½ÑÐ¼Ð¸ ÐºÐ¾Ð¿Ð¸ÑÐ¼Ð¸ ÑÐµÐ³Ð»Ð°Ð¼ÐµÐ½ÑÐ¾Ð² (JSON)."""
    from regulations.regulations_backup import (
        RegulationsBackupError,
        backup_filename_now,
        export_regulations_payload,
        is_safe_backup_filename,
        list_backup_files,
        parse_regulations_backup_bytes,
        restore_regulations_from_payload,
        write_backup_file,
    )

    if not _is_admin(biota_user(request)):
        messages.error(request, "ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½")
        return redirect("/cabinet/")

    backups_dir = REGULATIONS_BACKUP_DIR

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "upload":
            uploaded_file = request.FILES.get("backup_file")
            if not uploaded_file:
                messages.error(request, "ÐÑÐ±ÐµÑÐ¸ÑÐµ ÑÐ°Ð¹Ð» Ð´Ð»Ñ Ð·Ð°Ð³ÑÑÐ·ÐºÐ¸")
                return redirect("/cabinet/regulations-backups/")

            if not uploaded_file.name.endswith(".json"):
                messages.error(request, "Ð¤Ð°Ð¹Ð» Ð´Ð¾Ð»Ð¶ÐµÐ½ Ð±ÑÑÑ Ð² ÑÐ¾ÑÐ¼Ð°ÑÐµ .json")
                return redirect("/cabinet/regulations-backups/")

            try:
                raw = uploaded_file.read()
                parse_regulations_backup_bytes(raw)
                safe_name = uploaded_file.name
                if not is_safe_backup_filename(safe_name):
                    safe_name = backup_filename_now()
                backup_path = backups_dir / safe_name
                backup_path.write_bytes(raw)
                messages.success(request, f"Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ Ð·Ð°Ð³ÑÑÐ¶ÐµÐ½Ð°: {safe_name}")
            except RegulationsBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ Ð·Ð°Ð³ÑÑÐ·ÐºÐµ: {exc}")

            return redirect("/cabinet/regulations-backups/")

        if action == "backup_all":
            try:
                path = write_backup_file(backups_dir)
                payload = export_regulations_payload()
                plans_n = len(payload["regulation_plans"])
                messages.success(
                    request,
                    f"Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ ÑÐµÐ³Ð»Ð°Ð¼ÐµÐ½ÑÐ¾Ð² ÑÐ¾Ð·Ð´Ð°Ð½Ð°: {path.name} ({plans_n} Ð·Ð°Ð¿Ð¸ÑÐµÐ¹)",
                )
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ð¸ ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ð¹: {exc}")

            return redirect("/cabinet/regulations-backups/")

        if action == "restore":
            backup_filename = request.POST.get("backup_filename", "").strip()
            if not is_safe_backup_filename(backup_filename):
                messages.error(request, "ÐÐµÐºÐ¾ÑÑÐµÐºÑÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÑÐ°Ð¹Ð»Ð°")
                return redirect("/cabinet/regulations-backups/")

            backup_path = backups_dir / backup_filename
            if not backup_path.exists() or not backup_path.is_file():
                messages.error(request, "Ð ÐµÐ·ÐµÑÐ²Ð½Ð°Ñ ÐºÐ¾Ð¿Ð¸Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°")
                return redirect("/cabinet/regulations-backups/")

            try:
                write_backup_file(
                    backups_dir,
                    filename=f"regulations_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                )
                raw = backup_path.read_bytes()
                payload = parse_regulations_backup_bytes(raw)
                stats = restore_regulations_from_payload(payload)
                messages.success(
                    request,
                    f"Ð ÐµÐ³Ð»Ð°Ð¼ÐµÐ½ÑÑ Ð²Ð¾ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½Ñ Ð¸Ð· ÑÐµÐ·ÐµÑÐ²Ð½Ð¾Ð¹ ÐºÐ¾Ð¿Ð¸Ð¸: {stats['plans']} Ð·Ð°Ð¿Ð¸ÑÐµÐ¹.",
                )
            except RegulationsBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° Ð¿ÑÐ¸ Ð²Ð¾ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ð¸: {exc}")

            return redirect("/cabinet/regulations-backups/")

    backups = list_backup_files(backups_dir)
    ctx = {
        "backups": backups,
        "backups_count": len(backups),
        "backups_dir": str(backups_dir.resolve()),
    }
    return render(request, "shifts/regulations_backups.html", ctx)


@biota_login_required
@require_http_methods(["GET"])
def regulations_backup_download(request, filename: str):
    """Ð¡ÐºÐ°ÑÐ°ÑÑ ÑÐµÐ·ÐµÑÐ²Ð½ÑÑ ÐºÐ¾Ð¿Ð¸Ñ ÑÐµÐ³Ð»Ð°Ð¼ÐµÐ½ÑÐ¾Ð²."""
    from regulations.regulations_backup import is_safe_backup_filename

    if not _is_admin(biota_user(request)):
        return HttpResponse("ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½", status=403)

    if not is_safe_backup_filename(filename):
        return HttpResponse("ÐÐµÐºÐ¾ÑÑÐµÐºÑÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÑÐ°Ð¹Ð»Ð°", status=400)

    backup_path = REGULATIONS_BACKUP_DIR / filename
    if not backup_path.exists() or not backup_path.is_file():
        return HttpResponse("Ð¤Ð°Ð¹Ð» Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", status=404)

    with open(backup_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


def _notify_cron_line(hm: str, slot: str) -> str:
    parts = (hm or "08:20").strip().split(":")
    h = int(parts[0]) if parts and parts[0].isdigit() else 8
    mi = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 20
    return (
        f"{mi} {h} * * * cd $PROJECT && .venv/bin/python manage.py "
        f"send_attendance_summaries --slot={slot}"
    )


@biota_login_required
@require_http_methods(["GET", "POST"])
def notifications_settings_view(request):
    """Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ñ: ÑÐ²Ð¾Ð´ÐºÐ¸ Ð¡ÐÐ£Ð Ð¿Ð¾ ÑÐ°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸Ñ Ð¸ ÑÑÑÐ½ÑÐ¹ ÑÐ¿Ð¸ÑÐ¾Ðº ÑÐ¾ÑÑÑÐ´Ð½Ð¸ÐºÐ¾Ð²."""
    user = biota_user(request)
    if not user or not _is_admin(user):
        messages.error(request, "ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½")
        return redirect("cabinet")

    cfg = biota_db.db_config()
    try:
        employees_full = biota_db.load_employees(cfg)
    except Exception as exc:
        return render(request, "shifts/error.html", {"title": "ÐÑÐ¸Ð±ÐºÐ° ÐÐ", "message": str(exc)})

    from biota_shifts.attendance_summary import (
        SLOT_EVENING,
        SLOT_MORNING,
        format_summary_text,
        load_attendance_summary_from_db,
        send_summary_telegram,
    )
    from biota_shifts.emp_codes import normalize_emp_code
    from biota_shifts.notification_settings import (
        load_notification_settings,
        parse_chat_ids_text,
        save_notification_settings,
        telegram_token_configured,
    )
    from biota_shifts.schedule import employee_label_row
    from biota_shifts.notify_relay import (
        notify_delivery_configured,
        notify_relay_configured,
        resolve_notify_relay_secret,
        resolve_notify_relay_url,
        send_notify_test,
    )
    from biota_shifts.inventory_notify import inventory_notify_enabled, send_inventory_notify_test
    from biota_shifts.telegram_notify import (
        fetch_telegram_bot_username,
        resolve_telegram_bot_token,
        telegram_notify_configured,
    )

    settings = load_notification_settings()
    preview_text = None
    preview_label = ""

    def _delivery_error() -> str:
        return "ÐÐ°ÑÑÑÐ¾Ð¹ÑÐµ Ð´Ð¾ÑÑÐ°Ð²ÐºÑ: URL ÑÐµÑÐ²ÐµÑÐ° Ð±Ð¾ÑÐ° Ð¸ chat_id (Ð¸Ð»Ð¸ ÑÐ¾ÐºÐµÐ½ Telegram)."

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "save":
            blacklist = request.POST.getlist("blacklist_emp_codes")
            save_payload = {
                "enabled": request.POST.get("enabled") == "1",
                "morning_enabled": request.POST.get("morning_enabled") == "1",
                "evening_enabled": request.POST.get("evening_enabled") == "1",
                "morning_time": request.POST.get("morning_time") or "08:20",
                "evening_time": request.POST.get("evening_time") or "20:20",
                "relay_url": (request.POST.get("relay_url") or "").strip(),
                "inventory_notify_enabled": request.POST.get("inventory_notify_enabled") == "1",
                "telegram_chat_ids": parse_chat_ids_text(request.POST.get("telegram_chat_ids") or ""),
                "blacklist_emp_codes": blacklist,
            }
            relay_secret_in = (request.POST.get("relay_secret") or "").strip()
            if relay_secret_in:
                save_payload["relay_secret"] = relay_secret_in
            token_in = (request.POST.get("telegram_bot_token") or "").strip()
            if token_in:
                save_payload["telegram_bot_token"] = token_in
            settings = save_notification_settings(save_payload)
            messages.success(request, "ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ ÑÐ²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ð¹ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ñ.")
            return redirect("cabinet_notifications")

        if action == "test_connection":
            if not notify_delivery_configured(settings):
                messages.error(request, _delivery_error())
            else:
                try:
                    n = send_notify_test(settings)
                    if notify_relay_configured(settings):
                        messages.success(request, "Ð¡Ð²ÑÐ·Ñ Ñ Ð±Ð¾ÑÐ¾Ð¼ OK â Ð¿ÑÐ¾Ð²ÐµÑÑÑÐµ ÑÐµÑÑÐ¾Ð²Ð¾Ðµ ÑÐ¾Ð¾Ð±ÑÐµÐ½Ð¸Ðµ Ð² Telegram.")
                    else:
                        messages.success(request, f"Ð¡Ð¾Ð¾Ð±ÑÐµÐ½Ð¸Ðµ Ð¾ÑÐ¿ÑÐ°Ð²Ð»ÐµÐ½Ð¾ Ð² {n} ÑÐ°Ñ(Ð¾Ð²) Telegram.")
                except Exception as exc:
                    messages.error(request, f"ÐÑÐ¸Ð±ÐºÐ° ÑÐ²ÑÐ·Ð¸: {exc}")
            return redirect("cabinet_notifications")

        if action in ("test_attendance_morning", "test_attendance_evening"):
            slot = SLOT_MORNING if action.endswith("morning") else SLOT_EVENING
            slot_label = "ÑÑÑÐµÐ½Ð½ÑÑ" if slot == SLOT_MORNING else "Ð²ÐµÑÐµÑÐ½ÑÑ"
            if not notify_delivery_configured(settings):
                messages.error(request, _delivery_error())
                return redirect("cabinet_notifications")
            try:
                summary = load_attendance_summary_from_db(slot, settings=settings)
                send_summary_telegram(summary, settings)
                messages.success(request, f"{slot_label.capitalize()} ÑÐ²Ð¾Ð´ÐºÐ° Ð¡ÐÐ£Ð Ð¾ÑÐ¿ÑÐ°Ð²Ð»ÐµÐ½Ð° Ð² Telegram.")
            except Exception as exc:
                messages.error(request, f"ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾ÑÐ¿ÑÐ°Ð²Ð¸ÑÑ ÑÐ²Ð¾Ð´ÐºÑ: {exc}")
            return redirect("cabinet_notifications")

        if action == "test_inventory":
            if not notify_delivery_configured(settings):
                messages.error(request, _delivery_error())
                return redirect("cabinet_notifications")
            if not inventory_notify_enabled(settings):
                messages.error(request, "Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ñ ÑÐºÐ»Ð°Ð´Ð° Ð²ÑÐºÐ»ÑÑÐµÐ½Ñ â Ð²ÐºÐ»ÑÑÐ¸ÑÐµ Ð³Ð°Ð»Ð¾ÑÐºÑ Ð² Ð½Ð°ÑÑÑÐ¾Ð¹ÐºÐ°Ñ.")
                return redirect("cabinet_notifications")
            try:
                actor = user or "admin"
                send_inventory_notify_test(settings, actor=actor)
                messages.success(request, "Ð¢ÐµÑÑÐ¾Ð²Ð¾Ðµ ÑÐ²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ðµ ÑÐºÐ»Ð°Ð´Ð° Ð¾ÑÐ¿ÑÐ°Ð²Ð»ÐµÐ½Ð¾ Ð² Telegram.")
            except Exception as exc:
                messages.error(request, f"ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾ÑÐ¿ÑÐ°Ð²Ð¸ÑÑ: {exc}")
            return redirect("cabinet_notifications")

        if action in ("preview_morning", "preview_evening"):
            slot = SLOT_MORNING if "morning" in action else SLOT_EVENING
            try:
                summary = load_attendance_summary_from_db(slot, settings=settings)
                preview_text = format_summary_text(summary)
                preview_label = "Ð£ÑÑÐµÐ½Ð½ÑÑ ÑÐ²Ð¾Ð´ÐºÐ° Ð¡ÐÐ£Ð" if slot == SLOT_MORNING else "ÐÐµÑÐµÑÐ½ÑÑ ÑÐ²Ð¾Ð´ÐºÐ° Ð¡ÐÐ£Ð"
            except Exception as exc:
                messages.error(request, f"ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ ÑÑÐ¾ÑÐ¼Ð¸ÑÐ¾Ð²Ð°ÑÑ ÑÐ²Ð¾Ð´ÐºÑ: {exc}")
                return redirect("cabinet_notifications")

    blacklist_codes = set(settings.get("blacklist_emp_codes") or [])
    employee_rows = []
    if not employees_full.empty:
        for _, row in employees_full.iterrows():
            code = normalize_emp_code(row.get("emp_code"))
            if not code:
                continue
            employee_rows.append(
                {
                    "emp_code": code,
                    "label": employee_label_row(row),
                    "department_name": str(row.get("department_name") or "").strip() or "â",
                    "blacklisted": code in blacklist_codes,
                }
            )
        employee_rows.sort(key=lambda r: (r["department_name"].lower(), r["label"].lower()))

    chat_ids = settings.get("telegram_chat_ids") or []
    tg_token = resolve_telegram_bot_token(settings)
    relay_url = resolve_notify_relay_url(settings)
    ctx = {
        "settings": settings,
        "employee_rows": employee_rows,
        "telegram_chat_ids_text": "\n".join(chat_ids),
        "relay_url": relay_url,
        "relay_secret_configured": bool(settings.get("relay_secret") or resolve_notify_relay_secret(settings)),
        "notify_delivery_configured": notify_delivery_configured(settings),
        "notify_relay_configured": notify_relay_configured(settings),
        "telegram_configured": telegram_notify_configured(settings),
        "telegram_token_configured": telegram_token_configured(settings),
        "telegram_bot_username": fetch_telegram_bot_username(tg_token) if tg_token and not relay_url else "",
        "inventory_notify_on": inventory_notify_enabled(settings),
        "preview_text": preview_text,
        "preview_label": preview_label,
        "cron_morning": _notify_cron_line(settings.get("morning_time"), "morning"),
        "cron_evening": _notify_cron_line(settings.get("evening_time"), "evening"),
    }
    return render(request, "shifts/cabinet_notifications.html", ctx)


def _icon_form_key(key: str) -> str:
    return key.replace(".", "__")


def _handle_icon_preset_action(request, action: str) -> bool:
    from biota_shifts.hugeicons_map import apply_default_icons_preset, apply_hugeicons_preset, preset_count

    if action == "preset_hugeicons":
        apply_hugeicons_preset()
        messages.success(
            request,
            f"ÐÐ° ÑÐ°Ð¹ÑÐµ Ð²ÐºÐ»ÑÑÐµÐ½Ñ Ð½Ð¾Ð²ÑÐµ Ð¸ÐºÐ¾Ð½ÐºÐ¸ Hugeicons ({preset_count()}). ÐÐ±Ð½Ð¾Ð²Ð¸ÑÐµ ÑÑÑÐ°Ð½Ð¸ÑÑ (Ctrl+F5).",
        )
        return True
    if action == "preset_default":
        apply_default_icons_preset()
        messages.success(request, "ÐÐ° ÑÐ°Ð¹ÑÐµ Ð²ÐºÐ»ÑÑÐµÐ½Ñ ÑÑÐ°Ð½Ð´Ð°ÑÑÐ½ÑÐµ Ð¸ÐºÐ¾Ð½ÐºÐ¸. ÐÐ±Ð½Ð¾Ð²Ð¸ÑÐµ ÑÑÑÐ°Ð½Ð¸ÑÑ (Ctrl+F5).")
        return True
    return False


def _icon_settings_context() -> dict:
    from biota_shifts.hugeicons_map import preset_count
    from biota_shifts.icon_settings import get_icon_preset, load_icon_settings

    preset = get_icon_preset()
    return {
        "icon_preset": preset,
        "icon_preset_is_hugeicons": preset == "hugeicons",
        "hugeicons_preset_count": preset_count(),
        "manual_overrides_count": len((load_icon_settings().get("overrides") or {})),
    }


@biota_login_required
@require_http_methods(["GET", "POST"])
def icons_settings_view(request):
    """Ð¡Ð¿ÑÐ°Ð²Ð¾ÑÐ½Ð¸Ðº Ð¸ÐºÐ¾Ð½Ð¾Ðº ÑÐ°Ð¹ÑÐ°: Ð¿ÑÐ¾ÑÐ¼Ð¾ÑÑ Ð¸ Ð³Ð»Ð¾Ð±Ð°Ð»ÑÐ½ÑÐµ Ð¿ÐµÑÐµÐ¾Ð¿ÑÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ñ."""
    user = biota_user(request)
    if not user or not _is_admin(user):
        messages.error(request, "ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½")
        return redirect("cabinet")

    from biota_shifts.icon_registry import DEFAULT_ICON_REGISTRY, ICON_KINDS
    from biota_shifts.icon_settings import get_effective_overrides, load_icon_settings, save_icon_settings
    from biota_shifts.icons import get_icon, list_icons_grouped

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if _handle_icon_preset_action(request, action):
            return redirect("cabinet_icons")
        if action == "reset":
            save_icon_settings({}, preset="default")
            messages.success(request, "ÐÑÐµ Ð¸ÐºÐ¾Ð½ÐºÐ¸ ÑÐ±ÑÐ¾ÑÐµÐ½Ñ Ðº Ð·Ð½Ð°ÑÐµÐ½Ð¸ÑÐ¼ Ð¿Ð¾ ÑÐ¼Ð¾Ð»ÑÐ°Ð½Ð¸Ñ.")
        elif action == "save":
            overrides: dict[str, dict] = {}
            for key in DEFAULT_ICON_REGISTRY:
                fk = _icon_form_key(key)
                kind = (request.POST.get(f"icon_{fk}_kind") or "").strip()
                value = (request.POST.get(f"icon_{fk}_value") or "").strip()
                if kind in ICON_KINDS and value:
                    overrides[key] = {"kind": kind, "value": value}
            save_icon_settings(overrides)
            messages.success(request, "ÐÐºÐ¾Ð½ÐºÐ¸ ÑÐ¾ÑÑÐ°Ð½ÐµÐ½Ñ. ÐÐ±Ð½Ð¾Ð²Ð¸ÑÐµ ÑÑÑÐ°Ð½Ð¸ÑÑ ÑÐ°Ð¹ÑÐ° (Ctrl+F5).")
        return redirect("cabinet_icons")

    icon_rows = []
    for key in sorted(DEFAULT_ICON_REGISTRY.keys()):
        spec = get_icon(key)
        default = DEFAULT_ICON_REGISTRY[key]
        icon_rows.append(
            {
                "key": key,
                "form_key": _icon_form_key(key),
                "label": spec["label"],
                "group": spec["group"],
                "kind": spec["kind"],
                "value": spec["value"],
                "default_kind": default["kind"],
                "default_value": default["value"],
                "is_overridden": spec["kind"] != default["kind"] or spec["value"] != default["value"],
            }
        )

    ctx = {
        "icon_groups": list_icons_grouped(),
        "icon_rows": icon_rows,
        "icon_kinds": ICON_KINDS,
        "overrides_count": len(get_effective_overrides()),
        **_icon_settings_context(),
    }
    return render(request, "shifts/cabinet_icons.html", ctx)


@biota_login_required
@require_http_methods(["GET", "POST"])
def icons_preview_view(request):
    """ÐÑÐµÐ²ÑÑ Ð½Ð¾Ð²ÑÑ SVG Ð¸Ð· Figma (ÐºÐ°Ð½Ð´Ð¸Ð´Ð°ÑÑ) ÑÑÐ´Ð¾Ð¼ Ñ ÑÐµÐºÑÑÐ¸Ð¼Ð¸ Ð¸ÐºÐ¾Ð½ÐºÐ°Ð¼Ð¸."""
    user = biota_user(request)
    if not user or not _is_admin(user):
        messages.error(request, "ÐÐ¾ÑÑÑÐ¿ Ð·Ð°Ð¿ÑÐµÑÐµÐ½")
        return redirect("cabinet")

    from biota_shifts.icon_candidates import (
        apply_all_candidates,
        candidates_count,
        figma_inventory,
        list_preview_rows,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if _handle_icon_preset_action(request, action):
            return redirect("cabinet_icons_preview")
        if action == "apply":
            n = apply_all_candidates()
            if n:
                messages.success(
                    request,
                    f"ÐÑÐ¸Ð¼ÐµÐ½ÐµÐ½Ð¾ {n} Ð¸ÐºÐ¾Ð½Ð¾Ðº. ÐÐ±Ð½Ð¾Ð²Ð¸ÑÐµ ÑÑÑÐ°Ð½Ð¸ÑÑ ÑÐ°Ð¹ÑÐ° (Ctrl+F5).",
                )
            else:
                messages.warning(request, "ÐÐµÑ SVG-ÐºÐ°Ð½Ð´Ð¸Ð´Ð°ÑÐ¾Ð² Ð² static/icons/candidates/.")
        return redirect("cabinet_icons_preview")

    rows = list_preview_rows()
    ctx = {
        "preview_rows": rows,
        "candidates_count": candidates_count(),
        "figma_rows": figma_inventory(),
        "total_icons": len(rows),
        **_icon_settings_context(),
    }
    return render(request, "shifts/cabinet_icons_preview.html", ctx)


@biota_login_required
@require_http_methods(["GET", "POST"])
def visual_warehouse_settings_view(request):
    """Сроки актуальности инвентаризации на визуальном складе (цвета дат)."""
    user = biota_user(request)
    if not user or not _is_admin(user):
        messages.error(request, "Доступ запрещен")
        return redirect("cabinet")

    from biota_shifts.visual_warehouse_settings import (
        load_visual_warehouse_settings,
        save_visual_warehouse_settings,
    )

    settings = load_visual_warehouse_settings()
    if request.method == "POST":
        settings = save_visual_warehouse_settings(
            {
                "audit_ok_days": request.POST.get("audit_ok_days"),
                "audit_warn_days": request.POST.get("audit_warn_days"),
            }
        )
        messages.success(request, "Сроки инвентаризации визуального склада сохранены.")
        return redirect("cabinet_visual_warehouse")

    return render(
        request,
        "shifts/cabinet_visual_warehouse.html",
        {"vw_settings": settings},
    )
