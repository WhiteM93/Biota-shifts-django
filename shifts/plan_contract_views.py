"""Контракты раздела «План»: дедлайн и объёмы по позициям."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST, require_http_methods

from biota_shifts.auth import _is_admin, user_is_executor

from .auth_utils import biota_login_required, biota_user, nav_permission_required
from .models import PlanContract, PlanContractLine, PlannedProduct
from .plan_departments import PLANNED_PRODUCT_DEPARTMENT_CHOICES
from .plan_usage import product_assembly_usage_rows, product_contract_usage_rows


def _rail_ctx() -> dict:
    return {"plan_department_choices": PLANNED_PRODUCT_DEPARTMENT_CHOICES}


def _executor_write_block(request, user: str | None, contract: PlanContract | None):
    if not user_is_executor(user) or _is_admin(user or ""):
        return None
    messages.info(request, "Редактирование контрактов плана доступно только руководителям.")
    if contract:
        return redirect("plan_contract_detail", pk=contract.pk)
    return redirect("plan_contracts")


def _contract_rows_post(request) -> list[dict[str, str]]:
    ids = request.POST.getlist("line_planned_id")
    names = request.POST.getlist("line_product_name")
    qtys = request.POST.getlist("line_qty")
    n = max(len(ids), len(names), len(qtys))
    rows: list[dict[str, str]] = []
    for i in range(n):
        pid = str(ids[i]).strip() if i < len(ids) else ""
        nm = str(names[i]).strip() if i < len(names) else ""
        qty = str(qtys[i]).strip() if i < len(qtys) else "1"
        rows.append({"pk": pid, "name": nm, "qty": qty})
    return rows or [{"pk": "", "name": "", "qty": "1"}]


def _parse_line_qty_contract(raw: str | None) -> tuple[int | None, str | None]:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        return 1, None
    try:
        val = int(s)
    except ValueError:
        try:
            val = int(float(s))
        except ValueError:
            return None, "Укажите целое количество в строке контракта."
    if val < 1:
        return None, "Количество должно быть не меньше 1."
    if val > 1_000_000:
        return None, "Слишком большое количество."
    return val, None


def _parse_deadline(raw: str | None):
    s = (raw or "").strip()
    if not s:
        return None, "Укажите дедлайн контракта."
    d = parse_date(s)
    if d is None:
        return None, "Некорректная дата дедлайна."
    return d, None


def _resolve_contract_lines(
    rows: list[dict[str, str]],
) -> tuple[list[tuple[PlannedProduct, int]] | None, str | None]:
    merged: dict[int, tuple[PlannedProduct, int]] = {}
    order_ids: list[int] = []

    for row in rows:
        pid_raw = (row.get("pk") or "").strip()
        nm = (row.get("name") or "").strip()
        if not pid_raw and not nm:
            continue

        qty_int, qty_err = _parse_line_qty_contract(row.get("qty"))
        if qty_err:
            return None, qty_err

        prod: PlannedProduct | None = None
        if pid_raw.isdigit():
            prod = PlannedProduct.objects.filter(pk=int(pid_raw)).first()
            if prod is None:
                return None, "Указана позиция по id — запись в плане не найдена."
        elif nm:
            prod = PlannedProduct.objects.filter(name__iexact=nm).first()
            if prod is None:
                return (
                    None,
                    "Позиция с таким названием не найдена в плане. Выберите из подсказок или создайте позицию в плане.",
                )
        else:
            continue

        if prod.pk in merged:
            p, prev_q = merged[prod.pk]
            merged[prod.pk] = (p, prev_q + qty_int)
        else:
            merged[prod.pk] = (prod, qty_int)
            order_ids.append(prod.pk)

    return [(merged[k][0], merged[k][1]) for k in order_ids], None


def _rows_initial(contract: PlanContract | None) -> list[dict[str, str]]:
    if not contract:
        return [{"pk": "", "name": "", "qty": "1"}]
    lines = list(contract.lines.order_by("sort_order", "id").select_related("product"))
    if not lines:
        return [{"pk": "", "name": "", "qty": "1"}]
    return [{"pk": str(x.product_id), "name": x.product.name, "qty": str(x.quantity)} for x in lines]


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD"])
def plan_contract_article_detail(request, contract_pk: int, product_pk: int):
    contract = get_object_or_404(
        PlanContract.objects.annotate(
            total_qty=Coalesce(Sum("lines__quantity"), Value(0, output_field=IntegerField())),
        ),
        pk=contract_pk,
    )
    line = PlanContractLine.objects.select_related("contract", "product").filter(
        contract_id=contract_pk,
        product_id=product_pk,
    ).first()
    if line is None:
        raise Http404("Эта позиция не входит в выбранный контракт.")
    item = get_object_or_404(
        PlannedProduct.objects.select_related("naladki_product").prefetch_related(
            "stages", "assembly_components__component"
        ),
        pk=product_pk,
    )
    contracted_product_ids = frozenset(contract.lines.values_list("product_id", flat=True))
    bom_scaled: list[dict] = []
    if item.is_assembly:
        ac_list = sorted(
            item.assembly_components.all(),
            key=lambda ac: (ac.sort_order, ac.pk),
        )
        for ac in ac_list:
            bom_scaled.append(
                {
                    "ac": ac,
                    "per_kit": ac.quantity,
                    "in_contract": ac.quantity * line.quantity,
                    "in_contract_assembly": line.quantity,
                    "component_in_contract": ac.component_id in contracted_product_ids,
                }
            )

    usage_contract_rows, usage_contract_sum = product_contract_usage_rows(product_pk)
    usage_assembly_rows = product_assembly_usage_rows(product_pk)

    return render(
        request,
        "shifts/plan/contract_article_detail.html",
        {
            **_rail_ctx(),
            "contract": contract,
            "contract_line": line,
            "item": item,
            "bom_scaled": bom_scaled,
            "usage_contract_rows": usage_contract_rows,
            "usage_contract_sum": usage_contract_sum,
            "usage_assembly_rows": usage_assembly_rows,
            "usage_highlight_contract_pk": contract_pk,
        },
    )


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD"])
def plan_contract_index(request):
    contracts = list(
        PlanContract.objects.annotate(
            line_count=Count("lines"),
            total_qty=Coalesce(Sum("lines__quantity"), Value(0, output_field=IntegerField())),
        ).order_by("deadline", "-id")
    )
    return render(
        request,
        "shifts/plan/contracts_list.html",
        {**_rail_ctx(), "contracts": contracts},
    )


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD"])
def plan_contract_detail(request, pk: int):
    c = get_object_or_404(
        PlanContract.objects.annotate(
            total_qty=Coalesce(Sum("lines__quantity"), Value(0, output_field=IntegerField())),
        ).prefetch_related("lines__product"),
        pk=pk,
    )
    return render(
        request,
        "shifts/plan/contract_detail.html",
        {**_rail_ctx(), "contract": c},
    )


@biota_login_required
@nav_permission_required("plan")
@require_http_methods(["GET", "HEAD", "POST"])
def plan_contract_edit(request, pk: int | None = None):
    user = biota_user(request)
    contract = None if pk is None else get_object_or_404(PlanContract, pk=pk)

    r = _executor_write_block(request, user, contract)
    if r is not None:
        return r

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        deadline_raw = request.POST.get("deadline")
        rows = _contract_rows_post(request)

        deadline, derr = _parse_deadline(deadline_raw)
        if derr:
            messages.error(request, derr)
            return render(
                request,
                "shifts/plan/contract_edit.html",
                {
                    **_rail_ctx(),
                    "contract": contract,
                    "title_value": title,
                    "deadline_value": (deadline_raw or "").strip(),
                    "line_rows": rows,
                },
            )

        resolved, lerr = _resolve_contract_lines(rows)
        if lerr:
            messages.error(request, lerr)
            return render(
                request,
                "shifts/plan/contract_edit.html",
                {
                    **_rail_ctx(),
                    "contract": contract,
                    "title_value": title,
                    "deadline_value": (deadline_raw or "").strip(),
                    "line_rows": rows,
                },
            )
        assert resolved is not None
        if not resolved:
            messages.error(request, "Добавьте хотя бы одну позицию плана с количеством.")
            return render(
                request,
                "shifts/plan/contract_edit.html",
                {
                    **_rail_ctx(),
                    "contract": contract,
                    "title_value": title,
                    "deadline_value": (deadline_raw or "").strip(),
                    "line_rows": rows,
                },
            )

        with transaction.atomic():
            if contract is None:
                contract = PlanContract.objects.create(title=title, deadline=deadline)
            else:
                contract.title = title
                contract.deadline = deadline
                contract.save(update_fields=("title", "deadline", "updated_at"))
            contract.lines.all().delete()
            PlanContractLine.objects.bulk_create(
                [
                    PlanContractLine(
                        contract=contract,
                        product=p,
                        sort_order=i,
                        quantity=q,
                    )
                    for i, (p, q) in enumerate(resolved)
                ]
            )

        messages.success(request, "Контракт сохранён.")
        return redirect("plan_contract_detail", pk=contract.pk)

    init_rows = _rows_initial(contract)
    deadline_init = ""
    title_init = ""
    if contract:
        deadline_init = contract.deadline.isoformat()
        title_init = contract.title or ""

    return render(
        request,
        "shifts/plan/contract_edit.html",
        {
            **_rail_ctx(),
            "contract": contract,
            "title_value": title_init,
            "deadline_value": deadline_init,
            "line_rows": init_rows,
        },
    )


@biota_login_required
@nav_permission_required("plan")
@require_POST
def plan_contract_delete(request, pk: int):
    user = biota_user(request)
    c = get_object_or_404(PlanContract, pk=pk)
    r = _executor_write_block(request, user, c)
    if r is not None:
        return r
    c.delete()
    messages.success(request, "Контракт удалён.")
    return redirect("plan_contracts")
