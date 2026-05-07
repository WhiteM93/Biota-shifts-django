"""Сигналы моделей: автосвязь «Наладки» → «План» при любом сохранении Product."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Product
from .plan_naladki_bridge import ensure_plan_piece_for_naladki_product


@receiver(post_save, sender=Product)
def sync_plan_piece_after_product_save(sender, instance, **kwargs):
    """Создание/привязка PlannedProduct для карточки наладки (в т.ч. админка, импорты, shell)."""
    ensure_plan_piece_for_naladki_product(instance.pk)
