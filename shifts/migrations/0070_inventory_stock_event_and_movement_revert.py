# Generated manually for warehouse audit + movement rollback flags.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0069_user_inventory_stock_filter_prefs"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockmovement",
            name="is_reverted",
            field=models.BooleanField(default=False, verbose_name="Откат выполнен"),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="reverted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Когда откатили"),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="reverted_by",
            field=models.CharField(blank=True, max_length=120, verbose_name="Кто откатил"),
        ),
        migrations.CreateModel(
            name="InventoryStockEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Когда")),
                ("actor_username", models.CharField(max_length=120, verbose_name="Кто")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("tool_edit", "Редактирование позиции"),
                            ("tool_delete", "Удаление позиции"),
                            ("rollback", "Откат движения"),
                            ("privilege_stock", "Право на склад"),
                        ],
                        max_length=24,
                        verbose_name="Тип",
                    ),
                ),
                ("summary", models.CharField(max_length=500, verbose_name="Кратко")),
                ("details", models.JSONField(blank=True, default=dict, verbose_name="Детали")),
                (
                    "stock_movement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inventory_events",
                        to="shifts.stockmovement",
                        verbose_name="Связанное движение",
                    ),
                ),
                (
                    "tool",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inventory_events",
                        to="shifts.toolitem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Событие склада",
                "verbose_name_plural": "События склада",
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
