from datetime import date
from decimal import Decimal, InvalidOperation
import json

from django.contrib import messages
from django.db import transaction
from django.db.models import F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from biota_shifts import db as biota_db
from biota_shifts.auth import _is_admin, employees_df_for_nav, nav_permissions_for_user
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts.emp_codes import normalize_emp_code
from biota_shifts.schedule import employee_label_row
from .auth_utils import (
    biota_login_required,
    biota_user,
    inventory_route_nav_access_required,
    write_permission_required,
)
from .models import (
    CENTER_DRILL_ANGLES,
    COUNTERSINK_ANGLES,
    COUNTERSINK_TYPES,
    COATING_TYPES,
    CountersinkSpec,
    DrillSpec,
    END_MILL_TYPES,
    CenterDrillSpec,
    EndMillSpec,
    StockMovement,
    TapSpec,
    ToolItem,
    PurchaseRequest,
    EmployeeDefectRecord,
    EmployeePayrollMonthStatus,
    TAP_HOLE_TYPES,
    TAP_TOOL_TYPES,
    THREAD_STANDARDS,
    TOOL_MATERIAL_TYPES,
    WORK_MATERIAL_TYPES,
    PURCHASE_STATUSES,
)


def _distinct_text_values(qs, field_name: str):
    return [v for v in qs.exclude(**{f"{field_name}__isnull": True}).values_list(field_name, flat=True).distinct().order_by(field_name) if v]


def _distinct_numeric_values(qs, field_name: str):
    return list(
        qs.exclude(**{f"{field_name}__isnull": True}).values_list(field_name, flat=True).distinct().order_by(field_name)
    )


def _to_decimal(val: str, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal((val or "").strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return default


def _to_int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _to_decimal_or_none(val: str):
    parsed = _to_decimal(val, Decimal("-1"))
    return parsed if parsed >= 0 else None


def _to_int_or_none(val: str):
    parsed = _to_int(val, -1)
    return parsed if parsed >= 0 else None


def _fmt_unknown(v, prefix: str = "") -> str:
    if v is None or str(v) == "":
        return f"{prefix}неизв."
    return f"{prefix}{v}"


def _build_end_mill_name(diameter_mm, flutes_count, tool_material: str, work_material: str) -> str:
    tool_mat_label = dict(TOOL_MATERIAL_TYPES).get(tool_material, tool_material)
    work_mat_label = dict(WORK_MATERIAL_TYPES).get(work_material, work_material)
    parts = [f"Фреза D{_fmt_unknown(diameter_mm)}", f"{_fmt_unknown(flutes_count)} кром."]
    if tool_mat_label:
        parts.append(tool_mat_label)
    if work_mat_label:
        parts.append(f"по {work_mat_label}")
    return " / ".join(parts)


def _build_tap_name(size_label: str, thread_standard: str, tap_type: str, hole_type: str) -> str:
    std_map = dict(THREAD_STANDARDS)
    ttype_map = dict(TAP_TOOL_TYPES)
    htype_map = dict(TAP_HOLE_TYPES)
    return f"{size_label} / {std_map.get(thread_standard, thread_standard)} / {ttype_map.get(tap_type, tap_type)} / {htype_map.get(hole_type, hole_type)}"


def _build_center_drill_name(diameter_mm, angle_deg: str) -> str:
    return f"Центровка D{_fmt_unknown(diameter_mm)} / {angle_deg or '60'}°"


def _build_countersink_name(countersink_type: str, diameter_mm, angle_deg: str, size_label: str) -> str:
    type_label = dict(COUNTERSINK_TYPES).get(countersink_type, countersink_type or "машинный")
    size_part = f" / {size_label}" if size_label else ""
    return f"Зенкер {type_label} D{_fmt_unknown(diameter_mm)} / {angle_deg or '90'}°{size_part}"


def _build_drill_name(diameter_mm, overall_length_mm, cutting_length_mm, angle_deg) -> str:
    return (
        f"Сверло D{_fmt_unknown(diameter_mm)} / "
        f"L{_fmt_unknown(overall_length_mm)} / "
        f"Lc{_fmt_unknown(cutting_length_mm)} / "
        f"{_fmt_unknown(angle_deg)}°"
    )


@biota_login_required
@inventory_route_nav_access_required
@write_permission_required
@require_http_methods(["GET", "POST"])
def inventory_view(request):
    action = request.POST.get("action") if request.method == "POST" else ""
    panel = (request.GET.get("panel") or "stock").strip()
    if panel not in {"stock", "history", "issue", "arrival", "issue_outcome", "purchases", "defects", "payroll", "employees"}:
        panel = "stock"

    username = biota_user(request) or "Неизвестный пользователь"
    is_admin_user = _is_admin(username)
    perms = nav_permissions_for_user(username)
    can_defects = perms.get("defects", True)
    can_payroll = perms.get("payroll", True)
    can_employees = perms.get("employees", True)
    if is_admin_user:
        can_defects = can_payroll = can_employees = True
    if panel == "defects" and not can_defects:
        messages.warning(request, "У вас нет доступа к разделу «Учёт брака».")
        return redirect(reverse("inventory"))
    if panel == "payroll" and not can_payroll:
        messages.warning(request, "У вас нет доступа к разделу «Расчёт ЗП».")
        return redirect(reverse("inventory"))
    if panel == "employees" and not can_employees:
        messages.warning(request, "У вас нет доступа к разделу «Сотрудники».")
        return redirect(reverse("inventory"))
    employee_options = []
    employee_department_map = {}
    employee_table_rows: list[dict] = []
    if panel == "defects" or action in {"create_defect_record", "update_defect_record"}:
        try:
            cfg = biota_db.db_config()
            employees_df = employees_df_for_nav(username, "defects", biota_db.load_employees(cfg))
            if not employees_df.empty:
                prepared: list[tuple[str, str, str, str]] = []
                base_counts: dict[str, int] = {}
                for _, row in employees_df.iterrows():
                    base_label = employee_label_row(row)
                    if not base_label or base_label == "Без имени":
                        continue
                    dept = str(row.get("department_name") or "").strip()
                    last = str(row.get("last_name") or "").strip()
                    first = str(row.get("first_name") or "").strip()
                    full_name = " ".join(p for p in (last, first) if p)
                    emp_code = str(row.get("emp_code") or "").strip()
                    prepared.append((base_label, full_name, emp_code, dept))
                    base_counts[base_label] = base_counts.get(base_label, 0) + 1

                for base_label, full_name, emp_code, dept in prepared:
                    label = base_label
                    if base_counts.get(base_label, 0) > 1:
                        if full_name and full_name != base_label:
                            label = f"{base_label} ({full_name})"
                        elif emp_code:
                            label = f"{base_label} [{emp_code}]"
                    # На случай редких коллизий (однофамильцы с одинаковым именем)
                    if label in employee_department_map and emp_code:
                        label = f"{label} [{emp_code}]"
                    if label not in employee_department_map:
                        employee_department_map[label] = dept
                employee_options = sorted(employee_department_map.keys())
        except Exception:
            employee_options = []
            employee_department_map = {}

    if panel == "employees":
        try:
            cfg = biota_db.db_config()
            emp_df = employees_df_for_nav(username, "employees", biota_db.load_employees(cfg))
            if not emp_df.empty:
                rows: list[dict] = []
                for _, row in emp_df.iterrows():
                    emp_code = str(row.get("emp_code") or "").strip()
                    if not emp_code:
                        continue
                    rows.append(
                        {
                            "emp_code": emp_code,
                            "label": (employee_label_row(row) or "").strip() or "—",
                            "last_name": str(row.get("last_name") or "").strip(),
                            "first_name": str(row.get("first_name") or "").strip(),
                            "department_name": str(row.get("department_name") or "").strip(),
                            "position_name": str(row.get("position_name") or "").strip(),
                            "area_name": str(row.get("area_name") or "").strip(),
                        }
                    )
                employee_table_rows = sorted(rows, key=lambda r: (r["label"].lower(), r["emp_code"]))
        except Exception:
            employee_table_rows = []

    if action == "add_end_mill":
        diameter_mm = _to_decimal(request.POST.get("diameter_mm"), Decimal("0"))
        overall_length_mm = _to_decimal(request.POST.get("overall_length_mm"), Decimal("0"))
        cutting_length_mm = _to_decimal(request.POST.get("cutting_length_mm"), Decimal("0"))
        flutes_count = _to_int(request.POST.get("flutes_count"), 0)
        quantity = _to_int(request.POST.get("quantity"), 0)
        tool_material = (request.POST.get("tool_material") or "").strip()
        coating_type = (request.POST.get("coating_type") or "none").strip()
        work_material = (request.POST.get("work_material") or "").strip()
        main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        if diameter_mm <= 0 or overall_length_mm <= 0 or cutting_length_mm <= 0 or flutes_count <= 0 or quantity <= 0:
            messages.error(request, "Для фрезы заполните параметры корректно (числа больше нуля).")
            return redirect("inventory")
        with transaction.atomic():
            tool = ToolItem.objects.create(
                category="end_mill",
                name=_build_end_mill_name(diameter_mm, flutes_count, tool_material, work_material),
                tool_material=tool_material,
                coating_type=coating_type,
                work_material=work_material,
                main_diameter_mm=main_diameter_mm,
                quantity=quantity,
            )
            EndMillSpec.objects.create(
                tool=tool,
                diameter_mm=diameter_mm,
                overall_length_mm=overall_length_mm,
                cutting_length_mm=cutting_length_mm,
                flutes_count=flutes_count,
            )
        messages.success(request, "Фреза добавлена в склад.")
        return redirect("inventory")

    if action == "add_tap":
        thread_standard = (request.POST.get("thread_standard") or "metric").strip()
        size_label = (request.POST.get("size_label") or "").strip()
        pitch_mm = _to_decimal(request.POST.get("pitch_mm"), Decimal("0"))
        tpi = _to_int(request.POST.get("tpi"), 0) or None
        hole_type = (request.POST.get("hole_type") or "any").strip()
        tap_type = (request.POST.get("tap_type") or "cutting").strip()
        overall_length_mm = _to_decimal(request.POST.get("overall_length_mm"), Decimal("0"))
        cutting_length_mm = _to_decimal(request.POST.get("cutting_length_mm"), Decimal("0"))
        quantity = _to_int(request.POST.get("quantity"), 0)
        tool_material = (request.POST.get("tool_material") or "").strip()
        coating_type = (request.POST.get("coating_type") or "none").strip()
        work_material = (request.POST.get("work_material") or "").strip()
        main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        if not size_label or overall_length_mm <= 0 or cutting_length_mm <= 0 or quantity <= 0:
            messages.error(request, "Для метчика заполните размер, длины и количество.")
            return redirect("inventory")
        with transaction.atomic():
            tool = ToolItem.objects.create(
                category="tap",
                name=_build_tap_name(size_label, thread_standard, tap_type, hole_type),
                tool_material=tool_material,
                coating_type=coating_type,
                work_material=work_material,
                main_diameter_mm=main_diameter_mm,
                quantity=quantity,
            )
            TapSpec.objects.create(
                tool=tool,
                thread_standard=thread_standard,
                size_label=size_label,
                pitch_mm=pitch_mm if pitch_mm > 0 else None,
                tpi=tpi,
                hole_type=hole_type,
                tap_type=tap_type,
                overall_length_mm=overall_length_mm,
                cutting_length_mm=cutting_length_mm,
            )
        messages.success(request, "Метчик добавлен в склад.")
        return redirect("inventory")

    if action == "move_stock":
        movement_type = (request.POST.get("movement_type") or "").strip()
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        qty = _to_int(request.POST.get("quantity"), 0)
        employee_name = (request.POST.get("employee_name") or "").strip()
        movement_date_raw = (request.POST.get("movement_date") or "").strip()
        comment = (request.POST.get("comment") or "").strip()
        try:
            movement_date = date.fromisoformat(movement_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату движения.")
            return redirect("inventory")
        if movement_type not in {"issue", "restock", "writeoff"} or tool_id <= 0 or qty <= 0:
            messages.error(request, "Проверьте тип операции, инструмент и количество.")
            return redirect("inventory")
        if movement_type == "writeoff" and not comment:
            messages.error(request, "Для списания обязательно укажите причину в комментарии.")
            return redirect("inventory")

        with transaction.atomic():
            tool = ToolItem.objects.select_for_update().get(id=tool_id)
            if movement_type in {"issue", "writeoff"}:
                if tool.quantity < qty:
                    messages.error(request, f"Недостаточно остатков: доступно {tool.quantity}.")
                    return redirect("inventory")
                tool.quantity -= qty
            else:
                tool.quantity += qty
            tool.save(update_fields=["quantity", "updated_at"])
            StockMovement.objects.create(
                movement_type=movement_type,
                tool=tool,
                quantity=qty,
                employee_name=employee_name,
                movement_date=movement_date,
                comment=comment,
                created_by_account=username,
            )
        messages.success(request, "Движение склада сохранено.")
        return redirect("inventory")

    if action == "delete_tool_item":
        if not is_admin_user:
            messages.error(request, "Удалять позиции склада может только администратор.")
            return redirect(f"{request.path}?panel=stock")
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        if tool_id <= 0:
            messages.error(request, "Позиция склада не найдена.")
            return redirect(f"{request.path}?panel=stock")
        tool = ToolItem.objects.filter(id=tool_id).first()
        if not tool:
            messages.error(request, "Позиция склада не найдена.")
            return redirect(f"{request.path}?panel=stock")
        if tool.is_deleted:
            messages.info(request, "Позиция уже помечена как удаленная администратором.")
            return redirect(f"{request.path}?panel=stock")
        tool.is_deleted = True
        tool.deleted_at = timezone.now()
        tool.deleted_by = username
        tool.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])
        messages.success(request, "Позиция помечена как удаленная администратором.")
        return redirect(f"{request.path}?panel=stock")

    if action == "update_tool_item":
        if not is_admin_user:
            messages.error(request, "Изменять позиции склада может только администратор.")
            return redirect(f"{request.path}?panel=stock")
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        tool = (
            ToolItem.objects.select_related(
                "end_mill_spec",
                "tap_spec",
                "center_drill_spec",
                "countersink_spec",
                "drill_spec",
            )
            .filter(id=tool_id, is_deleted=False)
            .first()
        )
        if not tool:
            messages.error(request, "Позиция склада не найдена.")
            return redirect(f"{request.path}?panel=stock")

        tool.tool_material = (request.POST.get("tool_material") or "").strip()
        tool.coating_type = (request.POST.get("coating_type") or "none").strip()
        tool.work_material = (request.POST.get("work_material") or "").strip()
        tool.main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        tool.quantity = max(0, _to_int(request.POST.get("quantity"), tool.quantity))

        if tool.category == "end_mill" and tool.end_mill_spec:
            tool.end_mill_spec.mill_type = (request.POST.get("mill_type") or "end").strip()
            tool.end_mill_spec.diameter_mm = _to_decimal_or_none(request.POST.get("em_diameter_mm"))
            tool.end_mill_spec.corner_radius_mm = _to_decimal_or_none(request.POST.get("em_corner_radius_mm"))
            tool.end_mill_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("em_overall_length_mm"))
            tool.end_mill_spec.cutting_length_mm = _to_decimal_or_none(request.POST.get("em_cutting_length_mm"))
            tool.end_mill_spec.flutes_count = _to_int_or_none(request.POST.get("em_flutes_count"))
            tool.end_mill_spec.save()
        elif tool.category == "tap" and tool.tap_spec:
            tool.tap_spec.thread_standard = (request.POST.get("thread_standard") or "metric").strip()
            tool.tap_spec.size_label = (request.POST.get("size_label") or "").strip()
            tool.tap_spec.pitch_mm = _to_decimal_or_none(request.POST.get("tap_pitch_mm"))
            tool.tap_spec.tpi = _to_int_or_none(request.POST.get("tap_tpi"))
            tool.tap_spec.hole_type = (request.POST.get("hole_type") or "any").strip()
            tool.tap_spec.tap_type = (request.POST.get("tap_type") or "cutting").strip()
            tool.tap_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("tap_overall_length_mm"))
            tool.tap_spec.cutting_length_mm = _to_decimal_or_none(request.POST.get("tap_cutting_length_mm"))
            tool.tap_spec.save()
        elif tool.category == "center_drill" and tool.center_drill_spec:
            tool.center_drill_spec.diameter_mm = _to_decimal_or_none(request.POST.get("cd_diameter_mm"))
            tool.center_drill_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("cd_overall_length_mm"))
            tool.center_drill_spec.angle_deg = (request.POST.get("cd_angle_deg") or "60").strip()
            tool.center_drill_spec.save()
        elif tool.category == "countersink" and tool.countersink_spec:
            tool.countersink_spec.countersink_type = (request.POST.get("cs_type") or "machine").strip()
            tool.countersink_spec.diameter_mm = _to_decimal_or_none(request.POST.get("cs_diameter_mm"))
            tool.countersink_spec.angle_deg = (request.POST.get("cs_angle_deg") or "90").strip()
            tool.countersink_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("cs_overall_length_mm"))
            tool.countersink_spec.flutes_count = _to_int_or_none(request.POST.get("cs_flutes_count"))
            tool.countersink_spec.size_label = (request.POST.get("cs_size_label") or "").strip()
            tool.countersink_spec.save()
        elif tool.category == "drill" and tool.drill_spec:
            tool.drill_spec.diameter_mm = _to_decimal_or_none(request.POST.get("dr_diameter_mm"))
            tool.drill_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("dr_overall_length_mm"))
            tool.drill_spec.cutting_length_mm = _to_decimal_or_none(request.POST.get("dr_cutting_length_mm"))
            tool.drill_spec.angle_deg = _to_decimal_or_none(request.POST.get("dr_angle_deg"))
            tool.drill_spec.save()

        tool.save()
        messages.success(request, "Данные инструмента обновлены.")
        return redirect(f"{request.path}?panel=stock&category={tool.category}")

    if action == "update_tool_cell":
        if not is_admin_user:
            return JsonResponse({"ok": False, "error": "Только администратор."}, status=403)
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        field = (request.POST.get("field") or "").strip()
        value_raw = (request.POST.get("value") or "").strip()
        tool = ToolItem.objects.select_related("end_mill_spec").filter(id=tool_id, is_deleted=False).first()
        if not tool:
            return JsonResponse({"ok": False, "error": "Позиция не найдена."}, status=404)
        if tool.category != "end_mill" or not tool.end_mill_spec:
            return JsonResponse({"ok": False, "error": "Inline-редактирование пока доступно для фрез."}, status=400)

        if field == "mill_type":
            tool.end_mill_spec.mill_type = value_raw or "end"
            tool.end_mill_spec.save(update_fields=["mill_type"])
        elif field == "em_diameter_mm":
            tool.end_mill_spec.diameter_mm = _to_decimal_or_none(value_raw)
            tool.end_mill_spec.save(update_fields=["diameter_mm"])
        elif field == "em_corner_radius_mm":
            tool.end_mill_spec.corner_radius_mm = _to_decimal_or_none(value_raw)
            tool.end_mill_spec.save(update_fields=["corner_radius_mm"])
        elif field == "em_overall_length_mm":
            tool.end_mill_spec.overall_length_mm = _to_decimal_or_none(value_raw)
            tool.end_mill_spec.save(update_fields=["overall_length_mm"])
        elif field == "em_cutting_length_mm":
            tool.end_mill_spec.cutting_length_mm = _to_decimal_or_none(value_raw)
            tool.end_mill_spec.save(update_fields=["cutting_length_mm"])
        elif field == "em_flutes_count":
            tool.end_mill_spec.flutes_count = _to_int_or_none(value_raw)
            tool.end_mill_spec.save(update_fields=["flutes_count"])
        elif field == "main_diameter_mm":
            tool.main_diameter_mm = _to_decimal_or_none(value_raw)
            tool.save(update_fields=["main_diameter_mm", "updated_at"])
        elif field == "tool_material":
            tool.tool_material = value_raw
            tool.save(update_fields=["tool_material", "updated_at"])
        elif field == "coating_type":
            tool.coating_type = value_raw or "none"
            tool.save(update_fields=["coating_type", "updated_at"])
        elif field == "work_material":
            tool.work_material = value_raw
            tool.save(update_fields=["work_material", "updated_at"])
        elif field == "quantity":
            tool.quantity = max(0, _to_int(value_raw, tool.quantity))
            tool.save(update_fields=["quantity", "updated_at"])
        else:
            return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)

        return JsonResponse({"ok": True})

    if action == "process_issue_outcome":
        issue_id = _to_int(request.POST.get("issue_id"), 0)
        returned_qty = _to_int(request.POST.get("returned_qty"), 0)
        writeoff_qty = _to_int(request.POST.get("writeoff_qty"), 0)
        movement_date_raw = (request.POST.get("movement_date") or "").strip()
        comment = (request.POST.get("comment") or "").strip()
        employee_name = (request.POST.get("employee_name") or "").strip()
        if issue_id <= 0 or (returned_qty <= 0 and writeoff_qty <= 0):
            messages.error(request, "Выберите выдачу и укажите количество на возврат/списание.")
            return redirect("inventory")
        if not comment:
            messages.error(request, "Комментарий обязателен: укажите причину списания/возврата.")
            return redirect("inventory")
        try:
            movement_date = date.fromisoformat(movement_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату операции.")
            return redirect("inventory")

        with transaction.atomic():
            issue = StockMovement.objects.select_for_update().select_related("tool").filter(
                id=issue_id, movement_type="issue"
            ).first()
            if not issue:
                messages.error(request, "Исходная выдача не найдена.")
                return redirect("inventory")

            processed = (
                StockMovement.objects.filter(parent_issue=issue, movement_type__in=["restock", "writeoff"])
                .aggregate(total=Coalesce(Sum("quantity"), Value(0, output_field=IntegerField())))
                .get("total", 0)
            )
            remaining = max(0, issue.quantity - int(processed or 0))
            requested = returned_qty + writeoff_qty
            if requested > remaining:
                messages.error(request, f"По этой выдаче осталось обработать только {remaining} шт.")
                return redirect("inventory")

            if returned_qty > 0:
                issue.tool.quantity += returned_qty
                issue.tool.save(update_fields=["quantity", "updated_at"])
                StockMovement.objects.create(
                    movement_type="restock",
                    tool=issue.tool,
                    parent_issue=issue,
                    quantity=returned_qty,
                    employee_name=employee_name or issue.employee_name,
                    movement_date=movement_date,
                    comment=f"Возврат по выдаче #{issue.id}. {comment}",
                    created_by_account=username,
                )
            if writeoff_qty > 0:
                StockMovement.objects.create(
                    movement_type="writeoff",
                    tool=issue.tool,
                    parent_issue=issue,
                    quantity=writeoff_qty,
                    employee_name=employee_name or issue.employee_name,
                    movement_date=movement_date,
                    comment=f"Списание по выдаче #{issue.id}. {comment}",
                    created_by_account=username,
                )
        messages.success(request, "Операция по выданному инструменту сохранена.")
        return redirect("inventory")

    if action == "add_arrival_new":
        category = (request.POST.get("new_category") or "").strip()
        quantity = _to_int(request.POST.get("quantity"), 0)
        movement_date_raw = (request.POST.get("movement_date") or "").strip()
        comment = (request.POST.get("comment") or "").strip()
        tool_material = (request.POST.get("tool_material") or "").strip()
        coating_type = (request.POST.get("coating_type") or "none").strip()
        work_material = (request.POST.get("work_material") or "").strip()
        main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        if category not in {"end_mill", "tap"} or quantity <= 0:
            messages.error(request, "Укажите тип инструмента и количество для прихода.")
            return redirect("inventory")
        try:
            movement_date = date.fromisoformat(movement_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату прихода.")
            return redirect("inventory")

        with transaction.atomic():
            if category == "end_mill":
                mill_type = (request.POST.get("mill_type") or "end").strip()
                diameter_mm = _to_decimal_or_none(request.POST.get("em_diameter_mm"))
                corner_radius_mm = _to_decimal_or_none(request.POST.get("em_corner_radius_mm"))
                overall_length_mm = _to_decimal_or_none(request.POST.get("em_overall_length_mm"))
                cutting_length_mm = _to_decimal_or_none(request.POST.get("em_cutting_length_mm"))
                flutes_count = _to_int_or_none(request.POST.get("em_flutes_count"))
                tool = (
                    ToolItem.objects.select_for_update()
                    .filter(
                        category="end_mill",
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        end_mill_spec__mill_type=mill_type,
                        end_mill_spec__diameter_mm=diameter_mm,
                        end_mill_spec__corner_radius_mm=corner_radius_mm,
                        end_mill_spec__overall_length_mm=overall_length_mm,
                        end_mill_spec__cutting_length_mm=cutting_length_mm,
                        end_mill_spec__flutes_count=flutes_count,
                    )
                    .first()
                )
                if tool:
                    tool.quantity += quantity
                    tool.save(update_fields=["quantity", "updated_at"])
                else:
                    tool = ToolItem.objects.create(
                        category="end_mill",
                        name=_build_end_mill_name(diameter_mm, flutes_count, tool_material, work_material),
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        quantity=quantity,
                    )
                    EndMillSpec.objects.create(
                        tool=tool,
                        mill_type=mill_type,
                        diameter_mm=diameter_mm,
                        corner_radius_mm=corner_radius_mm,
                        overall_length_mm=overall_length_mm,
                        cutting_length_mm=cutting_length_mm,
                        flutes_count=flutes_count,
                    )
            else:
                thread_standard = (request.POST.get("thread_standard") or "metric").strip()
                size_label = (request.POST.get("size_label") or "").strip() or "Размер неизвестен"
                pitch_mm = _to_decimal_or_none(request.POST.get("tap_pitch_mm"))
                tpi = _to_int_or_none(request.POST.get("tap_tpi"))
                hole_type = (request.POST.get("hole_type") or "any").strip()
                tap_type = (request.POST.get("tap_type") or "cutting").strip()
                overall_length_mm = _to_decimal_or_none(request.POST.get("tap_overall_length_mm"))
                cutting_length_mm = _to_decimal_or_none(request.POST.get("tap_cutting_length_mm"))
                tool = (
                    ToolItem.objects.select_for_update()
                    .filter(
                        category="tap",
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        tap_spec__thread_standard=thread_standard,
                        tap_spec__size_label=size_label,
                        tap_spec__pitch_mm=pitch_mm,
                        tap_spec__tpi=tpi,
                        tap_spec__hole_type=hole_type,
                        tap_spec__tap_type=tap_type,
                        tap_spec__overall_length_mm=overall_length_mm,
                        tap_spec__cutting_length_mm=cutting_length_mm,
                    )
                    .first()
                )
                if tool:
                    tool.quantity += quantity
                    tool.save(update_fields=["quantity", "updated_at"])
                else:
                    tool = ToolItem.objects.create(
                        category="tap",
                        name=_build_tap_name(size_label, thread_standard, tap_type, hole_type),
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        quantity=quantity,
                    )
                    TapSpec.objects.create(
                        tool=tool,
                        thread_standard=thread_standard,
                        size_label=size_label,
                        pitch_mm=pitch_mm,
                        tpi=tpi,
                        hole_type=hole_type,
                        tap_type=tap_type,
                        overall_length_mm=overall_length_mm,
                        cutting_length_mm=cutting_length_mm,
                    )
            StockMovement.objects.create(
                movement_type="restock",
                tool=tool,
                quantity=quantity,
                movement_date=movement_date,
                comment=comment or "Приход инструмента",
                created_by_account=username,
            )
        messages.success(request, "Приход сохранен: остаток обновлен (или создана новая позиция).")
        return redirect("inventory")

    if action == "add_arrival_bulk":
        rows_json = (request.POST.get("rows_json") or "").strip()
        if not rows_json:
            messages.error(request, "Добавьте хотя бы одну строку прихода.")
            return redirect(f"{request.path}?panel=arrival")
        try:
            rows = json.loads(rows_json)
        except Exception:
            messages.error(request, "Некорректные данные строк прихода.")
            return redirect(f"{request.path}?panel=arrival")
        if not isinstance(rows, list) or not rows:
            messages.error(request, "Добавьте хотя бы одну строку прихода.")
            return redirect(f"{request.path}?panel=arrival")

        created_count = 0
        with transaction.atomic():
            for row in rows:
                if not isinstance(row, dict):
                    continue
                category = (row.get("category") or "").strip()
                quantity = _to_int(row.get("quantity"), 0)
                movement_date_raw = (row.get("movement_date") or "").strip()
                comment = (row.get("comment") or "").strip()
                supplier_name = (row.get("supplier_name") or "").strip()
                tool_material = (row.get("tool_material") or "").strip()
                coating_type = (row.get("coating_type") or "none").strip()
                work_material = (row.get("work_material") or "").strip()
                main_diameter_mm = _to_decimal_or_none(row.get("main_diameter_mm"))
                if category not in {"end_mill", "tap", "center_drill", "countersink", "drill"} or quantity <= 0:
                    continue
                try:
                    movement_date = date.fromisoformat(movement_date_raw)
                except ValueError:
                    movement_date = date.today()

                if category == "end_mill":
                    mill_type = (row.get("mill_type") or "end").strip()
                    diameter_mm = _to_decimal_or_none(row.get("em_diameter_mm"))
                    corner_radius_mm = _to_decimal_or_none(row.get("em_corner_radius_mm"))
                    overall_length_mm = _to_decimal_or_none(row.get("em_overall_length_mm"))
                    cutting_length_mm = _to_decimal_or_none(row.get("em_cutting_length_mm"))
                    flutes_count = _to_int_or_none(row.get("em_flutes_count"))
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="end_mill",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            end_mill_spec__mill_type=mill_type,
                            end_mill_spec__diameter_mm=diameter_mm,
                            end_mill_spec__corner_radius_mm=corner_radius_mm,
                            end_mill_spec__overall_length_mm=overall_length_mm,
                            end_mill_spec__cutting_length_mm=cutting_length_mm,
                            end_mill_spec__flutes_count=flutes_count,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="end_mill",
                            name=_build_end_mill_name(diameter_mm, flutes_count, tool_material, work_material),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        EndMillSpec.objects.create(
                            tool=tool,
                            mill_type=mill_type,
                            diameter_mm=diameter_mm,
                            corner_radius_mm=corner_radius_mm,
                            overall_length_mm=overall_length_mm,
                            cutting_length_mm=cutting_length_mm,
                            flutes_count=flutes_count,
                        )
                elif category == "tap":
                    thread_standard = (row.get("thread_standard") or "metric").strip()
                    size_label = (row.get("size_label") or "").strip() or "Размер неизвестен"
                    pitch_mm = _to_decimal_or_none(row.get("tap_pitch_mm"))
                    tpi = _to_int_or_none(row.get("tap_tpi"))
                    hole_type = (row.get("hole_type") or "any").strip()
                    tap_type = (row.get("tap_type") or "cutting").strip()
                    overall_length_mm = _to_decimal_or_none(row.get("tap_overall_length_mm"))
                    cutting_length_mm = _to_decimal_or_none(row.get("tap_cutting_length_mm"))
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="tap",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            tap_spec__thread_standard=thread_standard,
                            tap_spec__size_label=size_label,
                            tap_spec__pitch_mm=pitch_mm,
                            tap_spec__tpi=tpi,
                            tap_spec__hole_type=hole_type,
                            tap_spec__tap_type=tap_type,
                            tap_spec__overall_length_mm=overall_length_mm,
                            tap_spec__cutting_length_mm=cutting_length_mm,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="tap",
                            name=_build_tap_name(size_label, thread_standard, tap_type, hole_type),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        TapSpec.objects.create(
                            tool=tool,
                            thread_standard=thread_standard,
                            size_label=size_label,
                            pitch_mm=pitch_mm,
                            tpi=tpi,
                            hole_type=hole_type,
                            tap_type=tap_type,
                            overall_length_mm=overall_length_mm,
                            cutting_length_mm=cutting_length_mm,
                        )
                elif category == "center_drill":
                    diameter_mm = _to_decimal_or_none(row.get("cd_diameter_mm"))
                    overall_length_mm = _to_decimal_or_none(row.get("cd_overall_length_mm"))
                    angle_deg = (row.get("cd_angle_deg") or "60").strip()
                    if angle_deg not in {x[0] for x in CENTER_DRILL_ANGLES}:
                        angle_deg = "60"
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="center_drill",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            center_drill_spec__diameter_mm=diameter_mm,
                            center_drill_spec__overall_length_mm=overall_length_mm,
                            center_drill_spec__angle_deg=angle_deg,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="center_drill",
                            name=_build_center_drill_name(diameter_mm, angle_deg),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        CenterDrillSpec.objects.create(
                            tool=tool,
                            diameter_mm=diameter_mm,
                            overall_length_mm=overall_length_mm,
                            angle_deg=angle_deg,
                        )
                elif category == "countersink":
                    countersink_type = (row.get("cs_type") or "machine").strip()
                    if countersink_type not in {x[0] for x in COUNTERSINK_TYPES}:
                        countersink_type = "machine"
                    diameter_mm = _to_decimal_or_none(row.get("cs_diameter_mm"))
                    angle_deg = (row.get("cs_angle_deg") or "90").strip()
                    if angle_deg not in {x[0] for x in COUNTERSINK_ANGLES}:
                        angle_deg = "90"
                    overall_length_mm = _to_decimal_or_none(row.get("cs_overall_length_mm"))
                    flutes_count = _to_int_or_none(row.get("cs_flutes_count"))
                    size_label = (row.get("cs_size_label") or "").strip()
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="countersink",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            countersink_spec__countersink_type=countersink_type,
                            countersink_spec__diameter_mm=diameter_mm,
                            countersink_spec__angle_deg=angle_deg,
                            countersink_spec__overall_length_mm=overall_length_mm,
                            countersink_spec__flutes_count=flutes_count,
                            countersink_spec__size_label=size_label,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="countersink",
                            name=_build_countersink_name(countersink_type, diameter_mm, angle_deg, size_label),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        CountersinkSpec.objects.create(
                            tool=tool,
                            countersink_type=countersink_type,
                            diameter_mm=diameter_mm,
                            angle_deg=angle_deg,
                            overall_length_mm=overall_length_mm,
                            flutes_count=flutes_count,
                            size_label=size_label,
                        )
                else:
                    diameter_mm = _to_decimal_or_none(row.get("dr_diameter_mm"))
                    overall_length_mm = _to_decimal_or_none(row.get("dr_overall_length_mm"))
                    cutting_length_mm = _to_decimal_or_none(row.get("dr_cutting_length_mm"))
                    angle_deg = _to_decimal_or_none(row.get("dr_angle_deg"))
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="drill",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            drill_spec__diameter_mm=diameter_mm,
                            drill_spec__overall_length_mm=overall_length_mm,
                            drill_spec__cutting_length_mm=cutting_length_mm,
                            drill_spec__angle_deg=angle_deg,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="drill",
                            name=_build_drill_name(diameter_mm, overall_length_mm, cutting_length_mm, angle_deg),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        DrillSpec.objects.create(
                            tool=tool,
                            diameter_mm=diameter_mm,
                            overall_length_mm=overall_length_mm,
                            cutting_length_mm=cutting_length_mm,
                            angle_deg=angle_deg,
                        )
                StockMovement.objects.create(
                    movement_type="restock",
                    tool=tool,
                    quantity=quantity,
                    movement_date=movement_date,
                    comment=comment or (
                        f"Приход инструмента ({supplier_name})"
                        if supplier_name
                        else "Приход инструмента"
                    ),
                    created_by_account=username,
                )
                created_count += 1

        if created_count <= 0:
            messages.error(request, "Не удалось сохранить строки прихода. Проверьте данные.")
        else:
            messages.success(request, f"Оприходовано строк: {created_count}.")
        return redirect(f"{request.path}?panel=arrival")

    if action == "create_purchase_request":
        requested_item = (request.POST.get("requested_item") or "").strip()
        store_link = (request.POST.get("store_link") or "").strip()
        article = (request.POST.get("article") or "").strip()
        quantity = _to_int(request.POST.get("quantity"), 0)
        unit_price = _to_decimal(request.POST.get("unit_price"), Decimal("0"))
        request_comment = (request.POST.get("request_comment") or "").strip()
        if not requested_item or quantity <= 0:
            messages.error(request, "Укажите что закупать и количество больше нуля.")
            return redirect(f"{request.path}?panel=purchases")
        if unit_price < 0:
            messages.error(request, "Цена за 1 шт не может быть отрицательной.")
            return redirect(f"{request.path}?panel=purchases")
        if not store_link and not article:
            messages.error(request, "Добавьте ссылку на магазин или артикул.")
            return redirect(f"{request.path}?panel=purchases")
        PurchaseRequest.objects.create(
            requested_item=requested_item,
            store_link=store_link,
            article=article,
            quantity=quantity,
            unit_price=unit_price,
            request_comment=request_comment,
            requested_by=username,
        )
        messages.success(request, "Заявка на закупку добавлена.")
        return redirect(f"{request.path}?panel=purchases")

    if action == "update_purchase_status":
        req_id = _to_int(request.POST.get("request_id"), 0)
        new_status = (request.POST.get("status") or "").strip()
        status_comment = (request.POST.get("status_comment") or "").strip()
        if req_id <= 0 or new_status not in {x[0] for x in PURCHASE_STATUSES}:
            messages.error(request, "Проверьте заявку и новый статус.")
            return redirect(f"{request.path}?panel=purchases")
        pr = PurchaseRequest.objects.filter(id=req_id).first()
        if not pr:
            messages.error(request, "Заявка не найдена.")
            return redirect(f"{request.path}?panel=purchases")
        pr.status = new_status
        pr.status_comment = status_comment
        pr.status_updated_by = username
        pr.save(update_fields=["status", "status_comment", "status_updated_by", "updated_at"])
        messages.success(request, "Статус заявки обновлён.")
        return redirect(f"{request.path}?panel=purchases")

    if action == "delete_purchase_request":
        if not is_admin_user:
            messages.error(request, "Удалять заявки может только администратор.")
            return redirect(f"{request.path}?panel=purchases")
        req_id = _to_int(request.POST.get("request_id"), 0)
        if req_id <= 0:
            messages.error(request, "Заявка не найдена.")
            return redirect(f"{request.path}?panel=purchases")
        deleted, _ = PurchaseRequest.objects.filter(id=req_id).delete()
        if deleted:
            messages.success(request, "Заявка удалена.")
        else:
            messages.error(request, "Заявка не найдена.")
        return redirect(f"{request.path}?panel=purchases")

    if action == "create_defect_record":
        if not can_defects:
            messages.warning(request, "У вас нет доступа к разделу «Учёт брака».")
            return redirect(reverse("inventory"))
        defect_date_raw = (request.POST.get("defect_date") or "").strip()
        employee_name = (request.POST.get("employee_name") or "").strip()
        responsible_selected = [str(x).strip() for x in request.POST.getlist("responsible_names") if str(x).strip()]
        responsible_selected = list(dict.fromkeys(responsible_selected))
        responsible_name = ", ".join(responsible_selected) if responsible_selected else employee_name
        department_name = employee_department_map.get(employee_name, "")
        defect_quantity = _to_int(request.POST.get("defect_quantity"), 0)
        bad_quantity = _to_int(request.POST.get("bad_quantity"), 0)
        potential_defect_quantity = _to_int(request.POST.get("potential_defect_quantity"), 0)
        product_name = (request.POST.get("product_name") or "").strip()
        defect_reason = (request.POST.get("defect_reason") or "").strip()
        try:
            defect_date = date.fromisoformat(defect_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату.")
            return redirect(f"{request.path}?panel=defects")
        if not employee_name or not defect_reason:
            messages.error(request, "Заполните сотрудника и причину брака.")
            return redirect(f"{request.path}?panel=defects")
        if employee_options and employee_name not in employee_options:
            messages.error(request, "Выберите сотрудника из списка (нет доступа к этому сотруднику).")
            return redirect(f"{request.path}?panel=defects")
        if employee_name not in employee_department_map:
            messages.error(request, "Не удалось определить отдел сотрудника — обновите страницу и выберите сотрудника заново.")
            return redirect(f"{request.path}?panel=defects")
        if responsible_selected:
            bad_resp = [nm for nm in responsible_selected if employee_options and nm not in employee_options]
            if bad_resp:
                messages.error(request, "Выберите ответственных только из списка сотрудников.")
                return redirect(f"{request.path}?panel=defects")
        if defect_quantity < 0:
            messages.error(request, "Количество брака не может быть отрицательным.")
            return redirect(f"{request.path}?panel=defects")
        if bad_quantity < 0:
            messages.error(request, "Неисправно не может быть отрицательным.")
            return redirect(f"{request.path}?panel=defects")
        if bad_quantity > defect_quantity:
            messages.error(request, "Неисправно не должно превышать кол-во брака.")
            return redirect(f"{request.path}?panel=defects")
        if potential_defect_quantity < 0:
            messages.error(request, "Потенциальный брак не может быть отрицательным.")
            return redirect(f"{request.path}?panel=defects")
        good_quantity = defect_quantity - bad_quantity
        EmployeeDefectRecord.objects.create(
            defect_date=defect_date,
            responsible_name=responsible_name,
            employee_name=employee_name,
            department_name=department_name,
            defect_quantity=defect_quantity,
            good_quantity=good_quantity,
            bad_quantity=bad_quantity,
            potential_defect_quantity=potential_defect_quantity,
            product_name=product_name,
            defect_reason=defect_reason,
        )
        messages.success(request, "Запись о браке сохранена.")
        return redirect(f"{request.path}?panel=defects")

    if action == "update_defect_record":
        if not can_defects:
            messages.warning(request, "У вас нет доступа к разделу «Учёт брака».")
            return redirect(reverse("inventory"))
        rec_id = _to_int(request.POST.get("defect_id"), 0)
        if rec_id <= 0:
            messages.error(request, "Запись не найдена.")
            return redirect(f"{request.path}?panel=defects")
        rec = EmployeeDefectRecord.objects.filter(id=rec_id).first()
        if not rec:
            messages.error(request, "Запись не найдена.")
            return redirect(f"{request.path}?panel=defects")

        if not is_admin_user:
            allowed_departments = {d for d in employee_department_map.values() if d}
            has_access = (
                (rec.department_name and rec.department_name in allowed_departments)
                or (not rec.department_name and rec.employee_name in employee_options)
            )
            if not has_access:
                messages.error(request, "Нет прав на редактирование этой записи.")
                return redirect(f"{request.path}?panel=defects")

        defect_date_raw = (request.POST.get("defect_date") or "").strip()
        employee_name = (request.POST.get("employee_name") or "").strip()
        defect_quantity = _to_int(request.POST.get("defect_quantity"), 0)
        bad_quantity = _to_int(request.POST.get("bad_quantity"), 0)
        potential_defect_quantity = _to_int(request.POST.get("potential_defect_quantity"), 0)
        product_name = (request.POST.get("product_name") or "").strip()
        defect_reason = (request.POST.get("defect_reason") or "").strip()
        try:
            defect_date = date.fromisoformat(defect_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату.")
            return redirect(f"{request.path}?panel=defects")
        if not employee_name or not defect_reason:
            messages.error(request, "Заполните сотрудника и причину брака.")
            return redirect(f"{request.path}?panel=defects")
        if employee_options and employee_name not in employee_options:
            messages.error(request, "Выберите сотрудника из списка (нет доступа к этому сотруднику).")
            return redirect(f"{request.path}?panel=defects")
        if employee_name not in employee_department_map:
            messages.error(request, "Не удалось определить отдел сотрудника — обновите страницу и выберите сотрудника заново.")
            return redirect(f"{request.path}?panel=defects")
        if defect_quantity < 0:
            messages.error(request, "Количество брака не может быть отрицательным.")
            return redirect(f"{request.path}?panel=defects")
        if bad_quantity < 0:
            messages.error(request, "Неисправно не может быть отрицательным.")
            return redirect(f"{request.path}?panel=defects")
        if bad_quantity > defect_quantity:
            messages.error(request, "Неисправно не должно превышать кол-во брака.")
            return redirect(f"{request.path}?panel=defects")
        if potential_defect_quantity < 0:
            messages.error(request, "Потенциальный брак не может быть отрицательным.")
            return redirect(f"{request.path}?panel=defects")
        good_quantity = defect_quantity - bad_quantity

        rec.defect_date = defect_date
        rec.employee_name = employee_name
        # В таблице редактируется только основной сотрудник; список ответственных не перезаписываем.
        rec.responsible_name = rec.responsible_name or employee_name
        rec.department_name = employee_department_map.get(employee_name, "")
        rec.defect_quantity = defect_quantity
        rec.good_quantity = good_quantity
        rec.bad_quantity = bad_quantity
        rec.potential_defect_quantity = potential_defect_quantity
        rec.product_name = product_name
        rec.defect_reason = defect_reason
        rec.save(
            update_fields=[
                "defect_date",
                "employee_name",
                "responsible_name",
                "department_name",
                "defect_quantity",
                "good_quantity",
                "bad_quantity",
                "potential_defect_quantity",
                "product_name",
                "defect_reason",
            ]
        )
        messages.success(request, "Запись учёта брака обновлена.")
        return redirect(f"{request.path}?panel=defects")

    if action == "delete_defect_record":
        if not is_admin_user:
            messages.error(request, "Удалять записи учёта брака может только администратор.")
            return redirect(f"{request.path}?panel=defects")
        rec_id = _to_int(request.POST.get("defect_id"), 0)
        if rec_id <= 0:
            messages.error(request, "Запись не найдена.")
            return redirect(f"{request.path}?panel=defects")
        deleted, _ = EmployeeDefectRecord.objects.filter(id=rec_id).delete()
        if deleted:
            messages.success(request, "Запись учёта брака удалена.")
        else:
            messages.error(request, "Запись не найдена.")
        return redirect(f"{request.path}?panel=defects")

    show_all = (request.GET.get("show_all") or "1").strip() == "1"
    qs = ToolItem.objects.filter(is_deleted=False)
    if not show_all:
        qs = qs.filter(quantity__gt=0)
    filter_category = (request.GET.get("category") or "end_mill").strip()
    if filter_category not in {"end_mill", "tap", "center_drill", "countersink", "drill"}:
        filter_category = "end_mill"
    qs = qs.filter(category=filter_category)

    diameter_mm_raw = (request.GET.get("diameter_mm") or "").strip()
    mill_overall_length_raw = (request.GET.get("mill_overall_length_mm") or "").strip()
    mill_cutting_length_raw = (request.GET.get("mill_cutting_length_mm") or "").strip()
    mill_flutes_count_raw = (request.GET.get("mill_flutes_count") or "").strip()
    mill_corner_radius_raw = (request.GET.get("mill_corner_radius_mm") or "").strip()
    mill_type_raw = (request.GET.get("mill_type") or "").strip()

    tap_size = (request.GET.get("tap_size") or "").strip()
    tap_pitch_raw = (request.GET.get("tap_pitch") or "").strip()
    tap_thread_standard = (request.GET.get("tap_thread_standard") or "").strip()
    tap_hole_type = (request.GET.get("tap_hole_type") or "").strip()
    tap_tool_type = (request.GET.get("tap_tool_type") or "").strip()
    tap_overall_length_raw = (request.GET.get("tap_overall_length_mm") or "").strip()
    tap_cutting_length_raw = (request.GET.get("tap_cutting_length_mm") or "").strip()
    center_diameter_raw = (request.GET.get("center_diameter_mm") or "").strip()
    center_overall_length_raw = (request.GET.get("center_overall_length_mm") or "").strip()
    center_angle_raw = (request.GET.get("center_angle_deg") or "").strip()
    countersink_type_raw = (request.GET.get("countersink_type") or "").strip()
    countersink_diameter_raw = (request.GET.get("countersink_diameter_mm") or "").strip()
    countersink_angle_raw = (request.GET.get("countersink_angle_deg") or "").strip()
    countersink_length_raw = (request.GET.get("countersink_overall_length_mm") or "").strip()
    countersink_flutes_raw = (request.GET.get("countersink_flutes_count") or "").strip()
    countersink_size_raw = (request.GET.get("countersink_size_label") or "").strip()
    drill_diameter_raw = (request.GET.get("drill_diameter_mm") or "").strip()
    drill_overall_length_raw = (request.GET.get("drill_overall_length_mm") or "").strip()
    drill_cutting_length_raw = (request.GET.get("drill_cutting_length_mm") or "").strip()
    drill_angle_raw = (request.GET.get("drill_angle_deg") or "").strip()
    arrival_supplier = (request.GET.get("arrival_supplier") or "").strip()

    tool_material = (request.GET.get("tool_material") or "").strip()
    coating_type = (request.GET.get("coating_type") or "").strip()
    work_material = (request.GET.get("work_material") or "").strip()

    if diameter_mm_raw:
        diameter_mm = _to_decimal(diameter_mm_raw, Decimal("0"))
        if diameter_mm > 0:
            qs = qs.filter(end_mill_spec__diameter_mm=diameter_mm)
    if mill_overall_length_raw:
        mill_overall_length = _to_decimal(mill_overall_length_raw, Decimal("0"))
        if mill_overall_length > 0:
            qs = qs.filter(end_mill_spec__overall_length_mm=mill_overall_length)
    if mill_cutting_length_raw:
        mill_cutting_length = _to_decimal(mill_cutting_length_raw, Decimal("0"))
        if mill_cutting_length > 0:
            qs = qs.filter(end_mill_spec__cutting_length_mm=mill_cutting_length)
    if mill_flutes_count_raw:
        mill_flutes_count = _to_int(mill_flutes_count_raw, 0)
        if mill_flutes_count > 0:
            qs = qs.filter(end_mill_spec__flutes_count=mill_flutes_count)
    if mill_corner_radius_raw:
        mill_corner_radius = _to_decimal(mill_corner_radius_raw, Decimal("-1"))
        if mill_corner_radius >= 0:
            qs = qs.filter(end_mill_spec__corner_radius_mm=mill_corner_radius)
    if mill_type_raw:
        qs = qs.filter(end_mill_spec__mill_type=mill_type_raw)

    if tap_size:
        qs = qs.filter(tap_spec__size_label__iexact=tap_size)
    if tap_pitch_raw:
        tap_pitch = _to_decimal(tap_pitch_raw, Decimal("0"))
        if tap_pitch > 0:
            qs = qs.filter(tap_spec__pitch_mm=tap_pitch)
    if tap_thread_standard:
        qs = qs.filter(tap_spec__thread_standard=tap_thread_standard)
    if tap_hole_type:
        qs = qs.filter(tap_spec__hole_type=tap_hole_type)
    if tap_tool_type:
        qs = qs.filter(tap_spec__tap_type=tap_tool_type)
    if tap_overall_length_raw:
        tap_overall_length = _to_decimal(tap_overall_length_raw, Decimal("0"))
        if tap_overall_length > 0:
            qs = qs.filter(tap_spec__overall_length_mm=tap_overall_length)
    if tap_cutting_length_raw:
        tap_cutting_length = _to_decimal(tap_cutting_length_raw, Decimal("0"))
        if tap_cutting_length > 0:
            qs = qs.filter(tap_spec__cutting_length_mm=tap_cutting_length)
    if center_diameter_raw:
        center_diameter = _to_decimal(center_diameter_raw, Decimal("0"))
        if center_diameter > 0:
            qs = qs.filter(center_drill_spec__diameter_mm=center_diameter)
    if center_overall_length_raw:
        center_overall_length = _to_decimal(center_overall_length_raw, Decimal("0"))
        if center_overall_length > 0:
            qs = qs.filter(center_drill_spec__overall_length_mm=center_overall_length)
    if center_angle_raw:
        qs = qs.filter(center_drill_spec__angle_deg=center_angle_raw)
    if countersink_type_raw:
        qs = qs.filter(countersink_spec__countersink_type=countersink_type_raw)
    if countersink_diameter_raw:
        countersink_diameter = _to_decimal(countersink_diameter_raw, Decimal("0"))
        if countersink_diameter > 0:
            qs = qs.filter(countersink_spec__diameter_mm=countersink_diameter)
    if countersink_angle_raw:
        qs = qs.filter(countersink_spec__angle_deg=countersink_angle_raw)
    if countersink_length_raw:
        countersink_length = _to_decimal(countersink_length_raw, Decimal("0"))
        if countersink_length > 0:
            qs = qs.filter(countersink_spec__overall_length_mm=countersink_length)
    if countersink_flutes_raw:
        countersink_flutes = _to_int(countersink_flutes_raw, 0)
        if countersink_flutes > 0:
            qs = qs.filter(countersink_spec__flutes_count=countersink_flutes)
    if countersink_size_raw:
        qs = qs.filter(countersink_spec__size_label__iexact=countersink_size_raw)
    if drill_diameter_raw:
        drill_diameter = _to_decimal(drill_diameter_raw, Decimal("0"))
        if drill_diameter > 0:
            qs = qs.filter(drill_spec__diameter_mm=drill_diameter)
    if drill_overall_length_raw:
        drill_overall_length = _to_decimal(drill_overall_length_raw, Decimal("0"))
        if drill_overall_length > 0:
            qs = qs.filter(drill_spec__overall_length_mm=drill_overall_length)
    if drill_cutting_length_raw:
        drill_cutting_length = _to_decimal(drill_cutting_length_raw, Decimal("0"))
        if drill_cutting_length > 0:
            qs = qs.filter(drill_spec__cutting_length_mm=drill_cutting_length)
    if drill_angle_raw:
        drill_angle = _to_decimal(drill_angle_raw, Decimal("0"))
        if drill_angle > 0:
            qs = qs.filter(drill_spec__angle_deg=drill_angle)

    if tool_material:
        qs = qs.filter(tool_material=tool_material)
    if coating_type:
        qs = qs.filter(coating_type=coating_type)
    if work_material:
        qs = qs.filter(work_material=work_material)
    if arrival_supplier:
        qs = qs.filter(
            movements__movement_type="restock",
            movements__comment__icontains=arrival_supplier,
        ).distinct()

    option_source_qs = ToolItem.objects.filter(is_deleted=False)
    if not show_all:
        option_source_qs = option_source_qs.filter(quantity__gt=0)
    option_source_qs = option_source_qs.filter(category=filter_category)

    end_mill_diameters = _distinct_numeric_values(option_source_qs.filter(category="end_mill"), "end_mill_spec__diameter_mm")
    end_mill_overall_lengths = _distinct_numeric_values(option_source_qs.filter(category="end_mill"), "end_mill_spec__overall_length_mm")
    end_mill_cutting_lengths = _distinct_numeric_values(option_source_qs.filter(category="end_mill"), "end_mill_spec__cutting_length_mm")
    end_mill_flutes = _distinct_numeric_values(option_source_qs.filter(category="end_mill"), "end_mill_spec__flutes_count")
    end_mill_corner_radii = _distinct_numeric_values(option_source_qs.filter(category="end_mill"), "end_mill_spec__corner_radius_mm")
    end_mill_types = _distinct_text_values(option_source_qs.filter(category="end_mill"), "end_mill_spec__mill_type")

    tap_sizes = _distinct_text_values(option_source_qs.filter(category="tap"), "tap_spec__size_label")
    tap_pitches = _distinct_numeric_values(option_source_qs.filter(category="tap"), "tap_spec__pitch_mm")
    tap_overall_lengths = _distinct_numeric_values(option_source_qs.filter(category="tap"), "tap_spec__overall_length_mm")
    tap_cutting_lengths = _distinct_numeric_values(option_source_qs.filter(category="tap"), "tap_spec__cutting_length_mm")
    tap_thread_standards = _distinct_text_values(option_source_qs.filter(category="tap"), "tap_spec__thread_standard")
    tap_hole_types = _distinct_text_values(option_source_qs.filter(category="tap"), "tap_spec__hole_type")
    tap_tool_types = _distinct_text_values(option_source_qs.filter(category="tap"), "tap_spec__tap_type")
    center_diameters = _distinct_numeric_values(option_source_qs.filter(category="center_drill"), "center_drill_spec__diameter_mm")
    center_overall_lengths = _distinct_numeric_values(option_source_qs.filter(category="center_drill"), "center_drill_spec__overall_length_mm")
    center_angles = _distinct_text_values(option_source_qs.filter(category="center_drill"), "center_drill_spec__angle_deg")
    countersink_types = _distinct_text_values(option_source_qs.filter(category="countersink"), "countersink_spec__countersink_type")
    countersink_diameters = _distinct_numeric_values(option_source_qs.filter(category="countersink"), "countersink_spec__diameter_mm")
    countersink_angles = _distinct_text_values(option_source_qs.filter(category="countersink"), "countersink_spec__angle_deg")
    countersink_lengths = _distinct_numeric_values(option_source_qs.filter(category="countersink"), "countersink_spec__overall_length_mm")
    countersink_flutes = _distinct_numeric_values(option_source_qs.filter(category="countersink"), "countersink_spec__flutes_count")
    countersink_sizes = _distinct_text_values(option_source_qs.filter(category="countersink"), "countersink_spec__size_label")
    drill_diameters = _distinct_numeric_values(option_source_qs.filter(category="drill"), "drill_spec__diameter_mm")
    drill_overall_lengths = _distinct_numeric_values(option_source_qs.filter(category="drill"), "drill_spec__overall_length_mm")
    drill_cutting_lengths = _distinct_numeric_values(option_source_qs.filter(category="drill"), "drill_spec__cutting_length_mm")
    drill_angles = _distinct_numeric_values(option_source_qs.filter(category="drill"), "drill_spec__angle_deg")
    issue_candidates = list(
        StockMovement.objects.filter(movement_type="issue")
        .select_related("tool", "tool__end_mill_spec", "tool__tap_spec", "tool__center_drill_spec", "tool__countersink_spec", "tool__drill_spec")
        .annotate(
            processed_qty=Coalesce(
                Sum("issue_outcomes__quantity"),
                Value(0, output_field=IntegerField()),
            )
        )
        .annotate(remaining_qty=F("quantity") - F("processed_qty"))
        .filter(remaining_qty__gt=0)
        .order_by("-movement_date", "-id")[:200]
    )
    purchase_status = (request.GET.get("purchase_status") or "").strip()
    purchase_date_from = (request.GET.get("purchase_date_from") or "").strip()
    purchase_date_to = (request.GET.get("purchase_date_to") or "").strip()
    purchase_employee = (request.GET.get("purchase_employee") or "").strip()
    purchase_qs = PurchaseRequest.objects.all()
    if purchase_status in {x[0] for x in PURCHASE_STATUSES}:
        purchase_qs = purchase_qs.filter(status=purchase_status)
    if purchase_date_from:
        purchase_qs = purchase_qs.filter(created_at__date__gte=purchase_date_from)
    if purchase_date_to:
        purchase_qs = purchase_qs.filter(created_at__date__lte=purchase_date_to)
    if purchase_employee:
        purchase_qs = purchase_qs.filter(requested_by__icontains=purchase_employee)

    defect_date_from = (request.GET.get("defect_date_from") or "").strip()
    defect_date_to = (request.GET.get("defect_date_to") or "").strip()
    defect_department = (request.GET.get("defect_department") or "").strip()
    defects_qs = EmployeeDefectRecord.objects.all()
    if not is_admin_user:
        allowed_departments = {d for d in employee_department_map.values() if d}
        if allowed_departments:
            defects_qs = defects_qs.filter(
                Q(department_name__in=allowed_departments)
                | Q(department_name="", employee_name__in=employee_options)
            )
        else:
            defects_qs = defects_qs.none()
    if defect_date_from:
        defects_qs = defects_qs.filter(defect_date__gte=defect_date_from)
    if defect_date_to:
        defects_qs = defects_qs.filter(defect_date__lte=defect_date_to)
    if defect_department:
        defects_qs = defects_qs.filter(department_name=defect_department)
    defect_department_options = sorted(
        {
            d
            for d in list(employee_department_map.values()) + list(
                EmployeeDefectRecord.objects.exclude(department_name="")
                .values_list("department_name", flat=True)
                .distinct()
            )
            if d
        }
    )

    payroll_rows: list[dict] = []
    payroll_year = date.today().year
    payroll_month = date.today().month
    payroll_month_name = MONTH_NAMES_RU[payroll_month]
    payroll_year_options: list[int] = []
    if panel == "payroll":
        from .payroll_helpers import build_payroll_employee_rows, parse_payroll_year_month

        payroll_year, payroll_month = parse_payroll_year_month(request)
        payroll_month_name = MONTH_NAMES_RU[payroll_month]
        pay_df, skud_totals, payroll_year_options = build_payroll_employee_rows(username, payroll_year, payroll_month)
        if pay_df is not None and not getattr(pay_df, "empty", True):
            for _, r in pay_df.iterrows():
                ec = normalize_emp_code(str(r.get("emp_code") or ""))
                if not ec:
                    continue
                payroll_rows.append(
                    {
                        "emp_code": ec,
                        "label": employee_label_row(r),
                        "department_name": str(r.get("department_name") or "").strip(),
                        "skud_hours": round(float(skud_totals.get(ec, 0.0)), 2),
                    }
                )
            codes = [row["emp_code"] for row in payroll_rows]
            status_by_code = {
                s.emp_code: s
                for s in EmployeePayrollMonthStatus.objects.filter(
                    year=payroll_year, month=payroll_month, emp_code__in=codes
                )
            }
            for row in payroll_rows:
                st = status_by_code.get(row["emp_code"])
                row["payroll_advance_ok"] = bool(st and st.advance_closed)
                row["payroll_month_ok"] = bool(st and st.payroll_closed)
        if not payroll_year_options:
            ny = date.today().year
            payroll_year_options = [ny - 1, ny, ny + 1]

    ctx = {
        "tool_items": qs.select_related("end_mill_spec", "tap_spec", "center_drill_spec", "countersink_spec", "drill_spec"),
        "movements": StockMovement.objects.select_related("tool", "tool__end_mill_spec", "tool__tap_spec", "tool__center_drill_spec", "tool__countersink_spec", "tool__drill_spec")[:50],
        "thread_standards": THREAD_STANDARDS,
        "tap_hole_types": TAP_HOLE_TYPES,
        "tap_tool_types": TAP_TOOL_TYPES,
        "filters": {
            "category": filter_category,
            "diameter_mm": diameter_mm_raw,
            "mill_overall_length_mm": mill_overall_length_raw,
            "mill_cutting_length_mm": mill_cutting_length_raw,
            "mill_flutes_count": mill_flutes_count_raw,
            "mill_corner_radius_mm": mill_corner_radius_raw,
            "mill_type": mill_type_raw,
            "tap_size": tap_size,
            "tap_pitch": tap_pitch_raw,
            "tap_thread_standard": tap_thread_standard,
            "tap_hole_type": tap_hole_type,
            "tap_tool_type": tap_tool_type,
            "tap_overall_length_mm": tap_overall_length_raw,
            "tap_cutting_length_mm": tap_cutting_length_raw,
            "center_diameter_mm": center_diameter_raw,
            "center_overall_length_mm": center_overall_length_raw,
            "center_angle_deg": center_angle_raw,
            "countersink_type": countersink_type_raw,
            "countersink_diameter_mm": countersink_diameter_raw,
            "countersink_angle_deg": countersink_angle_raw,
            "countersink_overall_length_mm": countersink_length_raw,
            "countersink_flutes_count": countersink_flutes_raw,
            "countersink_size_label": countersink_size_raw,
            "drill_diameter_mm": drill_diameter_raw,
            "drill_overall_length_mm": drill_overall_length_raw,
            "drill_cutting_length_mm": drill_cutting_length_raw,
            "drill_angle_deg": drill_angle_raw,
            "tool_material": tool_material,
            "coating_type": coating_type,
            "work_material": work_material,
            "arrival_supplier": arrival_supplier,
            "show_all": show_all,
        },
        "end_mill_filter_options": {
            "diameters": end_mill_diameters,
            "overall_lengths": end_mill_overall_lengths,
            "cutting_lengths": end_mill_cutting_lengths,
            "flutes": end_mill_flutes,
            "corner_radii": end_mill_corner_radii,
            "types": end_mill_types,
        },
        "end_mill_types": END_MILL_TYPES,
        "tap_filter_options": {
            "sizes": tap_sizes,
            "pitches": tap_pitches,
            "overall_lengths": tap_overall_lengths,
            "cutting_lengths": tap_cutting_lengths,
            "thread_standards": tap_thread_standards,
            "hole_types": tap_hole_types,
            "tool_types": tap_tool_types,
        },
        "center_drill_filter_options": {
            "diameters": center_diameters,
            "overall_lengths": center_overall_lengths,
            "angles": center_angles,
        },
        "center_drill_angles": CENTER_DRILL_ANGLES,
        "countersink_filter_options": {
            "types": countersink_types,
            "diameters": countersink_diameters,
            "angles": countersink_angles,
            "overall_lengths": countersink_lengths,
            "flutes": countersink_flutes,
            "sizes": countersink_sizes,
        },
        "countersink_types": COUNTERSINK_TYPES,
        "countersink_angles": COUNTERSINK_ANGLES,
        "drill_filter_options": {
            "diameters": drill_diameters,
            "overall_lengths": drill_overall_lengths,
            "cutting_lengths": drill_cutting_lengths,
            "angles": drill_angles,
        },
        "tool_material_types": TOOL_MATERIAL_TYPES,
        "coating_types": COATING_TYPES,
        "work_material_types": WORK_MATERIAL_TYPES,
        "today": date.today().isoformat(),
        "movement_tool_options": ToolItem.objects.select_related("end_mill_spec", "tap_spec", "center_drill_spec", "countersink_spec", "drill_spec").filter(is_deleted=False).order_by("category", "name"),
        "issue_candidates": issue_candidates,
        "purchase_requests": purchase_qs[:300],
        "purchase_statuses": PURCHASE_STATUSES,
        "purchase_filters": {
            "status": purchase_status,
            "date_from": purchase_date_from,
            "date_to": purchase_date_to,
            "employee": purchase_employee,
        },
        "is_admin_user": is_admin_user,
        "panel": panel,
        "employee_options": employee_options,
        "defect_records": defects_qs[:300],
        "defect_filters": {
            "date_from": defect_date_from,
            "date_to": defect_date_to,
            "department": defect_department,
        },
        "defect_department_options": defect_department_options,
        "employee_table_rows": employee_table_rows,
        "payroll_rows": payroll_rows,
        "payroll_year": payroll_year,
        "payroll_month": payroll_month,
        "payroll_month_name": payroll_month_name,
        "payroll_year_options": payroll_year_options,
        "month_choices_payroll": [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)],
    }
    return render(request, "shifts/inventory.html", ctx)
