"""Контракты производства: CRUD + операции изделия + текущий этап."""
from __future__ import annotations

import json

from django.db import transaction
from django.db.models import Count, Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, nav_permission_required, write_permission_required
from .models import WorkContract, WorkContractPosition, WorkPositionOperation

MAX_CONTRACTS = 200
MAX_POSITIONS = 500
MAX_OPS = 40

_DEMO_SEED = (
    (
        "Контракт А — корпус",
        (
            (
                "Кожух ВРПЕ.301122.009 СБ",
                "Материал - лист АМг 2М 2,5мм",
                250,
                ("Лазерный", "Гибка", "Фрезерный"),
            ),
            (
                "Радиатор ВРПЕ.752694.034",
                "Заготовка - профиль AB1320 185мм",
                84,
                ("Фрезерный",),
            ),
            ("Панель ВРПЕ.741148.003", "", 672, ("Лазерный", "Монтаж")),
        ),
    ),
    (
        "Контракт Б — крепёж / мелкие",
        (
            ("Кронштейн ВРПЕ.301122.011", "Лист 2мм", 800, ("Лазерный", "Гибка")),
            ("Пластина ВРПЕ.741148.010", "", 1600, ("Лазерный",)),
        ),
    ),
)

_STAGE_META = (
    WorkContractPosition.STAGE_NOT_STARTED,
    WorkContractPosition.STAGE_N_A,
    WorkContractPosition.STAGE_NO_INFO,
    WorkContractPosition.STAGE_DONE,
)
# STAGE_PAUSED обрабатывается отдельно — сохраняет current_operation


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


def _backfill_missing_operations() -> None:
    empty = (
        WorkContractPosition.objects.annotate(ops_n=Count("operations"))
        .filter(ops_n=0)
        .order_by("id")[:200]
    )
    defaults = ("Лазерный", "Фрезерный")
    for pos in empty:
        for k, op_name in enumerate(defaults):
            WorkPositionOperation.objects.create(position=pos, name=op_name, sort_order=k)


def _ensure_demo_contracts() -> None:
    if WorkContract.objects.exists():
        _backfill_missing_operations()
        return
    with transaction.atomic():
        for i, (title, rows) in enumerate(_DEMO_SEED):
            cab = WorkContract.objects.create(name=title, sort_order=i)
            for j, (name, desc, qty, ops) in enumerate(rows):
                pos = WorkContractPosition.objects.create(
                    contract=cab,
                    name=name,
                    description=desc,
                    quantity=qty,
                    sort_order=j,
                    stage=WorkContractPosition.STAGE_NOT_STARTED,
                )
                for k, op_name in enumerate(ops):
                    WorkPositionOperation.objects.create(
                        position=pos, name=op_name, sort_order=k
                    )
    _backfill_missing_operations()


def _serialize_operation(op: WorkPositionOperation) -> dict:
    return {
        "id": op.id,
        "position_id": op.position_id,
        "name": op.name,
        "description": op.description or "",
        "sort_order": op.sort_order,
    }


def _clean_operations_payload(ops_raw) -> list[tuple[str, str]]:
    """Список (name, description) из JSON body."""
    out: list[tuple[str, str]] = []
    if not isinstance(ops_raw, list):
        return out
    for item in ops_raw[:MAX_OPS]:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()[:120]
            note = str(item.get("description") or item.get("note") or "").strip()[:300]
        else:
            name = str(item or "").strip()[:120]
            note = ""
        if name:
            out.append((name, note))
    return out


def _serialize_position(pos: WorkContractPosition, *, depth: int = 0) -> dict:
    ops = list(pos.operations.all()) if hasattr(pos, "_prefetched_objects_cache") else list(
        pos.operations.order_by("sort_order", "id")
    )
    return {
        "id": pos.id,
        "contract_id": pos.contract_id,
        "parent_id": pos.parent_id,
        "split_depth": int(depth),
        "name": pos.name,
        "description": pos.description or "",
        "quantity": int(pos.quantity or 1),
        "sort_order": pos.sort_order,
        "stage": pos.stage,
        "stage_label": pos.stage_label(),
        "current_operation_id": pos.current_operation_id,
        "operations": [_serialize_operation(o) for o in ops],
    }


def _flatten_positions(positions) -> list[tuple[WorkContractPosition, int]]:
    """Корни по sort_order/id, сразу под каждым — его отрывы (рекурсивно)."""
    by_parent: dict[int | None, list[WorkContractPosition]] = {}
    for p in positions:
        by_parent.setdefault(p.parent_id, []).append(p)
    for kids in by_parent.values():
        kids.sort(key=lambda x: (x.sort_order, x.id))

    out: list[tuple[WorkContractPosition, int]] = []

    def walk(node: WorkContractPosition, depth: int) -> None:
        out.append((node, depth))
        for ch in by_parent.get(node.id, []):
            walk(ch, depth + 1)

    for root in by_parent.get(None, []):
        walk(root, 0)
    return out


def _serialize_contract(cab: WorkContract, *, with_positions: bool = True) -> dict:
    data = {
        "id": cab.id,
        "name": cab.name,
        "notes": cab.notes or "",
        "sort_order": cab.sort_order,
        "positions_count": 0,
        "positions_qty": 0,
        "positions": [],
    }
    if with_positions:
        flat = _flatten_positions(list(cab.positions.all()))
        data["positions"] = [_serialize_position(p, depth=d) for p, d in flat]
        data["positions_count"] = len(flat)
        data["positions_qty"] = sum(int(p.quantity or 0) for p, _d in flat)
    else:
        data["positions_count"] = getattr(cab, "positions_count", cab.positions.count())
        data["positions_qty"] = int(getattr(cab, "positions_qty", 0) or 0)
    return data


def _contracts_queryset():
    return (
        WorkContract.objects.prefetch_related(
            Prefetch(
                "positions",
                queryset=WorkContractPosition.objects.prefetch_related("operations").order_by(
                    "sort_order", "id"
                ),
            )
        )
        .annotate(positions_qty=Sum("positions__quantity"))
        .order_by("sort_order", "name", "id")
    )


def _position_depth(pos: WorkContractPosition) -> int:
    depth = 0
    pid = pos.parent_id
    seen: set[int] = set()
    while pid and pid not in seen and depth < 20:
        seen.add(pid)
        depth += 1
        pid = (
            WorkContractPosition.objects.filter(pk=pid)
            .values_list("parent_id", flat=True)
            .first()
        )
    return depth


def _load_position(pk: int) -> WorkContractPosition:
    return (
        WorkContractPosition.objects.prefetch_related("operations")
        .select_related("current_operation", "parent")
        .get(pk=pk)
    )


def _set_position_stage(pos: WorkContractPosition, stage_raw, operation_id) -> str | None:
    stage = str(stage_raw or "").strip()
    if stage == WorkContractPosition.STAGE_PAUSED:
        pos.stage = WorkContractPosition.STAGE_PAUSED
        # зафиксировать этап, на котором остановились (если передан / уже был)
        if operation_id not in (None, ""):
            try:
                op_id = int(operation_id)
            except (TypeError, ValueError):
                return "Укажите операцию паузы"
            op = WorkPositionOperation.objects.filter(pk=op_id, position=pos).first()
            if op is None:
                return "Операция не найдена у этого изделия"
            pos.current_operation = op
        # иначе оставляем current_operation как есть (не сбрасываем)
        return None
    if stage in _STAGE_META:
        pos.stage = stage
        pos.current_operation = None
        return None
    if stage == WorkContractPosition.STAGE_OPERATION or operation_id not in (None, ""):
        try:
            op_id = int(operation_id)
        except (TypeError, ValueError):
            return "Укажите операцию"
        op = WorkPositionOperation.objects.filter(pk=op_id, position=pos).first()
        if op is None:
            return "Операция не найдена у этого изделия"
        pos.stage = WorkContractPosition.STAGE_OPERATION
        pos.current_operation = op
        return None
    if not stage:
        pos.stage = WorkContractPosition.STAGE_NOT_STARTED
        pos.current_operation = None
        return None
    return "Некорректный этап"


@biota_login_required
@nav_permission_required("contracts")
@require_http_methods(["GET"])
def contracts_view(request):
    _ensure_demo_contracts()
    contracts = list(_contracts_queryset())
    payload = [_serialize_contract(c) for c in contracts]
    return render(
        request,
        "shifts/contracts.html",
        {
            "contracts_json": json.dumps(payload, ensure_ascii=False),
            "contracts_count": len(payload),
        },
    )


@biota_login_required
@nav_permission_required("contracts")
@require_http_methods(["GET"])
def contracts_api_list(request):
    _ensure_demo_contracts()
    return JsonResponse(
        {"ok": True, "contracts": [_serialize_contract(c) for c in _contracts_queryset()]}
    )


@biota_login_required
@nav_permission_required("contracts")
@write_permission_required
@require_http_methods(["POST"])
def contracts_api_contract_upsert(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    name = str(body.get("name") or "").strip()[:200]
    if not name:
        return _err("Укажите название контракта")
    notes = str(body.get("notes") or "").strip()[:300]
    sort_order = _clamp_int(body.get("sort_order"), 0, 0, 9999)
    cid = body.get("id")
    if cid:
        cab = get_object_or_404(WorkContract, pk=cid)
        cab.name = name
        cab.notes = notes
        if "sort_order" in body:
            cab.sort_order = sort_order
        cab.save()
    else:
        if WorkContract.objects.count() >= MAX_CONTRACTS:
            return _err(f"Лимит контрактов: {MAX_CONTRACTS}")
        cab = WorkContract.objects.create(name=name, notes=notes, sort_order=sort_order)
    cab = _contracts_queryset().get(pk=cab.pk)
    return JsonResponse({"ok": True, "contract": _serialize_contract(cab)})


@biota_login_required
@nav_permission_required("contracts")
@write_permission_required
@require_http_methods(["DELETE", "POST"])
def contracts_api_contract_delete(request, pk: int):
    cab = get_object_or_404(WorkContract, pk=pk)
    cab.delete()
    return JsonResponse({"ok": True})


@biota_login_required
@nav_permission_required("contracts")
@write_permission_required
@require_http_methods(["POST"])
def contracts_api_position_upsert(request):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    contract_id = body.get("contract_id")
    cab = get_object_or_404(WorkContract, pk=contract_id)
    name = str(body.get("name") or "").strip()[:320]
    if not name:
        return _err("Укажите изделие")
    description = str(body.get("description") or "").strip()[:2000]
    quantity = _clamp_int(body.get("quantity"), 1, 1, 1_000_000)
    sort_order = _clamp_int(body.get("sort_order"), 0, 0, 9999)
    pid = body.get("id")
    if pid:
        pos = get_object_or_404(WorkContractPosition, pk=pid, contract=cab)
        pos.name = name
        pos.description = description
        pos.quantity = quantity
        if "sort_order" in body:
            pos.sort_order = sort_order
        if "stage" in body or "current_operation_id" in body:
            err = _set_position_stage(pos, body.get("stage"), body.get("current_operation_id"))
            if err:
                return _err(err)
        pos.save()
    else:
        if cab.positions.count() >= MAX_POSITIONS:
            return _err(f"Лимит позиций в контракте: {MAX_POSITIONS}")
        pos = WorkContractPosition.objects.create(
            contract=cab,
            name=name,
            description=description,
            quantity=quantity,
            sort_order=sort_order,
            stage=WorkContractPosition.STAGE_NOT_STARTED,
        )
        ops_raw = body.get("operations")
        cleaned = _clean_operations_payload(ops_raw)
        for i, (op_name, op_note) in enumerate(cleaned):
            WorkPositionOperation.objects.create(
                position=pos, name=op_name, description=op_note, sort_order=i
            )
    pos = _load_position(pos.pk)
    return JsonResponse(
        {"ok": True, "position": _serialize_position(pos, depth=_position_depth(pos))}
    )


@biota_login_required
@nav_permission_required("contracts")
@write_permission_required
@require_http_methods(["DELETE", "POST"])
def contracts_api_position_delete(request, pk: int):
    pos = get_object_or_404(WorkContractPosition, pk=pk)
    pos.delete()
    return JsonResponse({"ok": True})


@biota_login_required
@nav_permission_required("contracts")
@write_permission_required
@require_http_methods(["POST"])
def contracts_api_position_stage(request, pk: int):
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    pos = get_object_or_404(
        WorkContractPosition.objects.prefetch_related("operations"), pk=pk
    )
    err = _set_position_stage(pos, body.get("stage"), body.get("current_operation_id"))
    if err:
        return _err(err)
    pos.save(update_fields=["stage", "current_operation"])
    pos = _load_position(pos.pk)
    return JsonResponse(
        {"ok": True, "position": _serialize_position(pos, depth=_position_depth(pos))}
    )


@biota_login_required
@nav_permission_required("contracts")
@write_permission_required
@require_http_methods(["POST"])
def contracts_api_position_split(request, pk: int):
    """Отрыв: часть количества уходит в дочернюю позицию со своим этапом."""
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    parent = get_object_or_404(
        WorkContractPosition.objects.prefetch_related("operations").select_related("parent"),
        pk=pk,
    )
    qty = _clamp_int(body.get("quantity"), 0, 0, 1_000_000)
    if qty < 1:
        return _err("Укажите количество отрыва")
    if qty >= int(parent.quantity or 0):
        return _err("Отрыв должен быть меньше текущего количества (оставьте хотя бы 1 шт.)")
    if _position_depth(parent) >= 8:
        return _err("Слишком глубокая вложенность отрывов")
    if parent.contract.positions.count() >= MAX_POSITIONS:
        return _err(f"Лимит позиций в контракте: {MAX_POSITIONS}")

    with transaction.atomic():
        parent.quantity = int(parent.quantity) - qty
        parent.save(update_fields=["quantity"])
        child = WorkContractPosition.objects.create(
            contract_id=parent.contract_id,
            parent=parent,
            name=parent.name,
            description=parent.description or "",
            quantity=qty,
            sort_order=parent.sort_order,
            stage=WorkContractPosition.STAGE_NOT_STARTED,
        )
        for i, op in enumerate(parent.operations.order_by("sort_order", "id")):
            WorkPositionOperation.objects.create(
                position=child,
                name=op.name,
                description=op.description or "",
                sort_order=i,
            )

    parent = _load_position(parent.pk)
    child = _load_position(child.pk)
    return JsonResponse(
        {
            "ok": True,
            "parent": _serialize_position(parent, depth=_position_depth(parent)),
            "child": _serialize_position(child, depth=_position_depth(child)),
        }
    )


@biota_login_required
@nav_permission_required("contracts")
@write_permission_required
@require_http_methods(["POST"])
def contracts_api_operations_replace(request, pk: int):
    """Заменить весь список операций изделия (с порядком)."""
    body = _json_body(request)
    if body is None:
        return _err("Некорректный JSON")
    pos = get_object_or_404(WorkContractPosition, pk=pk)
    if not isinstance(body.get("operations"), list):
        return _err("Укажите список операций")
    cleaned = _clean_operations_payload(body.get("operations"))
    with transaction.atomic():
        old_current_name = (
            pos.current_operation.name
            if pos.stage == WorkContractPosition.STAGE_OPERATION and pos.current_operation_id
            else ""
        )
        pos.operations.all().delete()
        created = []
        for i, (name, note) in enumerate(cleaned):
            created.append(
                WorkPositionOperation.objects.create(
                    position=pos, name=name, description=note, sort_order=i
                )
            )
        # сохранить текущий этап, если операция с тем же именем осталась
        if old_current_name:
            match = next((o for o in created if o.name == old_current_name), None)
            if match:
                pos.current_operation = match
                pos.stage = WorkContractPosition.STAGE_OPERATION
            else:
                pos.current_operation = None
                pos.stage = WorkContractPosition.STAGE_NOT_STARTED
            pos.save(update_fields=["current_operation", "stage"])
        elif pos.stage == WorkContractPosition.STAGE_OPERATION:
            pos.current_operation = None
            pos.stage = WorkContractPosition.STAGE_NOT_STARTED
            pos.save(update_fields=["current_operation", "stage"])
    pos = _load_position(pos.pk)
    return JsonResponse(
        {"ok": True, "position": _serialize_position(pos, depth=_position_depth(pos))}
    )
