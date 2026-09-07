"""Справочник типов/подтипов склада и настраиваемых характеристик."""
from __future__ import annotations

import hashlib
import json
import re

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, nav_permission_required, write_permission_required
from .models import STOCK_TOOL_FIELD_KINDS, StockToolField, StockToolSubtype, StockToolType
from .stock_tool_type_seed import (
    MAX_FIELDS_PER_SCOPE,
    MAX_SUBTYPES_PER_TYPE,
    move_type_into_parent,
)

MAX_TYPES = 80
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VALID_FIELD_KINDS = {k for k, _ in STOCK_TOOL_FIELD_KINDS}


def _err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


def _json_body(request):
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


def _clamp_int(val, default: int, lo: int, hi: int) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _norm_code(raw: str, *, fallback: str = "") -> str:
    text = (raw or "").strip().lower().replace("_", "-")
    if not text and fallback:
        text = slugify(fallback, allow_unicode=False) or ""
    text = re.sub(r"[^a-z0-9-]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if not text and fallback:
        digest = hashlib.md5(fallback.encode("utf-8")).hexdigest()[:8]
        text = f"item-{digest}"
    return text[:64]


def _norm_choices(raw) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(raw, str):
        parts = re.split(r"[\n,;]+", raw)
    elif isinstance(raw, list):
        parts = raw
    else:
        parts = []
    for part in parts:
        s = str(part or "").strip()[:80]
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= 80:
            break
    return out


def _serialize_field(field: StockToolField) -> dict:
    return {
        "id": field.id,
        "tool_type_id": field.tool_type_id,
        "subtype_id": field.subtype_id,
        "key": field.key,
        "label": field.label,
        "field_kind": field.field_kind,
        "field_kind_label": field.get_field_kind_display(),
        "choices": list(field.choices or []),
        "required": bool(field.required),
        "unit": field.unit or "",
        "help_text": field.help_text or "",
        "sort_order": field.sort_order,
    }


def _serialize_subtype(sub: StockToolSubtype, *, with_fields: bool = False) -> dict:
    data = {
        "id": sub.id,
        "tool_type_id": sub.tool_type_id,
        "name": sub.name,
        "code": sub.code,
        "is_active": bool(sub.is_active),
        "sort_order": sub.sort_order,
        "notes": sub.notes or "",
        "fields_count": getattr(sub, "fields_count", None),
    }
    if with_fields:
        fields = list(sub.fields.all())
        data["fields"] = [_serialize_field(f) for f in fields]
        data["fields_count"] = len(fields)
    return data


def _serialize_type(t: StockToolType, *, with_details: bool = False) -> dict:
    data = {
        "id": t.id,
        "name": t.name,
        "code": t.code,
        "is_active": bool(t.is_active),
        "sort_order": t.sort_order,
        "notes": t.notes or "",
        "subtypes_count": getattr(t, "subtypes_count", None),
        "fields_count": getattr(t, "fields_count", None),
    }
    if with_details:
        subtypes = list(t.subtypes.all())
        type_fields = [f for f in t.fields.all() if f.subtype_id is None]
        data["subtypes"] = [_serialize_subtype(s, with_fields=True) for s in subtypes]
        data["fields"] = [_serialize_field(f) for f in type_fields]
        data["subtypes_count"] = len(subtypes)
        data["fields_count"] = len(type_fields)
    return data


def _save_type(body: dict, obj: StockToolType | None) -> JsonResponse:
    name = str(body.get("name") or "").strip()[:120]
    if not name:
        return _err("Укажите название типа")
    code = _norm_code(str(body.get("code") or ""), fallback=name)
    if not code or not _SLUG_RE.match(code):
        return _err("Код типа: латиница, цифры и дефис")
    notes = str(body.get("notes") or "").strip()[:300]
    is_active = bool(body.get("is_active", True))
    sort_order = _clamp_int(body.get("sort_order"), 0, 0, 9999)

    try:
        with transaction.atomic():
            if obj is None:
                if StockToolType.objects.count() >= MAX_TYPES:
                    return _err(f"Лимит типов: {MAX_TYPES}")
                if StockToolType.objects.filter(code=code).exists():
                    return _err("Тип с таким кодом уже есть")
                obj = StockToolType.objects.create(
                    name=name,
                    code=code,
                    notes=notes,
                    is_active=is_active,
                    sort_order=sort_order,
                )
            else:
                if StockToolType.objects.filter(code=code).exclude(pk=obj.pk).exists():
                    return _err("Тип с таким кодом уже есть")
                obj.name = name
                obj.code = code
                obj.notes = notes
                obj.is_active = is_active
                obj.sort_order = sort_order
                obj.save()
    except IntegrityError:
        return _err("Не удалось сохранить тип (конфликт кода)")

    obj = StockToolType.objects.prefetch_related("subtypes__fields", "fields").get(pk=obj.pk)
    return JsonResponse({"ok": True, "type": _serialize_type(obj, with_details=True)})


def _save_subtype(body: dict, *, tool_type: StockToolType, sub: StockToolSubtype | None) -> JsonResponse:
    name = str(body.get("name") or "").strip()[:120]
    if not name:
        return _err("Укажите название подтипа")
    code = _norm_code(str(body.get("code") or ""), fallback=name)
    if not code or not _SLUG_RE.match(code):
        return _err("Код подтипа: латиница, цифры и дефис")
    notes = str(body.get("notes") or "").strip()[:300]
    is_active = bool(body.get("is_active", True))
    sort_order = _clamp_int(body.get("sort_order"), 0, 0, 9999)

    try:
        with transaction.atomic():
            if sub is None:
                if tool_type.subtypes.count() >= MAX_SUBTYPES_PER_TYPE:
                    return _err(f"Лимит подтипов: {MAX_SUBTYPES_PER_TYPE}")
                if StockToolSubtype.objects.filter(tool_type=tool_type, code=code).exists():
                    return _err("Подтип с таким кодом уже есть")
                sub = StockToolSubtype.objects.create(
                    tool_type=tool_type,
                    name=name,
                    code=code,
                    notes=notes,
                    is_active=is_active,
                    sort_order=sort_order,
                )
            else:
                if StockToolSubtype.objects.filter(tool_type=tool_type, code=code).exclude(pk=sub.pk).exists():
                    return _err("Подтип с таким кодом уже есть")
                sub.name = name
                sub.code = code
                sub.notes = notes
                sub.is_active = is_active
                sub.sort_order = sort_order
                sub.save()
    except IntegrityError:
        return _err("Не удалось сохранить подтип (конфликт кода)")

    sub = StockToolSubtype.objects.prefetch_related("fields").get(pk=sub.pk)
    return JsonResponse({"ok": True, "subtype": _serialize_subtype(sub, with_fields=True)})


def _save_field(body: dict, *, tool_type: StockToolType, field: StockToolField | None) -> JsonResponse:
    subtype = None
    subtype_id = body.get("subtype_id")
    if subtype_id not in (None, "", 0, "0"):
        subtype = get_object_or_404(StockToolSubtype, pk=subtype_id, tool_type=tool_type)

    label = str(body.get("label") or "").strip()[:120]
    if not label:
        return _err("Укажите подпись характеристики")
    key = _norm_code(str(body.get("key") or ""), fallback=label)
    if not key or not _SLUG_RE.match(key):
        return _err("Код поля: латиница, цифры и дефис")
    field_kind = str(body.get("field_kind") or "text").strip()
    if field_kind not in _VALID_FIELD_KINDS:
        return _err("Некорректный вид поля")
    choices = _norm_choices(body.get("choices"))
    if field_kind == "select" and not choices:
        return _err("Для списка укажите хотя бы один вариант")
    if field_kind != "select":
        choices = []
    required = bool(body.get("required"))
    unit = str(body.get("unit") or "").strip()[:24]
    help_text = str(body.get("help_text") or "").strip()[:200]
    sort_order = _clamp_int(body.get("sort_order"), 0, 0, 9999)

    try:
        with transaction.atomic():
            if field is None:
                scope_qs = StockToolField.objects.filter(tool_type=tool_type, subtype=subtype)
                if scope_qs.count() >= MAX_FIELDS_PER_SCOPE:
                    return _err(f"Лимит характеристик: {MAX_FIELDS_PER_SCOPE}")
                if scope_qs.filter(key=key).exists():
                    return _err("Поле с таким кодом уже есть в этой области")
                field = StockToolField.objects.create(
                    tool_type=tool_type,
                    subtype=subtype,
                    key=key,
                    label=label,
                    field_kind=field_kind,
                    choices=choices,
                    required=required,
                    unit=unit,
                    help_text=help_text,
                    sort_order=sort_order,
                )
            else:
                if (field.subtype_id or None) != (subtype.id if subtype else None):
                    return _err("Нельзя сменить область характеристики — удалите и создайте заново")
                qs = StockToolField.objects.filter(tool_type=tool_type, key=key, subtype=subtype)
                if qs.exclude(pk=field.pk).exists():
                    return _err("Поле с таким кодом уже есть в этой области")
                field.key = key
                field.label = label
                field.field_kind = field_kind
                field.choices = choices
                field.required = required
                field.unit = unit
                field.help_text = help_text
                field.sort_order = sort_order
                field.save()
    except IntegrityError:
        return _err("Не удалось сохранить характеристику (конфликт кода)")

    return JsonResponse({"ok": True, "field": _serialize_field(field)})


@biota_login_required
@nav_permission_required("inventory_types")
def inventory_types_view(request):
    kinds = [{"value": v, "label": lab} for v, lab in STOCK_TOOL_FIELD_KINDS]
    return render(
        request,
        "shifts/inventory_types.html",
        {
            "field_kinds": kinds,
            "field_kinds_json": json.dumps(kinds, ensure_ascii=False),
        },
    )


@biota_login_required
@nav_permission_required("inventory_types")
@require_http_methods(["GET", "POST"])
def inventory_types_api_types(request):
    if request.method == "GET":
        with_details = str(request.GET.get("details") or "").strip() in {"1", "true", "yes"}
        qs = StockToolType.objects.all().prefetch_related("subtypes__fields", "fields")
        rows = []
        for t in qs:
            if with_details:
                rows.append(_serialize_type(t, with_details=True))
            else:
                subtypes = list(t.subtypes.all())
                type_fields = [f for f in t.fields.all() if f.subtype_id is None]
                t.subtypes_count = len(subtypes)
                t.fields_count = len(type_fields)
                rows.append(_serialize_type(t))
        return JsonResponse({"ok": True, "types": rows})
    return _api_types_post(request)


@write_permission_required
def _api_types_post(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    return _save_type(body, None)


@biota_login_required
@nav_permission_required("inventory_types")
@require_http_methods(["GET", "POST", "DELETE"])
def inventory_types_api_type_detail(request, pk: int):
    obj = get_object_or_404(StockToolType.objects.prefetch_related("subtypes__fields", "fields"), pk=pk)
    if request.method == "GET":
        return JsonResponse({"ok": True, "type": _serialize_type(obj, with_details=True)})
    if request.method == "DELETE":
        return _api_type_delete(request, obj)
    return _api_type_update(request, obj)


@write_permission_required
def _api_type_update(request, obj: StockToolType):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    return _save_type(body, obj)


@write_permission_required
def _api_type_delete(request, obj: StockToolType):
    _ = request
    obj.delete()
    return JsonResponse({"ok": True})


@write_permission_required
def _move_type_into_type(request, source: StockToolType) -> JsonResponse:
    """Превращает тип в подтип другого типа (с полями и бывшими подтипами → «Вид»)."""
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    target_id = body.get("target_type_id") or body.get("parent_type_id")
    if not target_id:
        return _err("Укажите целевой тип")
    try:
        if int(target_id) == int(source.pk):
            return _err("Нельзя переместить тип в самого себя")
        target = get_object_or_404(StockToolType, pk=target_id)
        new_sub = move_type_into_parent(source, target)
    except IntegrityError:
        return _err("Не удалось переместить тип (конфликт кодов)")
    except ValueError as exc:
        return _err(str(exc))
    except (TypeError,):
        return _err("Некорректный целевой тип")

    target = StockToolType.objects.prefetch_related("subtypes__fields", "fields").get(pk=target.pk)
    return JsonResponse(
        {
            "ok": True,
            "type": _serialize_type(target, with_details=True),
            "moved_subtype_id": new_sub.id,
        }
    )


@biota_login_required
@nav_permission_required("inventory_types")
@write_permission_required
@require_http_methods(["POST"])
def inventory_types_api_type_move(request, pk: int):
    source = get_object_or_404(StockToolType, pk=pk)
    return _move_type_into_type(request, source)


@biota_login_required
@nav_permission_required("inventory_types")
@write_permission_required
@require_http_methods(["POST"])
def inventory_types_api_subtype_upsert(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    type_id = body.get("tool_type_id") or body.get("type_id")
    tool_type = get_object_or_404(StockToolType, pk=type_id)
    sub = None
    sub_id = body.get("id")
    if sub_id:
        sub = get_object_or_404(StockToolSubtype, pk=sub_id, tool_type=tool_type)
    return _save_subtype(body, tool_type=tool_type, sub=sub)


@biota_login_required
@nav_permission_required("inventory_types")
@write_permission_required
@require_http_methods(["DELETE"])
def inventory_types_api_subtype_delete(request, pk: int):
    sub = get_object_or_404(StockToolSubtype, pk=pk)
    sub.delete()
    return JsonResponse({"ok": True})


@biota_login_required
@nav_permission_required("inventory_types")
@write_permission_required
@require_http_methods(["POST"])
def inventory_types_api_field_upsert(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    type_id = body.get("tool_type_id") or body.get("type_id")
    tool_type = get_object_or_404(StockToolType, pk=type_id)
    field = None
    field_id = body.get("id")
    if field_id:
        field = get_object_or_404(StockToolField, pk=field_id, tool_type=tool_type)
    return _save_field(body, tool_type=tool_type, field=field)


@biota_login_required
@nav_permission_required("inventory_types")
@write_permission_required
@require_http_methods(["DELETE"])
def inventory_types_api_field_delete(request, pk: int):
    field = get_object_or_404(StockToolField, pk=pk)
    field.delete()
    return JsonResponse({"ok": True})
