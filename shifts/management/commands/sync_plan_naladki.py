"""Одноразово или после импортов — выровнять связи позиций плана (обычное изделие) с карточками наладок."""

from django.core.management.base import BaseCommand
from django.db import transaction

from shifts.models import PlannedProduct, Product
from shifts.plan_naladki_bridge import (
    finalize_plan_piece_naladki_link,
    sync_plan_piece_for_naladki_in_same_transaction,
)


class Command(BaseCommand):
    help = "Привязка/создание связей «План (изделие)» ↔ «Наладки» для уже существующих записей"

    def handle(self, *args, **options):
        n_plan = n_prod = 0
        for prod in Product.objects.order_by("id").iterator(chunk_size=200):
            with transaction.atomic():
                sync_plan_piece_for_naladki_in_same_transaction(prod.pk)
            n_prod += 1
        for pp in PlannedProduct.objects.filter(is_assembly=False, is_purchased=False).order_by(
            "id"
        ).iterator(chunk_size=200):
            with transaction.atomic():
                finalize_plan_piece_naladki_link(pp.pk)
            n_plan += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: обработано карточек наладок: {n_prod}, позиций плана-как-изделие: {n_plan}"
            )
        )
