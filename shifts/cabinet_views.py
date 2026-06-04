"""Личный кабинет: профиль и пароль (пользователи), имя и права (админ) — логика как в Streamlit."""
from datetime import datetime
from pathlib import Path
import shutil

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse

from biota_shifts import db as biota_db
from biota_shifts.config import INVENTORY_BACKUP_DIR, REGULATIONS_BACKUP_DIR, SCHEDULE_DIR
from biota_shifts.auth import (
    ADMIN_USERNAME,
    NAV_KEYS,
    NAV_LABELS_RU,
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
    _resolve_registered_user,
    _set_user_privileges,
    _update_registered_profile,
    nav_permissions_for_user,
    user_role_for_username,
)
from shifts.models import InventoryStockEvent
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
                if dep_opts:
                    nav_dep_filters: dict[str, list[str]] = {}
                    for k in NAV_KEYS:
                        if not nav_map.get(k, True):
                            continue
                        if k in ("products", "machines") or k in NAV_KEYS_NO_DEPT_FILTER:
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
                return redirect("cabinet")
            if action == "admin_approve_registration":
                target = (request.POST.get("approve_login") or "").strip()
                ok, err = _approve_registration(target)
                if ok:
                    messages.success(request, f"Регистрация подтверждена: {target}")
                else:
                    messages.error(request, err)
                return redirect("cabinet")
            if action == "admin_delete_user":
                target = (request.POST.get("delete_login") or "").strip()
                ok, err = _delete_registered_user(target)
                if ok:
                    messages.success(request, f"Учётная запись удалена: {target}")
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
            [
                {
                    "login": k,
                    "email": (v.get("email") or "").strip(),
                    "email_verified": not (v.get("email") or "").strip()
                    or bool(v.get("email_verified", True)),
                }
                for k, v in priv_store.items()
                if not v.get("approved", True)
            ],
            key=lambda x: str(x["login"]).lower(),
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
        ctx["priv_stock_manage"] = bool(pr.get("inventory_stock_manage"))
        ctx["priv_machines_quick_edit"] = bool(pr.get("machines_quick_edit"))
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
                    "no_dept_filter": k in NAV_KEYS_NO_DEPT_FILTER,
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
        ctx["profile_email_verified"] = not (rec.get("email") or "").strip() or bool(
            rec.get("email_verified", True)
        )
        ctx["profile_missing"] = not bool(rec)

    return render(request, "shifts/cabinet.html", ctx)


@biota_login_required
@require_http_methods(["GET", "POST"])
def schedule_backups_view(request):
    """Управление резервными копиями графиков."""
    # Проверяем, что пользователь админ
    if not _is_admin(biota_user(request)):
        messages.error(request, "Доступ запрещен")
        return redirect("/cabinet/")

    backups_dir = SCHEDULE_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        # Загрузить файл резервной копии
        if action == "upload":
            uploaded_file = request.FILES.get("backup_file")
            if not uploaded_file:
                messages.error(request, "Выберите файл для загрузки")
                return redirect("/cabinet/backups/")

            if not uploaded_file.name.endswith(".xlsx"):
                messages.error(request, "Файл должен быть в формате .xlsx")
                return redirect("/cabinet/backups/")

            try:
                # Сохраняем загруженный файл в папку бэкапов
                backup_path = backups_dir / uploaded_file.name
                with open(backup_path, "wb") as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

                messages.success(request, f"Резервная копия загружена: {uploaded_file.name}")
            except Exception as exc:
                messages.error(request, f"Ошибка при загрузке: {exc}")

            return redirect("/cabinet/backups/")

        # Создать резервную копию всех графиков
        elif action == "backup_all":
            try:
                # Находим все файлы schedule_*.xlsx в основной папке
                main_dir = SCHEDULE_DIR
                backup_count = 0

                for schedule_file in main_dir.glob("schedule_*.xlsx"):
                    if schedule_file.is_file():
                        # Создаем имя для бэкапа с временной меткой
                        now = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_name = f"{schedule_file.stem}_{now}.xlsx"
                        backup_path = backups_dir / backup_name

                        # Копируем файл
                        shutil.copy2(schedule_file, backup_path)
                        backup_count += 1

                messages.success(request, f"Создано {backup_count} резервных копий графиков")
            except Exception as exc:
                messages.error(request, f"Ошибка при создании резервных копий: {exc}")

            return redirect("/cabinet/backups/")

        # Восстановить из резервной копии
        elif action == "restore":
            backup_filename = request.POST.get("backup_filename", "").strip()
            if not backup_filename or ".." in backup_filename:
                messages.error(request, "Некорректное имя файла")
                return redirect("/cabinet/backups/")

            backup_path = backups_dir / backup_filename
            if not backup_path.exists() or not backup_path.is_file():
                messages.error(request, "Резервная копия не найдена")
                return redirect("/cabinet/backups/")

            try:
                # Извлекаем имя исходного файла (удаляем временную метку)
                # schedule_2026_05_20260521_101450.xlsx -> schedule_2026_05.xlsx
                parts = backup_filename.replace(".xlsx", "").split("_")
                if len(parts) >= 4:  # schedule, year, month, и дата
                    original_name = f"{parts[0]}_{parts[1]}_{parts[2]}.xlsx"
                else:
                    original_name = backup_filename

                original_path = SCHEDULE_DIR / original_name

                # Копируем бэкап обратно
                shutil.copy2(backup_path, original_path)
                messages.success(request, f"График восстановлен из резервной копии: {backup_filename}")
            except Exception as exc:
                messages.error(request, f"Ошибка при восстановлении: {exc}")

            return redirect("/cabinet/backups/")

    # Получить список резервных копий, отсортированный по дате (новые сверху)
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
    """Скачать резервную копию графика."""
    from biota_shifts.config import SCHEDULE_DIR

    # Проверяем, что пользователь админ
    if not _is_admin(biota_user(request)):
        return HttpResponse("Доступ запрещен", status=403)

    # Проверяем имя файла (защита от directory traversal)
    if ".." in filename or "/" in filename or "\\" in filename:
        return HttpResponse("Некорректное имя файла", status=400)

    backup_path = SCHEDULE_DIR / "backups" / filename

    if not backup_path.exists() or not backup_path.is_file():
        return HttpResponse("Файл не найден", status=404)

    # Отправляем файл
    with open(backup_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


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
    """Управление резервными копиями регламентов (JSON)."""
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
        messages.error(request, "Доступ запрещен")
        return redirect("/cabinet/")

    backups_dir = REGULATIONS_BACKUP_DIR

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "upload":
            uploaded_file = request.FILES.get("backup_file")
            if not uploaded_file:
                messages.error(request, "Выберите файл для загрузки")
                return redirect("/cabinet/regulations-backups/")

            if not uploaded_file.name.endswith(".json"):
                messages.error(request, "Файл должен быть в формате .json")
                return redirect("/cabinet/regulations-backups/")

            try:
                raw = uploaded_file.read()
                parse_regulations_backup_bytes(raw)
                safe_name = uploaded_file.name
                if not is_safe_backup_filename(safe_name):
                    safe_name = backup_filename_now()
                backup_path = backups_dir / safe_name
                backup_path.write_bytes(raw)
                messages.success(request, f"Резервная копия загружена: {safe_name}")
            except RegulationsBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"Ошибка при загрузке: {exc}")

            return redirect("/cabinet/regulations-backups/")

        if action == "backup_all":
            try:
                path = write_backup_file(backups_dir)
                payload = export_regulations_payload()
                plans_n = len(payload["regulation_plans"])
                messages.success(
                    request,
                    f"Резервная копия регламентов создана: {path.name} ({plans_n} записей)",
                )
            except Exception as exc:
                messages.error(request, f"Ошибка при создании резервных копий: {exc}")

            return redirect("/cabinet/regulations-backups/")

        if action == "restore":
            backup_filename = request.POST.get("backup_filename", "").strip()
            if not is_safe_backup_filename(backup_filename):
                messages.error(request, "Некорректное имя файла")
                return redirect("/cabinet/regulations-backups/")

            backup_path = backups_dir / backup_filename
            if not backup_path.exists() or not backup_path.is_file():
                messages.error(request, "Резервная копия не найдена")
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
                    f"Регламенты восстановлены из резервной копии: {stats['plans']} записей.",
                )
            except RegulationsBackupError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"Ошибка при восстановлении: {exc}")

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
    """Скачать резервную копию регламентов."""
    from regulations.regulations_backup import is_safe_backup_filename

    if not _is_admin(biota_user(request)):
        return HttpResponse("Доступ запрещен", status=403)

    if not is_safe_backup_filename(filename):
        return HttpResponse("Некорректное имя файла", status=400)

    backup_path = REGULATIONS_BACKUP_DIR / filename
    if not backup_path.exists() or not backup_path.is_file():
        return HttpResponse("Файл не найден", status=404)

    with open(backup_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
