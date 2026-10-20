from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import parse_qsl, urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import inventory_stock_manage_for_user

from .auth_utils import (
    biota_login_required,
    biota_user,
    inventory_route_nav_access_required,
    is_real_admin,
    request_is_admin_ui,
    write_permission_required,
)
from .models import (
    WarehouseEmployee,
    WarehouseFastenerItem,
    WarehouseFastenerMovement,
    WarehouseFastenerType,
)

_FASTENER_FILTER_KEYS = frozenset({"type_id", "thread_mm", "length_mm", "q", "show_all", "item_id"})
_DEFAULT_THREAD_MM = (
    Decimal("3"),
    Decimal("4"),
    Decimal("5"),
    Decimal("6"),
    Decimal("8"),
    Decimal("10"),
    Decimal("12"),
)
_SIZE_QUERY_RE = re.compile(
    r"[mм]\s*(?P<thread>\d+(?:[.,]\d+)?)\s*(?:[xх×*]\s*(?P<length>\d+))?",
    flags=re.IGNORECASE,
)


def _to_int(raw, default: int = 0) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _norm_thread_mm_value(raw: str) -> Decimal | None:
    val = str(raw or "").strip().upper().replace(",", ".")
    val = val.replace("М", "M")
    if val.startswith("M"):
        val = val[1:].strip()
    if not val:
        return None
    try:
        dec = Decimal(val)
    except (InvalidOperation, ValueError):
        return None
    if dec <= 0:
        return None
    return dec


def _fmt_thread_mm(thread_mm: Decimal | None) -> str:
    if thread_mm is None:
        return ""
    raw = format(thread_mm, "f").rstrip("0").rstrip(".")
    return f"M{raw or '0'}"


def _parse_movement_date(raw: str) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _match_employee(name: str, options: list[str]) -> str:
    raw = (name or "").strip()
    if not raw or not options:
        return ""
    if raw in options:
        return raw
    norm = raw.casefold()
    for opt in options:
        if opt.casefold() == norm:
            return opt
    return ""


def _clean_return_query(raw_query: str) -> str:
    clean: list[tuple[str, str]] = []
    for key, val in parse_qsl(str(raw_query or ""), keep_blank_values=False):
        if key in _FASTENER_FILTER_KEYS:
            clean.append((key, val))
    return urlencode(clean)


def _redirect_fasteners(request):
    query = _clean_return_query(request.POST.get("return_query") or "")
    url = reverse("inventory_fasteners")
    if query:
        url = f"{url}?{query}"
    return redirect(url)


def _filters_from_get(request_get) -> dict[str, str]:
    return {
        "type_id": (request_get.get("type_id") or "").strip(),
        "thread_mm": (request_get.get("thread_mm") or "").strip(),
        "length_mm": (request_get.get("length_mm") or "").strip(),
        "q": (request_get.get("q") or "").strip(),
        "show_all": "1" if (request_get.get("show_all") or "").strip() == "1" else "0",
        "item_id": (request_get.get("item_id") or "").strip(),
    }


def _size_hint_from_query(query_text: str) -> tuple[Decimal | None, int | None]:
    match = _SIZE_QUERY_RE.search(query_text or "")
    if not match:
        return None, None
    thread = _norm_thread_mm_value(match.group("thread") or "")
    length = _to_int(match.group("length"), 0)
    return thread, length if length > 0 else None


def _item_select_label(item: WarehouseFastenerItem) -> str:
    extras: list[str] = []
    if item.strength_class:
        extras.append(item.strength_class)
    if item.material:
        extras.append(item.material)
    if item.coating:
        extras.append(item.coating)
    tail = f" · {' / '.join(extras)}" if extras else ""
    return (
        f"{item.fastener_type.name} {_fmt_thread_mm(item.thread_diameter_mm)}x{item.length_mm}"
        f"{tail} · ост. {item.quantity}"
    )


@biota_login_required
@inventory_route_nav_access_required
@write_permission_required
@require_http_methods(["GET", "POST"])
def inventory_fasteners_view(request):
    username = biota_user(request) or "Неизвестный пользователь"
    is_admin_user = request_is_admin_ui(request)
    can_manage_stock = is_admin_user or (
        inventory_stock_manage_for_user(username) and not is_real_admin(request)
    )
    action = (request.POST.get("action") or "").strip() if request.method == "POST" else ""

    employee_options = list(
        WarehouseEmployee.objects.filter(is_active=True).order_by("name", "id").values_list("name", flat=True)
    )

    if action == "add_fastener_item":
        if not can_manage_stock:
            messages.error(request, "Добавлять позиции метизов могут только администратор или пользователь с выданным правом.")
            return _redirect_fasteners(request)

        type_id = _to_int(request.POST.get("fastener_type_id"), 0)
        fastener_type = WarehouseFastenerType.objects.filter(id=type_id, is_active=True).first()
        if not fastener_type:
            messages.error(request, "Выберите тип метиза.")
            return _redirect_fasteners(request)

        thread_mm = _norm_thread_mm_value(request.POST.get("thread_diameter"))
        length_mm = _to_int(request.POST.get("length_mm"), 0)
        qty = _to_int(request.POST.get("quantity"), 0)
        movement_date = _parse_movement_date(request.POST.get("movement_date")) or date.today()
        if thread_mm is None or length_mm <= 0 or qty <= 0:
            messages.error(request, "Укажите корректно размер (M...), длину и количество больше нуля.")
            return _redirect_fasteners(request)

        strength_class = (request.POST.get("strength_class") or "").strip()[:40]
        material = (request.POST.get("material") or "").strip()[:80]
        coating = (request.POST.get("coating") or "").strip()[:80]
        warehouse_location = (request.POST.get("warehouse_location") or "").strip()[:32]
        notes = (request.POST.get("notes") or "").strip()[:300]
        comment = (request.POST.get("comment") or "").strip()[:300]

        with transaction.atomic():
            item, created = WarehouseFastenerItem.objects.select_for_update().get_or_create(
                fastener_type=fastener_type,
                thread_diameter_mm=thread_mm,
                length_mm=length_mm,
                strength_class=strength_class,
                material=material,
                coating=coating,
                warehouse_location=warehouse_location,
                defaults={"notes": notes, "quantity": 0},
            )
            changed_fields: list[str] = []
            if notes and notes != item.notes:
                item.notes = notes
                changed_fields.append("notes")
            item.quantity = int(item.quantity or 0) + qty
            changed_fields.extend(["quantity", "updated_at"])
            item.save(update_fields=changed_fields)

            WarehouseFastenerMovement.objects.create(
                movement_type=WarehouseFastenerMovement.MOVE_RESTOCK,
                item=item,
                quantity=qty,
                movement_date=movement_date,
                comment=comment or ("Первичное оприходование" if created else "Пополнение"),
                created_by_account=username,
            )

        if created:
            messages.success(request, f"Позиция добавлена: {item.fastener_type.name} {item.size_label}.")
        else:
            messages.success(request, f"Остаток обновлён: {item.fastener_type.name} {item.size_label}.")
        return _redirect_fasteners(request)

    if action == "move_fastener_stock":
        if not can_manage_stock:
            messages.error(request, "Проводить движения метизов могут только администратор или пользователь с выданным правом.")
            return _redirect_fasteners(request)

        movement_type = (request.POST.get("movement_type") or "").strip()
        item_id = _to_int(request.POST.get("item_id"), 0)
        qty = _to_int(request.POST.get("quantity"), 0)
        movement_date = _parse_movement_date(request.POST.get("movement_date"))
        employee_name = (request.POST.get("employee_name") or "").strip()
        comment = (request.POST.get("comment") or "").strip()[:300]
        valid_types = {
            WarehouseFastenerMovement.MOVE_ISSUE,
            WarehouseFastenerMovement.MOVE_RESTOCK,
            WarehouseFastenerMovement.MOVE_WRITEOFF,
        }

        if movement_type not in valid_types or item_id <= 0 or qty <= 0:
            messages.error(request, "Проверьте тип операции, позицию и количество.")
            return _redirect_fasteners(request)
        if movement_date is None:
            messages.error(request, "Введите корректную дату движения.")
            return _redirect_fasteners(request)
        if movement_type == WarehouseFastenerMovement.MOVE_ISSUE:
            matched = _match_employee(employee_name, employee_options)
            if not matched:
                messages.error(request, "Для выдачи выберите сотрудника из списка склада.")
                return _redirect_fasteners(request)
            employee_name = matched
        if movement_type == WarehouseFastenerMovement.MOVE_WRITEOFF and not comment:
            messages.error(request, "Для списания обязательно укажите причину в комментарии.")
            return _redirect_fasteners(request)

        with transaction.atomic():
            item = (
                WarehouseFastenerItem.objects.select_for_update()
                .select_related("fastener_type")
                .filter(id=item_id, is_deleted=False)
                .first()
            )
            if not item:
                messages.error(request, "Позиция метиза не найдена.")
                return _redirect_fasteners(request)
            if movement_type in {
                WarehouseFastenerMovement.MOVE_ISSUE,
                WarehouseFastenerMovement.MOVE_WRITEOFF,
            }:
                if int(item.quantity or 0) < qty:
                    messages.error(request, f"Недостаточно остатка: доступно {item.quantity} шт.")
                    return _redirect_fasteners(request)
                item.quantity = int(item.quantity or 0) - qty
            else:
                item.quantity = int(item.quantity or 0) + qty
            item.save(update_fields=["quantity", "updated_at"])
            WarehouseFastenerMovement.objects.create(
                movement_type=movement_type,
                item=item,
                quantity=qty,
                employee_name=employee_name,
                movement_date=movement_date,
                comment=comment,
                created_by_account=username,
            )

        messages.success(request, "Движение метизов сохранено.")
        return _redirect_fasteners(request)

    filters = _filters_from_get(request.GET)
    query_text = filters["q"]
    selected_item_id = _to_int(filters.get("item_id"), 0)
    show_all = filters.get("show_all") == "1"
    size_thread, size_length = _size_hint_from_query(query_text)

    items_qs = (
        WarehouseFastenerItem.objects.filter(
            is_deleted=False,
            fastener_type__is_active=True,
        )
        .select_related("fastener_type")
        .order_by("thread_diameter_mm", "length_mm", "fastener_type__sort_order", "id")
    )
    if not show_all:
        items_qs = items_qs.filter(quantity__gt=0)

    type_id = _to_int(filters.get("type_id"), 0)
    if type_id > 0:
        items_qs = items_qs.filter(fastener_type_id=type_id)

    thread_mm = _norm_thread_mm_value(filters.get("thread_mm"))
    if thread_mm is not None:
        items_qs = items_qs.filter(thread_diameter_mm=thread_mm)

    length_mm = _to_int(filters.get("length_mm"), 0)
    if length_mm > 0:
        items_qs = items_qs.filter(length_mm=length_mm)

    if query_text:
        q_obj = (
            Q(fastener_type__name__icontains=query_text)
            | Q(strength_class__icontains=query_text)
            | Q(material__icontains=query_text)
            | Q(coating__icontains=query_text)
            | Q(notes__icontains=query_text)
            | Q(warehouse_location__icontains=query_text)
            | Q(fastener_type__standard__icontains=query_text)
        )
        items_qs = items_qs.filter(q_obj)
        if size_thread is not None:
            items_qs = items_qs.filter(thread_diameter_mm=size_thread)
        if size_length is not None:
            items_qs = items_qs.filter(length_mm=size_length)

    items = list(items_qs)

    type_options = list(
        WarehouseFastenerType.objects.filter(is_active=True).order_by("sort_order", "name", "id")
    )

    thread_values = sorted(
        {
            *list(
                WarehouseFastenerItem.objects.filter(
                    is_deleted=False,
                    fastener_type__is_active=True,
                ).values_list("thread_diameter_mm", flat=True)
            ),
            *_DEFAULT_THREAD_MM,
        }
    )
    thread_options = [{"value": format(v, "f").rstrip("0").rstrip("."), "label": _fmt_thread_mm(v)} for v in thread_values]

    length_values_qs = (
        WarehouseFastenerItem.objects.filter(
            is_deleted=False,
            fastener_type__is_active=True,
        )
        .values_list("length_mm", flat=True)
        .distinct()
        .order_by("length_mm")
    )
    length_options = [int(v) for v in length_values_qs if int(v or 0) > 0]

    movement_items = list(
        WarehouseFastenerItem.objects.filter(
            is_deleted=False,
            fastener_type__is_active=True,
        )
        .select_related("fastener_type")
        .order_by("thread_diameter_mm", "length_mm", "fastener_type__sort_order", "id")
    )
    if selected_item_id <= 0 and movement_items:
        selected_item_id = movement_items[0].id
    for mv_item in movement_items:
        mv_item.option_label = _item_select_label(mv_item)

    total_qty = int(items_qs.aggregate(total=Sum("quantity"))["total"] or 0)
    return_query = _clean_return_query(urlencode({k: v for k, v in filters.items() if v}))

    for row in items:
        params = {k: v for k, v in filters.items() if v}
        params["item_id"] = str(row.id)
        row.select_url = reverse("inventory_fasteners") + "?" + urlencode(params)

    movement_rows = list(
        WarehouseFastenerMovement.objects.select_related("item", "item__fastener_type")
        .order_by("-created_at", "-id")[:80]
    )

    ctx = {
        "panel": "fasteners",
        "can_manage_stock": can_manage_stock,
        "is_admin_user": is_admin_user,
        "filters": filters,
        "type_options": type_options,
        "thread_options": thread_options,
        "length_options": length_options,
        "items": items,
        "items_count": len(items),
        "items_total_qty": total_qty,
        "movement_items": movement_items,
        "movement_rows": movement_rows,
        "movement_type_options": WarehouseFastenerMovement.MOVEMENT_TYPES,
        "selected_item_id": selected_item_id,
        "employee_options": employee_options,
        "today": date.today().isoformat(),
        "return_query": return_query,
    }
    return render(request, "shifts/inventory_fasteners.html", ctx)
