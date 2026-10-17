"""Личный кабинет: профиль и пароль (пользователи), имя и права (админ) — логика как в Streamlit."""
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
    _delete_registered_users,
    _purge_pending_registrations,
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
                    messages.success(request, "Права сохранены.")
                    if old_inv != inv_flag:
                        InventoryStockEvent.objects.create(
                            actor_username=user,
                            event_type=InventoryStockEvent.EVENT_PRIVILEGE,
                            summary=(
                                f"Учётная запись «{target}»: право редактирования и удаления на складе "
                                f"{'включено' if inv_flag else 'выключено'}"
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
                    messages.success(request, f"Регистрация подтверждена: {target}")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
            if action == "admin_purge_pending_registrations":
                n, _logins = _purge_pending_registrations(all_pending=True)
                if n:
                    messages.success(request, f"Удалено ожидающих регистраций: {n}.")
                else:
                    messages.info(request, "Нет учётных записей, ожидающих подтверждения.")
                return redirect("cabinet")
            if action == "admin_clear_register_security_log":
                from shifts.register_security_log import clear_register_security_log

                if clear_register_security_log():
                    messages.success(request, "Журнал атак на регистрацию очищен.")
                else:
                    messages.error(request, "Не удалось очистить журнал.")
                return redirect(f"{reverse('cabinet')}#cabinet-bot-watch")
            if action == "admin_user_names":
                target = (request.POST.get("names_login") or "").strip()
                first = (request.POST.get("first_name") or "").strip()
                last = (request.POST.get("last_name") or "").strip()
                ok, err = _update_registered_names(target, first, last)
                if ok:
                    label = account_label_for_username(target)
                    messages.success(
                        request,
                        f"Имя сохранено: {label}" if label != target else f"Имя для «{target}» очищено.",
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
                    messages.success(request, f"Учётная запись удалена: {target}")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
            if action == "admin_delete_users":
                targets = request.POST.getlist("delete_login")
                n, removed, errs = _delete_registered_users(targets)
                if n:
                    preview = ", ".join(removed[:8])
                    more = f" и ещё {n - 8}" if n > 8 else ""
                    messages.success(request, f"Удалено учёток: {n} ({preview}{more}).")
                if errs:
                    messages.error(request, "; ".join(errs[:5]))
                elif not n:
                    messages.warning(request, "Не выбран ни один пользователь.")
                return redirect(f"{reverse('cabinet')}#cabinet-privileges")
        else:
            if action == "profile":
                first = (request.POST.get("first_name") or "").strip()
                last = (request.POST.get("last_name") or "").strip()
                em = request.POST.get("email") or ""
                key = _canonical_store_username(user)
                if not key:
                    messages.error(request, "Профиль не найден.")
                else:
                    ok, err = _update_registered_profile(
                        key, email=em, first_name=first, last_name=last
                    )
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
        from django.conf import settings as dj_settings

        max_age = int(getattr(dj_settings, "BIOTA_PENDING_REG_MAX_AGE_DAYS", 7) or 0)
        if max_age > 0:
            _purge_pending_registrations(all_pending=False, max_age_days=max_age)

        ctx["system_health"] = collect_system_health()
        from shifts.register_security_log import build_register_attack_dashboard

        ctx["register_attack"] = build_register_attack_dashboard()
        priv_store = _load_users_store()
        ctx["pending_registrations"] = sorted(
            [
                {
                    "login": k,
                    "email": (v.get("email") or "").strip(),
                    "email_verified": bool((v.get("email") or "").strip())
                    and bool(v.get("email_verified", False)),
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
            USER_ROLE_MANAGER: "Руководитель",
            USER_ROLE_EXECUTOR: "Исполнитель (только просмотр/скачивание)",
        }
        ctx["priv_nav"] = _pn
        _ndf = _nav_department_filters_map(pr) if ctx["priv_selected"] else {}
        raw_ndf = pr.get("nav_dep_filters") if isinstance(pr.get("nav_dep_filters"), dict) else {}
        ctx["priv_stock_manage"] = bool(pr.get("inventory_stock_manage"))
        ctx["priv_machines_quick_edit"] = bool(pr.get("machines_quick_edit"))
        ctx["priv_nav_rows"] = []
        for k in NAV_KEYS:
            sel_deps = [d for d in (_ndf.get(k) or []) if d in dep_opts]
            has_dept_picker = bool(dep_opts and k not in NAV_KEYS_NO_DEPT_FILTER)
            extra_toggle = None
            if k == "inventory":
                extra_toggle = {
                    "field": "priv_inventory_stock_manage",
                    "label": "Редактирование склада",
                    "on": ctx["priv_stock_manage"],
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
        ctx["profile_created"] = rec.get("created_at") or "—"
        ctx["profile_access"] = _access_scope_description(rec)
        role = user_role_for_username(user)
        ctx["profile_role"] = "исполнитель" if role == USER_ROLE_EXECUTOR else "руководитель"
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
    from django.http import Http404
    raise Http404("Раздел удалён")


@biota_login_required
@require_http_methods(["GET"])
def schedule_backup_download(request, filename: str):
    from django.http import Http404
    raise Http404("Раздел удалён")


@biota_login_required
@require_http_methods(["GET", "POST"])
def inventory_backups_view(request):
    """Управление резервными копиями склада (JSON)."""
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
        messages.error(request, "Доступ запрещен")
        return redirect("/cabinet/")

    backups_dir = INVENTORY_BACKUP_DIR

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "upload":
            uploaded_file = request.FILES.get("backup_file")
            if not uploaded_file:
                messages.error(request, "Выберите файл для загрузки")
                return redirect("/cabinet/inventory-backups/")

            if not uploaded_file.name.endswith(".json"):
                messages.error(request, "Файл должен быть в формате .json")
                return redirect("/cabinet/inventory-backups/")

            try:
                raw = uploaded_file.read()
                parse_inventory_backup_bytes(raw)
                safe_name = uploaded_file.name
                if not is_safe_backup_filename(safe_name):
                    safe_name = backup_filename_now()
                backup_path = backups_dir / safe_name
                backup_path.write_bytes(raw)
                messages.success(request, f"Резервная копия загружена: {safe_name}")
            except InventoryBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"Ошибка при загрузке: {exc}")

            return redirect("/cabinet/inventory-backups/")

        if action == "backup_now":
            try:
                path = write_backup_file(backups_dir)
                payload = export_inventory_payload()
                tools_n = len(payload["tool_items"])
                messages.success(
                    request,
                    f"Резервная копия склада создана: {path.name} ({tools_n} позиций инструмента)",
                )
            except Exception as exc:
                messages.error(request, f"Ошибка при создании резервной копии: {exc}")

            return redirect("/cabinet/inventory-backups/")

        if action == "restore":
            backup_filename = request.POST.get("backup_filename", "").strip()
            if not is_safe_backup_filename(backup_filename):
                messages.error(request, "Некорректное имя файла")
                return redirect("/cabinet/inventory-backups/")

            backup_path = backups_dir / backup_filename
            if not backup_path.exists() or not backup_path.is_file():
                messages.error(request, "Резервная копия не найдена")
                return redirect("/cabinet/inventory-backups/")

            try:
                write_backup_file(backups_dir, filename=f"inventory_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                raw = backup_path.read_bytes()
                payload = parse_inventory_backup_bytes(raw)
                stats = restore_inventory_from_payload(payload)
                messages.success(
                    request,
                    "Склад восстановлен из резервной копии: "
                    f"{stats['tools']} позиций, {stats['movements']} движений, "
                    f"{stats['purchases']} заявок на закупку.",
                )
            except InventoryBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"Ошибка при восстановлении: {exc}")

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
    """Скачать резервную копию склада на диск / флешку."""
    from shifts.inventory_backup import is_safe_backup_filename

    if not _is_admin(biota_user(request)):
        return HttpResponse("Доступ запрещен", status=403)

    if not is_safe_backup_filename(filename):
        return HttpResponse("Некорректное имя файла", status=400)

    backup_path = INVENTORY_BACKUP_DIR / filename
    if not backup_path.exists() or not backup_path.is_file():
        return HttpResponse("Файл не найден", status=404)

    with open(backup_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response



@biota_login_required
@require_http_methods(["GET", "POST"])
def regulations_backups_view(request):
    from django.http import Http404
    raise Http404("Раздел удалён")


@biota_login_required
@require_http_methods(["GET"])
def regulations_backup_download(request, filename: str):
    from django.http import Http404
    raise Http404("Раздел удалён")




@biota_login_required
@require_http_methods(["GET", "POST"])
def notifications_settings_view(request):
    """Уведомления склада (Telegram / relay). Сводки СКУД удалены."""
    user = biota_user(request)
    if not user or not _is_admin(user):
        messages.error(request, "Доступ запрещен")
        return redirect("cabinet")

    from biota_shifts.notification_settings import (
        load_notification_settings,
        notify_outbound_enabled,
        parse_chat_ids_text,
        save_notification_settings,
        telegram_token_configured,
    )
    from biota_shifts.notify_relay import (
        notify_delivery_configured,
        notify_relay_configured,
        resolve_notify_relay_secret,
        resolve_notify_relay_url,
        send_notify_test,
    )
    from biota_shifts.inventory_notify import inventory_notify_enabled, send_inventory_notify_test
    from biota_shifts.telegram_notify import telegram_notify_configured

    settings = load_notification_settings()

    def _delivery_error() -> str:
        return "Настройте доставку: URL сервера бота и chat_id (или токен Telegram)."

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "save":
            save_payload = {
                "enabled": request.POST.get("enabled") == "1",
                "morning_enabled": False,
                "evening_enabled": False,
                "morning_time": request.POST.get("morning_time") or "08:20",
                "evening_time": request.POST.get("evening_time") or "20:20",
                "relay_url": (request.POST.get("relay_url") or "").strip(),
                "inventory_notify_enabled": request.POST.get("inventory_notify_enabled") == "1",
                "telegram_chat_ids": parse_chat_ids_text(request.POST.get("telegram_chat_ids") or ""),
                "blacklist_emp_codes": [],
            }
            relay_secret_in = (request.POST.get("relay_secret") or "").strip()
            if relay_secret_in:
                save_payload["relay_secret"] = relay_secret_in
            token_in = (request.POST.get("telegram_bot_token") or "").strip()
            if token_in:
                save_payload["telegram_bot_token"] = token_in
            settings = save_notification_settings(save_payload)
            messages.success(request, "Настройки уведомлений сохранены.")
            return redirect("cabinet_notifications")
        if action == "test_connection":
            if not notify_delivery_configured(settings):
                messages.error(request, _delivery_error())
            else:
                try:
                    n = send_notify_test(settings)
                    if notify_relay_configured(settings):
                        messages.success(request, "Связь с ботом OK — проверьте тестовое сообщение в Telegram.")
                    else:
                        messages.success(request, f"Сообщение отправлено в {n} чат(ов) Telegram.")
                except Exception as exc:
                    messages.error(request, f"Ошибка связи: {exc}")
            return redirect("cabinet_notifications")
        if action == "test_inventory":
            if not notify_delivery_configured(settings):
                messages.error(request, _delivery_error())
                return redirect("cabinet_notifications")
            if not inventory_notify_enabled(settings):
                messages.error(request, "Уведомления склада выключены — включите галочку в настройках.")
                return redirect("cabinet_notifications")
            try:
                send_inventory_notify_test(settings, actor=user or "admin")
                messages.success(request, "Тестовое уведомление склада отправлено в Telegram.")
            except Exception as exc:
                messages.error(request, f"Не удалось отправить: {exc}")
            return redirect("cabinet_notifications")

    chat_ids = settings.get("telegram_chat_ids") or []
    ctx = {
        "settings": settings,
        "employee_rows": [],
        "telegram_chat_ids_text": "\n".join(chat_ids),
        "relay_url": resolve_notify_relay_url(settings),
        "relay_secret_configured": bool(settings.get("relay_secret") or resolve_notify_relay_secret(settings)),
        "notify_delivery_configured": notify_delivery_configured(settings),
        "notify_relay_configured": notify_relay_configured(settings),
        "telegram_configured": telegram_notify_configured(settings),
        "telegram_token_configured": telegram_token_configured(settings),
        "telegram_bot_username": "",
        "notify_outbound_enabled": notify_outbound_enabled(),
        "inventory_notify_on": inventory_notify_enabled(settings),
        "preview_text": None,
        "preview_label": "",
        "cron_morning": "",
        "cron_evening": "",
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
            f"На сайте включены новые иконки Hugeicons ({preset_count()}). Обновите страницы (Ctrl+F5).",
        )
        return True
    if action == "preset_default":
        apply_default_icons_preset()
        messages.success(request, "На сайте включены стандартные иконки. Обновите страницы (Ctrl+F5).")
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
    """Справочник иконок сайта: просмотр и глобальные переопределения."""
    user = biota_user(request)
    if not user or not _is_admin(user):
        messages.error(request, "Доступ запрещен")
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
            messages.success(request, "Все иконки сброшены к значениям по умолчанию.")
        elif action == "save":
            overrides: dict[str, dict] = {}
            for key in DEFAULT_ICON_REGISTRY:
                fk = _icon_form_key(key)
                kind = (request.POST.get(f"icon_{fk}_kind") or "").strip()
                value = (request.POST.get(f"icon_{fk}_value") or "").strip()
                if kind in ICON_KINDS and value:
                    overrides[key] = {"kind": kind, "value": value}
            save_icon_settings(overrides)
            messages.success(request, "Иконки сохранены. Обновите страницы сайта (Ctrl+F5).")
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
    """Превью новых SVG из Figma (кандидаты) рядом с текущими иконками."""
    user = biota_user(request)
    if not user or not _is_admin(user):
        messages.error(request, "Доступ запрещен")
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
                    f"Применено {n} иконок. Обновите страницы сайта (Ctrl+F5).",
                )
            else:
                messages.warning(request, "Нет SVG-кандидатов в static/icons/candidates/.")
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
