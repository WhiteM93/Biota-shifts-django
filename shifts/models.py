from django.db import models


THREAD_STANDARDS = [
    ("metric", "Метрическая (M)"),
    ("unc", "UNC"),
    ("unf", "UNF"),
    ("unef", "UNEF"),
    ("bsp", "BSP"),
    ("npt", "NPT"),
    ("other", "Другое"),
]

TAP_HOLE_TYPES = [
    ("through", "Сквозное"),
    ("blind", "Глухое"),
    ("any", "Универсальное"),
]

TAP_TOOL_TYPES = [
    ("cutting", "Режущий метчик"),
    ("forming", "Метчик-раскатник"),
    ("thread_mill", "Резьбофреза"),
]

END_MILL_TYPES = [
    ("end", "Концевая фреза"),
    ("roughing", "Обдирочная фреза"),
    ("t_slot", "Т-образная фреза"),
]

COATING_TYPES = [
    ("yellow", "Желтое"),
    ("brown", "Коричневое"),
    ("black", "Черное"),
    ("none", "Без покрытия"),
    ("multicolor", "Цветное"),
    ("blue", "Синее"),
    ("other", "Другое"),
]

TOOL_MATERIAL_TYPES = [
    ("hss", "HSS"),
    ("hss_co", "HSS-Co"),
    ("carbide", "Твердосплав"),
]

WORK_MATERIAL_TYPES = [
    ("P", "P (синий) — углеродистые и легированные стали"),
    ("M", "M (жёлтый) — нержавеющие стали"),
    ("K", "K (красный) — чугун"),
    ("N", "N (зелёный) — цветные металлы"),
    ("S", "S (коричневый) — жаропрочные сплавы и титан"),
    ("H", "H (серый) — закалённые стали (45–65 HRC)"),
]


class ToolItem(models.Model):
    category = models.CharField(
        max_length=20,
        choices=[("end_mill", "Фрезы"), ("tap", "Резьбовой инструмент")],
        verbose_name="Категория",
    )
    name = models.CharField(max_length=180, verbose_name="Наименование")
    tool_material = models.CharField(
        max_length=80,
        blank=True,
        choices=TOOL_MATERIAL_TYPES,
        verbose_name="Материал инструмента",
    )
    coating_type = models.CharField(
        max_length=20,
        choices=COATING_TYPES,
        default="none",
        verbose_name="Материал покрытия",
    )
    work_material = models.CharField(
        max_length=120,
        blank=True,
        choices=WORK_MATERIAL_TYPES,
        verbose_name="Материал обработки",
    )
    quantity = models.PositiveIntegerField(default=0, verbose_name="Количество")
    notes = models.CharField(max_length=300, blank=True, verbose_name="Примечание")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("category", "name")
        verbose_name = "Инструмент"
        verbose_name_plural = "Инструмент"

    def __str__(self):
        return f"{self.get_category_display()} / {self.name}"


class EndMillSpec(models.Model):
    tool = models.OneToOneField(ToolItem, on_delete=models.CASCADE, related_name="end_mill_spec")
    mill_type = models.CharField(max_length=20, choices=END_MILL_TYPES, default="end", verbose_name="Тип фрезы")
    diameter_mm = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Диаметр, мм", null=True, blank=True)
    corner_radius_mm = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Радиус, мм", null=True, blank=True)
    overall_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Общая длина, мм", null=True, blank=True)
    cutting_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Длина реж. части, мм", null=True, blank=True)
    flutes_count = models.PositiveSmallIntegerField(verbose_name="Количество кромок", null=True, blank=True)

    class Meta:
        verbose_name = "Параметры фрезы"
        verbose_name_plural = "Параметры фрез"

    def __str__(self):
        return f"{self.get_mill_type_display()} {self.diameter_mm} мм ({self.flutes_count} кромок)"


class TapSpec(models.Model):
    tool = models.OneToOneField(ToolItem, on_delete=models.CASCADE, related_name="tap_spec")
    thread_standard = models.CharField(max_length=20, choices=THREAD_STANDARDS, default="metric")
    size_label = models.CharField(max_length=32, verbose_name="Размер (M2, 1/4-20 и т.д.)")
    pitch_mm = models.DecimalField(max_digits=6, decimal_places=3, verbose_name="Шаг резьбы, мм", null=True, blank=True)
    tpi = models.PositiveSmallIntegerField(verbose_name="TPI (для дюймовых)", null=True, blank=True)
    hole_type = models.CharField(max_length=16, choices=TAP_HOLE_TYPES, default="any")
    tap_type = models.CharField(max_length=20, choices=TAP_TOOL_TYPES, default="cutting")
    overall_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Общая длина, мм", null=True, blank=True)
    cutting_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Длина реж. части, мм", null=True, blank=True)

    class Meta:
        verbose_name = "Параметры метчика"
        verbose_name_plural = "Параметры метчиков"

    def __str__(self):
        return f"{self.size_label} ({self.get_thread_standard_display()})"


class StockMovement(models.Model):
    movement_type = models.CharField(
        max_length=16,
        choices=[("issue", "Выдача"), ("restock", "Пополнение"), ("writeoff", "Списание")],
        verbose_name="Тип операции",
    )
    tool = models.ForeignKey(ToolItem, on_delete=models.PROTECT, related_name="movements")
    parent_issue = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issue_outcomes",
        verbose_name="Исходная выдача",
    )
    quantity = models.PositiveIntegerField(verbose_name="Количество")
    employee_name = models.CharField(max_length=120, blank=True, verbose_name="Сотрудник")
    movement_date = models.DateField(verbose_name="Дата")
    comment = models.CharField(max_length=300, blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-movement_date", "-id")
        verbose_name = "Движение склада"
        verbose_name_plural = "Движения склада"

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} / {self.tool.name}"
