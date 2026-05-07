"""Расчёт использования позиций плана в контрактах (с разбором BOM) и в составе сборок."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import PlanContract, PlanContractLine, PlannedAssemblyComponent


def contract_lines_and_bom_map() -> tuple[
    list[PlanContractLine],
    dict[int, list[PlannedAssemblyComponent]],
]:
    """
    Все строки контрактов и карта состава сборок (вложенность), нужная для обходов по BOM.
    """
    lines = list(
        PlanContractLine.objects.select_related("product", "contract"),
    )
    if not lines:
        return [], {}

    root_ids = {ln.product_id for ln in lines}
    need_bom = set(root_ids)
    expanding = True
    while expanding:
        expanding = False
        sub_asm = set(
            PlannedAssemblyComponent.objects.filter(
                assembly_id__in=need_bom,
                component__is_assembly=True,
            ).values_list("component_id", flat=True),
        )
        for cid in sub_asm:
            if cid not in need_bom:
                need_bom.add(cid)
                expanding = True

    bom_map: dict[int, list[PlannedAssemblyComponent]] = defaultdict(list)
    ac_qs = (
        PlannedAssemblyComponent.objects.filter(assembly_id__in=need_bom)
        .select_related("component")
        .order_by("assembly_id", "sort_order", "id")
    )
    for ac in ac_qs:
        bom_map[ac.assembly_id].append(ac)

    return lines, bom_map


def bom_contribution_from_root(
    bom_map: dict[int, list[PlannedAssemblyComponent]],
    root_pid: int,
    root_mult: int,
    target_pid: int,
) -> int:
    """Сколько единиц target_pid даёт одна строка контракта (корень root_pid, множитель root_mult)."""

    total = 0

    def walk(pid: int, mult: int) -> None:
        nonlocal total
        if pid == target_pid:
            total += mult
        for ac in bom_map.get(pid, []):
            walk(ac.component_id, mult * ac.quantity)

    walk(root_pid, root_mult)
    return total


def product_contract_usage_rows(product_pk: int) -> tuple[list[dict[str, Any]], int]:
    """
    По контрактам: полное количество позиции product_pk с учётом всех путей через составы.
    qty_direct — сумма по строкам контракта «напрямую»; qty_via_assemblies = qty_total - qty_direct.
    """
    lines, bom_map = contract_lines_and_bom_map()
    eff_by_c: dict[int, int] = defaultdict(int)
    for ln in lines:
        add = bom_contribution_from_root(
            bom_map,
            ln.product_id,
            max(1, int(ln.quantity)),
            product_pk,
        )
        if add:
            eff_by_c[ln.contract_id] += add

    direct_by_c: dict[int, int] = defaultdict(int)
    for ln in PlanContractLine.objects.filter(product_id=product_pk):
        direct_by_c[ln.contract_id] += ln.quantity

    cids = set(eff_by_c) | set(direct_by_c)
    if not cids:
        return [], 0

    contracts_ord = list(PlanContract.objects.filter(pk__in=cids).order_by("deadline", "id"))
    rows_out: list[dict[str, Any]] = []
    sum_all = 0
    for c in contracts_ord:
        e = int(eff_by_c.get(c.pk, 0))
        d = int(direct_by_c.get(c.pk, 0))
        if e == 0 and d == 0:
            continue
        if e < d:
            e = d
        via = max(0, e - d)
        rows_out.append(
            {
                "contract": c,
                "qty_total": e,
                "qty_direct": d,
                "qty_via_assemblies": via,
            }
        )
        sum_all += e
    return rows_out, sum_all


def product_assembly_usage_rows(product_pk: int) -> list[dict[str, Any]]:
    """Сборки, в составе которых указана позиция, с количеством «на 1 комплект» родителя."""
    acs = (
        PlannedAssemblyComponent.objects.filter(component_id=product_pk)
        .select_related("assembly")
        .order_by("assembly__name", "assembly_id", "sort_order", "id")
    )
    return [{"assembly": ac.assembly, "qty_per_kit": ac.quantity} for ac in acs]
