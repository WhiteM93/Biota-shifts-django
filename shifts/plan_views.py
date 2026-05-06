"""Раздел «План»: изделия и маршрут по отделам."""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts.auth import _is_admin, user_is_executor

from .auth_utils import biota_login_required, biota_user, nav_permission_required
from .models import (
    PLANNED_PRODUCT_WORKPIECE_TYPE_CHOICES,
    PLANNED_PRODUCT_WORKPIECE_TYPE_VALUES,
    PlanContract,
    PlanContractLine,
    PlannedAssemblyComponent,
    PlannedProduct,
    PlannedProductStage,
)
from .plan_departments import (
    PLAN_DEPARTMENT_SLUG_TO_NAME,
    PLAN_RAIL_PKI_SLUG,
    PLANNED_PRODUCT_DEPARTMENT_CHOICES,
    PLANNED_PRODUCT_DEPARTMENT_VALUES,
)
from .plan_naladki_bridge import finalize_plan_piece_naladki_link
from .plan_usage import (
    contract_lines_and_bom_map,
    product_assembly_usage_rows,
    product_contract_usage_rows,
)

# Совпадает с логикой подсказок названий в shifts/product_views.py (наладки).
_NAME_STOP = {
    "корпус",
    "изделие",
    "деталь",
    "сборка",
    "сб",
}


def _name_tokens(text: str) -> list[str]:
    src = (text or "").lower()
    tokens = re.findall(r"[0-9a-zа-яё]+", src, flags=re.IGNORECASE)
    return [t for t in tokens if t]


def _meaningful_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for t in tokens:
        if t in _NAME_STOP:
            continue
        if len(t) < 3:
            continue
        out.append(t)
    return out


def _parse_assembly_qty(raw: str | None) -> tuple[int | None, str | None]:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        return 1, None
    try:
        val = int(s)
    except ValueError:
        try:
            val = int(float(s))
        except ValueError:
            return None, "Укажите целое количество в составе сборки."
    if val < 1:
        return None, "Количество в составе должно быть не меньше 1."
    if val > 1_000_000:
        return None, "Слишком большое количество."
    return val, None


def _bom_rows_post(request) -> list[dict[str, str]]:
    ids = request.POST.getlist("bom_planned_id")
    names = request.POST.getlist("bom_component_name")
    qtys = request.POST.getlist("bom_component_qty")
    n = max(len(ids), len(names), len(qtys))
    rows: list[dict[str, str]] = []
    for i in range(n):
        pid = str(ids[i]).strip() if i < len(ids) else ""
        nm = str(names[i]).strip() if i < len(names) else ""
        qty = str(qtys[i]).strip() if i < len(qtys) else "1"
        rows.append({"pk": pid, "name": nm, "qty": qty})
    return rows or [{"pk": "", "name": "", "qty": "1"}]


def _bom_rows_initial(item: PlannedProduct | None) -> list[dict[str, str]]:
    if not item or not item.is_assembly:
        return [{"pk": "", "name": "", "qty": "1"}]
    lines = list(
        item.assembly_components.order_by("sort_order", "id")
        .select_related("component")
    )
    if not lines:
        return [{"pk": "", "name": "", "qty": "1"}]
    return [{"pk": str(x.component_id), "name": x.component.name, "qty": str(x.quantity)} for x in lines]


def _resolve_bom_lines(
    *,
    assembly_pk: int | None,
    assembly_name: str,
    bom_rows: list[dict[str, str]],
) -> tuple[list[tuple[PlannedProduct, int]] | None, str | None]:
    """Строки формы → упорядоченные пары (компонент, кол-во на комплект); дубликаты компонента складываются."""
    merged: dict[int, tuple[PlannedProduct, int]] = {}
    order_ids: list[int] = []
    an_key = (assembly_name or "").strip().casefold()

    for row in bom_rows:
        pid_raw = (row.get("pk") or "").strip()
        nm = (row.get("name") or "").strip()
        if not pid_raw and not nm:
            continue

        qty_int, qty_err = _parse_assembly_qty(row.get("qty"))
        if qty_err:
            return None, qty_err
        assert qty_int is not None

        comp: PlannedProduct | None = None
        if pid_raw.isdigit():
            comp = PlannedProduct.objects.filter(pk=int(pid_raw)).first()
            if comp is None:
                return None, "Указано изделие из состава по id — запись не найдена."
        elif nm:
            if assembly_pk is None and an_key and nm.casefold() == an_key:
                return (
                    None,
                    "Строка состава совпадает с названием этой сборки — укажите другое входящее изделие.",
                )
            comp = PlannedProduct.objects.filter(name__iexact=nm).first()
            if comp is None:
                comp = PlannedProduct.objects.create(name=nm, is_assembly=False)
        else:
            continue

        assert comp is not None
        if assembly_pk is not None and comp.pk == assembly_pk:
            return None, "Нельзя включить изделие в состав самого себя."

        if comp.pk in merged:
            p, prev_q = merged[comp.pk]
            merged[comp.pk] = (p, prev_q + qty_int)
        else:
            merged[comp.pk] = (comp, qty_int)
            order_ids.append(comp.pk)

    return [(merged[k][0], merged[k][1]) for k in order_ids], None


def _normalize_plan_product_type(raw: str | None) -> str:
    t = (raw or "made").strip().lower()
    return t if t in ("made", "assembly", "pki") else "made"


def _flags_from_plan_product_type(t: str) -> tuple[bool, bool]:
    if t == "assembly":
        return True, False
    if t == "pki":
        return False, True
    return False, False


def _workpiece_type_form_value(plan_product_type: str, post) -> str:
    """Значение для поля формы после ошибки: только допустимый код или пусто."""
    if plan_product_type != "made":
        return ""
    raw = (post.get("workpiece_type") or "").strip()
    return raw if raw in PLANNED_PRODUCT_WORKPIECE_TYPE_VALUES else ""


def _workpiece_type_initial(item: PlannedProduct | None) -> str:
    if not item or item.is_assembly or item.is_purchased:
        return ""
    return (item.workpiece_type or "").strip()


def _laser_thickness_input_value(item: PlannedProduct | None) -> str:
    if not item or item.laser_sheet_thickness_mm is None:
        return ""
    d = item.laser_sheet_thickness_mm
    s = format(d, "f").rstrip("0").rstrip(".")
    return s if s else "0"


def _laser_material_marking_input_value(item: PlannedProduct | None) -> str:
    if not item:
        return ""
    return (item.laser_material_marking or "").strip()


def _laser_material_marking_suggestions() -> list[str]:
    """Уникальные маркировки по плану (без учёта регистра); в списке — как сохранено в первой записи."""
    rows = (
        PlannedProduct.objects.filter(workpiece_type="laser")
        .exclude(laser_material_marking="")
        .order_by("id")
        .values_list("laser_material_marking", flat=True)
    )
    seen: set[str] = set()
    out: list[str] = []
    for raw in rows:
        s = (raw or "").strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _parse_laser_sheet_thickness_mm(raw: str | None) -> tuple[Decimal | None, str | None]:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        return None, "Укажите толщину листа, мм."
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None, "Толщина листа: введите число (мм)."
    if d <= 0:
        return None, "Толщина листа должна быть больше нуля."
    if d > Decimal("500"):
        return None, "Слишком большая толщина листа."
    return d, None


def _plan_product_type_from_item(item: PlannedProduct | None) -> str:
    if item and item.is_assembly:
        return "assembly"
    if item and item.is_purchased:
        return "pki"
    return "made"


def _edit_form_context(
    *,
    item: PlannedProduct | None,
    name_value: str,
    plan_product_type: str,
    workpiece_type_value: str,
    laser_sheet_thickness_value: str = "",
    laser_material_marking_value: str = "",
    stage_rows: list[dict[str, str]],
    bom_rows: list[dict[str, str]],
) -> dict:
    if item and item.pk:
        usage_contract_rows, usage_contract_sum = product_contract_usage_rows(item.pk)
        usage_assembly_rows = product_assembly_usage_rows(item.pk)
    else:
        usage_contract_rows, usage_contract_sum, usage_assembly_rows = [], 0, []

    return {
        "item": item,
        "name_value": name_value,
        "plan_product_type": _normalize_plan_product_type(plan_product_type),
        "workpiece_type_value": workpiece_type_value,
        "workpiece_type_choices": PLANNED_PRODUCT_WORKPIECE_TYPE_CHOICES,
        "laser_sheet_thickness_value": laser_sheet_thickness_value,
        "laser_material_marking_value": laser_material_marking_value,
        "laser_material_marking_suggestions": _laser_material_marking_suggestions(),
        "stage_rows": stage_rows,
        "bom_rows": bom_rows,
        "department_choices": PLANNED_PRODUCT_DEPARTMENT_CHOICES,
        "plan_department_choices": PLANNED_PRODUCT_DEPARTMENT_CHOICES,
        "usage_contract_rows": usage_contract_rows,
        "usage_contract_sum": usage_contract_sum,
        "usage_assembly_rows": usage_assembly_rows,
        "usage_highlight_contract_pk": None,
    }


def _stage_rows_for_form(
    post_depts: list[str] | None,
    post_notes: list[str] | None,
    stages_initial: list[PlannedProductStage] | None,
) -> list[dict[str, str]]:
    if post_depts is not None:
        rows: list[dict[str, str]] = []
        notes = post_notes or []
        for i, d in enumerate(post_depts):
            note = notes[i] if i < len(notes) else ""
            rows.append({"dept": str(d), "note": str(note)})
        return rows or [{"dept": "", "note": ""}]
    if stages_initial:
        return [{"dept": s.department, "note": s.description or ""} for s in stages_initial]
    return [{"dept": "", "note": ""}]


def _redirect_executors_from_edit(request, user: str | None, item: PlannedProduct | None):
    if not user_is_executor(user) or _is_admin(user or ""):
        return None
    messages.info(request, "Редактирование изделий плана доступно только руководителям.")
    if item:
        return redirect("plan_article_detail", pk=item.pk)
    return redirect("plan")


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET"])
def plan_product_name_suggestions_view(request):
    """Подсказки по названию изделий плана (как у наладок)."""
    q = (request.GET.get("q") or "").strip()
    exclude_id_raw = (request.GET.get("exclude_id") or "").strip()
    exclude_id = int(exclude_id_raw) if exclude_id_raw.isdigit() else None
    if len(q) < 2:
        return JsonResponse({"ok": True, "items": []})

    qs = PlannedProduct.objects.all()
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)

    q_tokens_all = _name_tokens(q)
    q_tokens = _meaningful_tokens(q_tokens_all)
    q_numeric_tokens = [t for t in q_tokens_all if any(ch.isdigit() for ch in t) and len(t) >= 4]

    cond = Q(name__icontains=q)
    for t in q_tokens[:3]:
        cond |= Q(name__icontains=t)

    candidates = list(qs.filter(cond).order_by("-updated_at", "name").values("id", "name")[:60])
    scored = []
    for row in candidates:
        name = row.get("name") or ""
        name_tokens_all = _name_tokens(name)
        name_tokens = set(_meaningful_tokens(name_tokens_all))
        if q_numeric_tokens:
            name_numeric = {t for t in name_tokens_all if any(ch.isdigit() for ch in t) and len(t) >= 4}
            if not any(t in name_numeric for t in q_numeric_tokens):
                continue
        if q_tokens:
            inter = len(set(q_tokens) & name_tokens)
            score = inter / max(len(set(q_tokens)), 1)
            if score < 0.6 and q.lower() not in name.lower():
                continue
        scored.append(row)
        if len(scored) >= 8:
            break

    return JsonResponse({"ok": True, "items": scored})


_PLAN_INDEX_VIEWS = frozenset({"all", "assembly", "purchased", "made"})


def _pki_totals_via_contract_lines() -> dict[int, int]:
    """
    Суммарное количество ПКИ по всем строкам контрактов:
    — прямой учёт строк, где позиция = ПКИ;
    — если строка указывает на сборку, обход BOM (рекурсивно), количество умножается цепочкой на комплект.
    """
    lines, bom_map = contract_lines_and_bom_map()
    if not lines:
        return {}

    totals: dict[int, int] = defaultdict(int)

    def walk_assembly(assembly_pk: int, mult: int) -> None:
        for ac in bom_map.get(assembly_pk, []):
            eff = mult * ac.quantity
            comp = ac.component
            if comp.is_purchased:
                totals[comp.pk] += eff
            elif comp.is_assembly:
                walk_assembly(comp.pk, eff)

    for ln in lines:
        p = ln.product
        q_ln = max(1, int(ln.quantity))
        if p.is_purchased:
            totals[p.pk] += q_ln
        elif p.is_assembly:
            walk_assembly(p.pk, q_ln)

    return dict(totals)


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD"])
def plan_department_planning(request, slug: str):
    slug_l = str(slug or "").strip().lower()
    if slug_l == PLAN_RAIL_PKI_SLUG:
        pid_to_qty = _pki_totals_via_contract_lines()
        if not pid_to_qty:
            rows = []
        else:
            products = PlannedProduct.objects.filter(pk__in=pid_to_qty.keys()).order_by("name")
            rows = [{"product": p, "qty": pid_to_qty[p.pk]} for p in products]
        return render(
            request,
            "shifts/plan/department_planning.html",
            {
                "plan_scope_title": "ПКИ по всем контрактам",
                "planning_mode": "pki",
                "department_label": "",
                "pki_rows": rows,
                "contract_blocks": [],
                "plan_department_choices": PLANNED_PRODUCT_DEPARTMENT_CHOICES,
            },
        )

    dept = PLAN_DEPARTMENT_SLUG_TO_NAME.get(slug_l)
    if dept is None:
        raise Http404("Неизвестный отдел.")

    product_ids = PlannedProductStage.objects.filter(department=dept).values_list(
        "product_id", flat=True
    ).distinct()
    pids_with_dept = frozenset(product_ids)

    contract_blocks: list[dict] = []
    if pids_with_dept:
        lines, bom_map = contract_lines_and_bom_map()
        cmap: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))

        def walk_department(contract_id: int, product_id: int, mult: int) -> None:
            if product_id in pids_with_dept:
                cmap[contract_id][product_id] += mult
            for ac in bom_map.get(product_id, []):
                walk_department(contract_id, ac.component_id, mult * ac.quantity)

        if lines:
            for ln in lines:
                walk_department(
                    ln.contract_id,
                    ln.product_id,
                    max(1, int(ln.quantity)),
                )

            cids_nonempty = sorted(
                {cid for cid, pmap in cmap.items() if any(q > 0 for q in pmap.values())},
            )
            if cids_nonempty:
                contracts_by_pk = PlanContract.objects.in_bulk(cids_nonempty)
                all_pids_for_rows: set[int] = set()
                for cid in cids_nonempty:
                    for pid, qty in cmap[cid].items():
                        if qty > 0:
                            all_pids_for_rows.add(pid)
                bulk_prods = PlannedProduct.objects.in_bulk(all_pids_for_rows)

                def _contract_sort_key(cid: int) -> tuple:
                    c = contracts_by_pk.get(cid)
                    if c is None:
                        return (date.min, cid)
                    return (c.deadline, cid)

                for cid in sorted(cids_nonempty, key=_contract_sort_key):
                    c = contracts_by_pk.get(cid)
                    if c is None:
                        continue
                    pmap = cmap[cid]
                    inner = sorted(
                        (
                            (bulk_prods[pid], qty)
                            for pid, qty in pmap.items()
                            if pid in bulk_prods and qty > 0
                        ),
                        key=lambda t: ((t[0].name or "").lower(), t[0].pk),
                    )
                    if not inner:
                        continue
                    contract_blocks.append(
                        {
                            "contract": c,
                            "lines": [{"product": p, "qty": qty} for p, qty in inner],
                        },
                    )

    return render(
        request,
        "shifts/plan/department_planning.html",
        {
            "plan_scope_title": dept,
            "planning_mode": "dept",
            "department_label": dept,
            "pki_rows": [],
            "contract_blocks": contract_blocks,
            "plan_department_choices": PLANNED_PRODUCT_DEPARTMENT_CHOICES,
        },
    )


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD"])
def plan_index(request):
    view = (request.GET.get("view") or "assembly").strip().lower()
    if view not in _PLAN_INDEX_VIEWS:
        view = "assembly"

    qs = PlannedProduct.objects.annotate(stage_count=Count("stages"))
    if view == "assembly":
        qs = qs.filter(is_assembly=True)
    elif view == "purchased":
        qs = qs.filter(is_purchased=True)
    elif view == "made":
        qs = qs.filter(is_assembly=False, is_purchased=False)

    items = list(qs.order_by("-updated_at", "-id"))
    return render(
        request,
        "shifts/plan/index.html",
        {
            "items": items,
            "plan_view": view,
            "plan_department_choices": PLANNED_PRODUCT_DEPARTMENT_CHOICES,
        },
    )


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD"])
def plan_article_detail(request, pk: int):
    item = get_object_or_404(
        PlannedProduct.objects.select_related("naladki_product").prefetch_related(
            "stages", "assembly_components__component"
        ),
        pk=pk,
    )
    usage_contract_rows, usage_contract_sum = product_contract_usage_rows(item.pk)
    usage_assembly_rows = product_assembly_usage_rows(item.pk)
    return render(
        request,
        "shifts/plan/article_detail.html",
        {
            "item": item,
            "plan_department_choices": PLANNED_PRODUCT_DEPARTMENT_CHOICES,
            "usage_contract_rows": usage_contract_rows,
            "usage_contract_sum": usage_contract_sum,
            "usage_assembly_rows": usage_assembly_rows,
            "usage_highlight_contract_pk": None,
        },
    )


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD", "POST"])
def plan_article_edit(request, pk: int | None = None):
    user = biota_user(request)
    item = None if pk is None else get_object_or_404(
        PlannedProduct.objects.prefetch_related("stages", "assembly_components__component"),
        pk=pk,
    )

    r = _redirect_executors_from_edit(request, user, item)
    if r is not None:
        return r

    stages_initial: list[PlannedProductStage] = []
    if item:
        stages_initial = list(item.stages.all())

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        plan_product_type = _normalize_plan_product_type(request.POST.get("plan_product_type"))
        is_assembly, is_purchased = _flags_from_plan_product_type(plan_product_type)
        depts = request.POST.getlist("stage_department")
        notes = request.POST.getlist("stage_description")
        bom_rows = _bom_rows_post(request)
        while len(notes) < len(depts):
            notes.append("")

        wp_form_val = _workpiece_type_form_value(plan_product_type, request.POST)
        wp_raw = (request.POST.get("workpiece_type") or "").strip()
        laser_form_kw = {
            "laser_sheet_thickness_value": (request.POST.get("laser_sheet_thickness_mm") or "").strip(),
            "laser_material_marking_value": (request.POST.get("laser_material_marking") or "").strip(),
        }

        if not name:
            messages.error(request, "Укажите название изделия.")
            rows = _stage_rows_for_form(depts, notes, None)
            return render(
                request,
                "shifts/plan/article_edit.html",
                _edit_form_context(
                    item=item,
                    name_value=name,
                    plan_product_type=plan_product_type,
                    workpiece_type_value=wp_form_val,
                    stage_rows=rows,
                    bom_rows=bom_rows,
                    **laser_form_kw,
                ),
            )

        if plan_product_type == "made":
            if wp_raw not in PLANNED_PRODUCT_WORKPIECE_TYPE_VALUES:
                messages.error(
                    request,
                    "Для изделия выберите тип заготовки: Заготовительный, Лазерный или ПКИ.",
                )
                rows = _stage_rows_for_form(depts, notes, None)
                return render(
                    request,
                    "shifts/plan/article_edit.html",
                    _edit_form_context(
                        item=item,
                        name_value=name,
                        plan_product_type=plan_product_type,
                        workpiece_type_value=wp_form_val,
                        stage_rows=rows,
                        bom_rows=bom_rows,
                        **laser_form_kw,
                    ),
                )

        workpiece_type_stored = wp_raw if plan_product_type == "made" else ""

        laser_thick_dec: Decimal | None = None
        laser_mark_stored = ""
        if workpiece_type_stored == "laser":
            laser_thick_dec, terr = _parse_laser_sheet_thickness_mm(laser_form_kw["laser_sheet_thickness_value"])
            if terr:
                messages.error(request, terr)
                rows = _stage_rows_for_form(depts, notes, None)
                return render(
                    request,
                    "shifts/plan/article_edit.html",
                    _edit_form_context(
                        item=item,
                        name_value=name,
                        plan_product_type=plan_product_type,
                        workpiece_type_value=wp_form_val,
                        stage_rows=rows,
                        bom_rows=bom_rows,
                        **laser_form_kw,
                    ),
                )
            if not laser_form_kw["laser_material_marking_value"]:
                messages.error(request, "Укажите маркировку материала для лазерной заготовки.")
                rows = _stage_rows_for_form(depts, notes, None)
                return render(
                    request,
                    "shifts/plan/article_edit.html",
                    _edit_form_context(
                        item=item,
                        name_value=name,
                        plan_product_type=plan_product_type,
                        workpiece_type_value=wp_form_val,
                        stage_rows=rows,
                        bom_rows=bom_rows,
                        **laser_form_kw,
                    ),
                )
            laser_mark_stored = laser_form_kw["laser_material_marking_value"]

        stages_clean: list[tuple[str, str]] = []
        for d_raw, note in zip(depts, notes):
            d = (d_raw or "").strip()
            if not d:
                continue
            if d not in PLANNED_PRODUCT_DEPARTMENT_VALUES:
                messages.error(request, "Выбран неизвестный отдел — обновите страницу и попробуйте снова.")
                rows = _stage_rows_for_form(depts, notes, None)
                return render(
                    request,
                    "shifts/plan/article_edit.html",
                    _edit_form_context(
                        item=item,
                        name_value=name,
                        plan_product_type=plan_product_type,
                        workpiece_type_value=wp_form_val,
                        stage_rows=rows,
                        bom_rows=bom_rows,
                        **laser_form_kw,
                    ),
                )
            stages_clean.append((d, (note or "").strip()))

        bom_lines_resolved: list[tuple[PlannedProduct, int]] = []
        if is_assembly:
            resolved, bom_err = _resolve_bom_lines(
                assembly_pk=item.pk if item else None,
                assembly_name=name,
                bom_rows=bom_rows,
            )
            if bom_err:
                messages.error(request, bom_err)
                rows = _stage_rows_for_form(depts, notes, None)
                return render(
                    request,
                    "shifts/plan/article_edit.html",
                    _edit_form_context(
                        item=item,
                        name_value=name,
                        plan_product_type=plan_product_type,
                        workpiece_type_value=wp_form_val,
                        stage_rows=rows,
                        bom_rows=bom_rows,
                        **laser_form_kw,
                    ),
                )
            assert resolved is not None
            bom_lines_resolved = resolved
            if not bom_lines_resolved:
                messages.error(request, "Для сборочного изделия укажите хотя бы одно входящее изделие в составе.")
                rows = _stage_rows_for_form(depts, notes, None)
                return render(
                    request,
                    "shifts/plan/article_edit.html",
                    _edit_form_context(
                        item=item,
                        name_value=name,
                        plan_product_type=plan_product_type,
                        workpiece_type_value=wp_form_val,
                        stage_rows=rows,
                        bom_rows=bom_rows,
                        **laser_form_kw,
                    ),
                )

        with transaction.atomic():
            if item is None:
                item = PlannedProduct.objects.create(
                    name=name,
                    is_assembly=is_assembly,
                    is_purchased=is_purchased,
                    workpiece_type=workpiece_type_stored,
                    laser_sheet_thickness_mm=laser_thick_dec,
                    laser_material_marking=laser_mark_stored,
                )
            else:
                item.name = name
                item.is_assembly = is_assembly
                item.is_purchased = is_purchased
                item.workpiece_type = workpiece_type_stored
                item.laser_sheet_thickness_mm = laser_thick_dec
                item.laser_material_marking = laser_mark_stored
                item.save(
                    update_fields=(
                        "name",
                        "is_assembly",
                        "is_purchased",
                        "workpiece_type",
                        "laser_sheet_thickness_mm",
                        "laser_material_marking",
                        "updated_at",
                    )
                )
            item.stages.all().delete()
            PlannedProductStage.objects.bulk_create(
                [
                    PlannedProductStage(product=item, sort_order=i, department=dep, description=desc)
                    for i, (dep, desc) in enumerate(stages_clean)
                ]
            )
            item.assembly_components.all().delete()
            if is_assembly and bom_lines_resolved:
                PlannedAssemblyComponent.objects.bulk_create(
                    [
                        PlannedAssemblyComponent(
                            assembly=item,
                            component=c,
                            sort_order=i,
                            quantity=q,
                        )
                        for i, (c, q) in enumerate(bom_lines_resolved)
                    ]
                )

            finalize_plan_piece_naladki_link(item.pk)

        messages.success(request, "Изделие и маршрут сохранены.")
        return redirect("plan_article_detail", pk=item.pk)

    rows = _stage_rows_for_form(None, None, stages_initial if stages_initial else None)
    bom_init = _bom_rows_initial(item)
    return render(
        request,
        "shifts/plan/article_edit.html",
        _edit_form_context(
            item=item,
            name_value=item.name if item else "",
            plan_product_type=_plan_product_type_from_item(item),
            workpiece_type_value=_workpiece_type_initial(item),
            laser_sheet_thickness_value=_laser_thickness_input_value(item),
            laser_material_marking_value=_laser_material_marking_input_value(item),
            stage_rows=rows,
            bom_rows=bom_init,
        ),
    )


@biota_login_required
@nav_permission_required("plan")
@require_POST
def plan_article_delete(request, pk: int):
    user = biota_user(request)
    item = get_object_or_404(PlannedProduct, pk=pk)
    r = _redirect_executors_from_edit(request, user, item)
    if r is not None:
        return r
    item.delete()
    messages.success(request, "Изделие удалено.")
    return redirect("plan")
