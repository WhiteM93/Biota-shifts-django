"""Сигналы моделей: автосвязь «Наладки» → «План» при любом сохранении Product."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Product
from .plan_naladki_bridge import ensure_plan_piece_for_naladki_product


@receiver(post_save, sender=Product)
def sync_plan_piece_after_product_save(sender, instance, **kwargs):
    """Создание/привязка PlannedProduct для карточки наладки (в т.ч. админка, импорты, shell)."""
    ensure_plan_piece_for_naladki_product(instance.pk)


def _connect_inventory_notify_signals() -> None:
    from shifts.models import InventoryStockEvent, StockMovement

    @receiver(post_save, sender=StockMovement)
    def notify_after_stock_movement(sender, instance, created, **kwargs):
        if not created:
            return
        from biota_shifts.inventory_notify import try_notify_stock_movement

        try_notify_stock_movement(instance.pk)

    @receiver(post_save, sender=InventoryStockEvent)
    def notify_after_inventory_event(sender, instance, created, **kwargs):
        if not created:
            return
        from biota_shifts.inventory_notify import try_notify_inventory_event

        try_notify_inventory_event(instance.pk)


_connect_inventory_notify_signals()
