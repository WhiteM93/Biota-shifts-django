from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shifts", "0108_inspection_value_marks"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductSetupPieceNorm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "tsht_norm",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=12,
                        verbose_name="Тшт (норма, 1.0 = 60 мин)",
                    ),
                ),
                (
                    "tsht_min",
                    models.DecimalField(
                        decimal_places=3,
                        max_digits=12,
                        verbose_name="Тшт, мин/шт",
                    ),
                ),
                (
                    "previous_tsht_norm",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=12,
                        null=True,
                        verbose_name="Предыдущая Тшт",
                    ),
                ),
                ("comment", models.CharField(blank=True, default="", max_length=500, verbose_name="Комментарий")),
                ("author", models.CharField(blank=True, default="", max_length=120, verbose_name="Автор")),
                (
                    "t_auto",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        max_digits=12,
                        null=True,
                        verbose_name="Тавтом, мин",
                    ),
                ),
                ("k_parts", models.PositiveIntegerField(default=1, verbose_name="k деталей за цикл")),
                (
                    "a_pct",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=6,
                        null=True,
                        verbose_name="a, %",
                    ),
                ),
                (
                    "t_ust",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        max_digits=12,
                        null=True,
                        verbose_name="Туст, мин",
                    ),
                ),
                (
                    "t_izm",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        max_digits=12,
                        null=True,
                        verbose_name="Тизм, мин",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Сохранено")),
                (
                    "setup",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="piece_norms",
                        to="shifts.productsetup",
                        verbose_name="Установка",
                    ),
                ),
            ],
            options={
                "verbose_name": "Норма Тшт установки",
                "verbose_name_plural": "Нормы Тшт установок",
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
