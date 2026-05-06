"""Связь позиций плана (обычное изделие) с карточками наладок (Product): автосоздание и синхрон имён."""

from __future__ import annotations

from django.db import transaction

from .models import PlannedProduct, Product


def plan_piece_is_linked_type(plan: PlannedProduct) -> bool:
    """Позиция типа «изделие»: не сборка и не ПКИ — ей соответствует карточка наладки."""
    return not plan.is_assembly and not plan.is_purchased


def _ensure_plan_piece_for_naladki_locked(product_pk: int) -> PlannedProduct | None:
    """Вызывается уже внутри transaction.atomic."""
    product = Product.objects.select_for_update().get(pk=product_pk)
    nm_full = product.name.strip()
    nm_plan = (nm_full[:400] if nm_full else (product.name or "")[:400]).strip()

    linked = PlannedProduct.objects.select_for_update().filter(naladki_product_id=product.pk).first()
    if linked:
        if linked.name.strip() != nm_plan:
            linked.name = nm_plan
            linked.save(update_fields=["name", "updated_at"])
        return linked

    orphan = (
        PlannedProduct.objects.select_for_update()
        .filter(
            name__iexact=nm_plan,
            is_assembly=False,
            is_purchased=False,
            naladki_product__isnull=True,
        )
        .order_by("-updated_at", "-id")
        .first()
    )
    if orphan:
        orphan.naladki_product_id = product.pk
        orphan.save(update_fields=["naladki_product_id", "updated_at"])
        return orphan

    return PlannedProduct.objects.create(
        name=nm_plan or nm_full[:400],
        is_assembly=False,
        is_purchased=False,
        naladki_product_id=product.pk,
    )


def ensure_plan_piece_for_naladki_product(product_pk: int) -> PlannedProduct | None:
    """После сохранения карточки наладки (отдельная транзакция)."""
    with transaction.atomic():
        return _ensure_plan_piece_for_naladki_locked(product_pk)


def sync_plan_piece_for_naladki_in_same_transaction(product_pk: int) -> PlannedProduct | None:
    """То же, что обеспечение связи — вызывать уже внутри transaction.atomic представления."""
    return _ensure_plan_piece_for_naladki_locked(product_pk)


def finalize_plan_piece_naladki_link(plan_pk: int) -> None:
    """Вызывается внутри уже открытого transaction.atomic после сохранения PlannedProduct."""
    plan = PlannedProduct.objects.select_for_update().get(pk=plan_pk)

    if not plan_piece_is_linked_type(plan):
        if plan.naladki_product_id:
            plan.naladki_product = None
            plan.save(update_fields=["naladki_product_id", "updated_at"])
        return

    full_name = plan.name.strip()
    nm = full_name[:300]
    if plan.naladki_product_id:
        prod = Product.objects.select_for_update().get(pk=plan.naladki_product_id)
        if prod.name.strip() != nm:
            prod.name = nm
            prod.save(update_fields=["name", "updated_at"])
        return

    for prod in Product.objects.select_for_update().filter(name__iexact=nm).order_by("-updated_at", "-id"):
        taken = PlannedProduct.objects.filter(naladki_product_id=prod.pk).exclude(pk=plan.pk).exists()
        if taken:
            continue
        plan.naladki_product_id = prod.pk
        plan.save(update_fields=["naladki_product_id", "updated_at"])
        return

    prod_new = Product.objects.create(name=nm or full_name[:300])
    plan.naladki_product_id = prod_new.pk
    plan.save(update_fields=["naladki_product_id", "updated_at"])
