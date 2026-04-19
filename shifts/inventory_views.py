from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, nav_permission_required
from .models import (
    COATING_TYPES,
    END_MILL_TYPES,
    EndMillSpec,
    StockMovement,
    TapSpec,
    ToolItem,
    TAP_HOLE_TYPES,
    TAP_TOOL_TYPES,
    THREAD_STANDARDS,
    TOOL_MATERIAL_TYPES,
    WORK_MATERIAL_TYPES,
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


@biota_login_required
@nav_permission_required("inventory")
@require_http_methods(["GET", "POST"])
def inventory_view(request):
    action = request.POST.get("action") if request.method == "POST" else ""
    panel = (request.GET.get("panel") or "stock").strip()
    if panel not in {"stock", "history", "issue", "arrival", "issue_outcome"}:
        panel = "stock"

    if action == "add_end_mill":
        diameter_mm = _to_decimal(request.POST.get("diameter_mm"), Decimal("0"))
        overall_length_mm = _to_decimal(request.POST.get("overall_length_mm"), Decimal("0"))
        cutting_length_mm = _to_decimal(request.POST.get("cutting_length_mm"), Decimal("0"))
        flutes_count = _to_int(request.POST.get("flutes_count"), 0)
        quantity = _to_int(request.POST.get("quantity"), 0)
        tool_material = (request.POST.get("tool_material") or "").strip()
        coating_type = (request.POST.get("coating_type") or "none").strip()
        work_material = (request.POST.get("work_material") or "").strip()
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
            )
        messages.success(request, "Движение склада сохранено.")
        return redirect("inventory")

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
            )
        messages.success(request, "Приход сохранен: остаток обновлен (или создана новая позиция).")
        return redirect("inventory")

    show_all = (request.GET.get("show_all") or "").strip() == "1"
    qs = ToolItem.objects.all()
    if not show_all:
        qs = qs.filter(quantity__gt=0)
    filter_category = (request.GET.get("category") or "").strip()
    if filter_category in {"end_mill", "tap"}:
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

    if tool_material:
        qs = qs.filter(tool_material=tool_material)
    if coating_type:
        qs = qs.filter(coating_type=coating_type)
    if work_material:
        qs = qs.filter(work_material=work_material)

    option_source_qs = ToolItem.objects.all()
    if not show_all:
        option_source_qs = option_source_qs.filter(quantity__gt=0)
    if filter_category in {"end_mill", "tap"}:
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
    issue_candidates = list(
        StockMovement.objects.filter(movement_type="issue")
        .select_related("tool", "tool__end_mill_spec", "tool__tap_spec")
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

    ctx = {
        "tool_items": qs.select_related("end_mill_spec", "tap_spec"),
        "movements": StockMovement.objects.select_related("tool")[:50],
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
            "tool_material": tool_material,
            "coating_type": coating_type,
            "work_material": work_material,
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
        "tool_material_types": TOOL_MATERIAL_TYPES,
        "coating_types": COATING_TYPES,
        "work_material_types": WORK_MATERIAL_TYPES,
        "today": date.today().isoformat(),
        "movement_tool_options": ToolItem.objects.select_related("end_mill_spec", "tap_spec").all().order_by("category", "name"),
        "issue_candidates": issue_candidates,
        "panel": panel,
    }
    return render(request, "shifts/inventory.html", ctx)
