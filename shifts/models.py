from django.core.validators import FileExtensionValidator
from django.db import models
import os


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
    ("radius", "Радиусная фреза"),
    ("ball", "Сферическая фреза"),
]

CENTER_DRILL_ANGLES = [
    ("60", "60"),
    ("90", "90"),
    ("120", "120"),
]

COUNTERSINK_TYPES = [
    ("hand", "Ручной"),
    ("machine", "Машинный"),
]

COUNTERSINK_ANGLES = [
    ("60", "60"),
    ("75", "75"),
    ("90", "90"),
    ("120", "120"),
]

COATING_TYPES = [
    ("none", "Без покрытия"),
    ("yellow", "Желтое"),
    ("brown", "Коричневое"),
    ("black", "Черное"),
    ("multicolor", "Цветное"),
    ("blue", "Синее"),
    ("other", "Другое"),
]

# Подсказки при наведении на маркер покрытия (склад и фильтры)
COATING_TYPE_TOOLTIPS = {
    "yellow": "обычно нитрид титана TiN или аналог, золотистый цвет",
    "brown": "обычно TiAlN, AlTiN и смежные составы для жары и трудных режимов",
    "black": "тёмное покрытие (часто углерод/алюминий/комплекс) для более тяжёлых режимов или чугуна",
    "none": "без покрытия как на этикетке, только материал пластины/стали режущей части",
    "multicolor": "многослойное покрытие, назначение смотреть по паспорту инструмента",
    "blue": "синий или сине-бирюзовый оттенок (например AlTiN-системы) для высоких нагрузок",
    "other": "нестандартное обозначение — см. техническое описание поставщика",
}

TOOL_MATERIAL_TYPES = [
    ("hrc45", "HRC 45"),
    ("hrc50", "HRC 50"),
    ("hrc55", "HRC 55"),
    ("hrc60", "HRC 60"),
    ("hrc65", "HRC 65"),
    ("hrc66", "HRC 66"),
    ("hrc70", "HRC 70"),
    ("hrc75", "HRC 75"),
    ("hrc80", "HRC 80"),
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
    ("PW", "Пластик (белый)"),
]

PURCHASE_STATUSES = [
    ("processing", "В обработке"),
    ("ordered", "Заказано"),
    ("delivered", "Доставлено"),
    ("stocked", "Реализовано на складе"),
]


class ToolItem(models.Model):
    category = models.CharField(
        max_length=20,
        choices=[
            ("end_mill", "Фрезы"),
            ("tap", "Резьбовой инструмент"),
            ("center_drill", "Центровки"),
            ("countersink", "Зенкера"),
            ("drill", "Сверла"),
        ],
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
    main_diameter_mm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Основной диаметр зажима, мм",
    )
    is_deleted = models.BooleanField(default=False, verbose_name="Помечен как удаленный")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Удален")
    deleted_by = models.CharField(max_length=120, blank=True, verbose_name="Удалил")
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


class CenterDrillSpec(models.Model):
    tool = models.OneToOneField(ToolItem, on_delete=models.CASCADE, related_name="center_drill_spec")
    diameter_mm = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Диаметр, мм", null=True, blank=True)
    overall_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Длина, мм", null=True, blank=True)
    angle_deg = models.CharField(max_length=8, choices=CENTER_DRILL_ANGLES, default="60", verbose_name="Угол, °")

    class Meta:
        verbose_name = "Параметры центровки"
        verbose_name_plural = "Параметры центровок"

    def __str__(self):
        return f"Центровка Ø{self.diameter_mm} / {self.angle_deg}°"


class CountersinkSpec(models.Model):
    tool = models.OneToOneField(ToolItem, on_delete=models.CASCADE, related_name="countersink_spec")
    countersink_type = models.CharField(max_length=16, choices=COUNTERSINK_TYPES, default="machine", verbose_name="Тип зенкера")
    diameter_mm = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Диаметр, мм", null=True, blank=True)
    angle_deg = models.CharField(max_length=8, choices=COUNTERSINK_ANGLES, default="90", verbose_name="Угол, °")
    overall_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Длина, мм", null=True, blank=True)
    flutes_count = models.PositiveSmallIntegerField(verbose_name="Количество кромок", null=True, blank=True)
    size_label = models.CharField(max_length=32, blank=True, verbose_name="Размер")

    class Meta:
        verbose_name = "Параметры зенкера"
        verbose_name_plural = "Параметры зенкеров"

    def __str__(self):
        return f"Зенкер {self.get_countersink_type_display()} Ø{self.diameter_mm} / {self.angle_deg}°"


class DrillSpec(models.Model):
    tool = models.OneToOneField(ToolItem, on_delete=models.CASCADE, related_name="drill_spec")
    diameter_mm = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Диаметр, мм", null=True, blank=True)
    overall_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Длина, мм", null=True, blank=True)
    cutting_length_mm = models.DecimalField(max_digits=7, decimal_places=2, verbose_name="Длина реж. части, мм", null=True, blank=True)
    angle_deg = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Угол, °", null=True, blank=True)

    class Meta:
        verbose_name = "Параметры сверла"
        verbose_name_plural = "Параметры сверл"

    def __str__(self):
        return f"Сверло Ø{self.diameter_mm} / {self.angle_deg}°"


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
    created_by_account = models.CharField(max_length=120, blank=True, verbose_name="Кто выполнил")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-movement_date", "-id")
        verbose_name = "Движение склада"
        verbose_name_plural = "Движения склада"

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} / {self.tool.name}"


class PurchaseRequest(models.Model):
    requested_item = models.CharField(max_length=255, verbose_name="Что закупить")
    store_link = models.URLField(blank=True, verbose_name="Ссылка на магазин")
    article = models.CharField(max_length=120, blank=True, verbose_name="Артикул")
    quantity = models.PositiveIntegerField(verbose_name="Количество")
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Цена за 1 шт",
    )
    status = models.CharField(
        max_length=20,
        choices=PURCHASE_STATUSES,
        default="processing",
        verbose_name="Статус",
    )
    request_comment = models.CharField(max_length=500, blank=True, verbose_name="Комментарий к заявке")
    status_comment = models.CharField(max_length=500, blank=True, verbose_name="Комментарий по статусу")
    requested_by = models.CharField(max_length=120, verbose_name="Кто запросил")
    status_updated_by = models.CharField(max_length=120, blank=True, verbose_name="Кто сменил статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Заявка на закупку"
        verbose_name_plural = "Заявки на закупку"

    def __str__(self):
        return f"{self.requested_item} x{self.quantity} ({self.get_status_display()})"

    @property
    def total_price(self):
        return self.unit_price * self.quantity


class EmployeeDefectRecord(models.Model):
    defect_date = models.DateField(verbose_name="Дата")
    responsible_name = models.CharField(max_length=120, verbose_name="Ответственный")
    employee_name = models.CharField(max_length=120, db_index=True, verbose_name="Сотрудник")
    department_name = models.CharField(max_length=200, blank=True, default="", db_index=True, verbose_name="Отдел")
    defect_quantity = models.PositiveIntegerField(verbose_name="Кол-во брака")
    good_quantity = models.PositiveIntegerField(default=0, verbose_name="Исправно")
    bad_quantity = models.PositiveIntegerField(default=0, verbose_name="Неисправно")
    potential_defect_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Потенциальный брак",
        help_text="Количество с потенциальным дефектом (учёт отдельно от подтверждённого брака).",
    )
    product_name = models.CharField(max_length=300, blank=True, default="", verbose_name="Изделие")
    defect_reason = models.CharField(max_length=500, verbose_name="Причина брака")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        ordering = ("-defect_date", "-id")
        verbose_name = "Запись учёта брака сотрудника"
        verbose_name_plural = "Учёт брака сотрудников"

    def __str__(self):
        return f"{self.defect_date} / {self.employee_name} / брак: {self.defect_quantity}"


EMPLOYEE_PAYROLL_SHIFT_HOURS = (
    (8, "8 часов"),
    (10, "10 часов"),
    (12, "12 часов"),
)


class EmployeePayrollProfile(models.Model):
    """Ставки и параметры смены для расчёта ЗП (привязка к коду сотрудника из Biota)."""

    emp_code = models.CharField(max_length=128, unique=True, db_index=True, verbose_name="Код сотрудника (Biota)")
    hourly_rate_day = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Ставка дневная, ₽/ч",
    )
    hourly_rate_night = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Ставка ночная, ₽/ч",
    )
    shift_hours = models.PositiveSmallIntegerField(
        choices=EMPLOYEE_PAYROLL_SHIFT_HOURS,
        default=8,
        verbose_name="Длительность смены, ч",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    updated_by = models.CharField(max_length=200, blank=True, default="", verbose_name="Кем обновлено")

    class Meta:
        verbose_name = "Параметры ЗП сотрудника"
        verbose_name_plural = "Параметры ЗП сотрудников"

    def __str__(self):
        return f"{self.emp_code} (смена {self.shift_hours} ч)"


class EmployeePayrollSettlement(models.Model):
    """Расчёт ЗП за месяц: табель по дням, премии, доли от начисления (поля — выплачиваемый % по линиям)."""

    emp_code = models.CharField(max_length=128, db_index=True, verbose_name="Код сотрудника")
    year = models.PositiveSmallIntegerField(verbose_name="Год")
    month = models.PositiveSmallIntegerField(verbose_name="Месяц")
    tab_by_day = models.JSONField(default=dict, blank=True, verbose_name="Часы по табелю по дням (ISO дата → часы)")
    bonus_percent = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name="Премия, % от начисления по табелю",
    )
    bonus_rub = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Премия, ₽",
    )
    penalty_quality_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        verbose_name="Качество, % от начисления по табелю (макс. 20)",
    )
    penalty_result_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        verbose_name="Результат, % от начисления по табелю (макс. 20)",
    )
    penalty_mode_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        verbose_name="Режим, % от начисления по табелю (макс. 10)",
    )
    penalty_rub = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Штраф, ₽",
    )
    advance_rub = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Аванс, ₽",
        help_text="Уже выплаченный или запланированный аванс за месяц — для сверки с расчётом «к выплате».",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    updated_by = models.CharField(max_length=200, blank=True, default="", verbose_name="Кем обновлено")

    class Meta:
        verbose_name = "Расчёт ЗП за месяц"
        verbose_name_plural = "Расчёты ЗП за месяц"
        constraints = [
            models.UniqueConstraint(
                fields=("emp_code", "year", "month"),
                name="uniq_employee_payroll_settlement_ym",
            )
        ]

    def __str__(self):
        return f"{self.emp_code} {self.year}-{self.month:02d}"


class EmployeePayrollMonthStatus(models.Model):
    """Отметки по сотруднику за календарный месяц (список ЗП и сверка с бухгалтерией)."""

    emp_code = models.CharField(max_length=128, db_index=True, verbose_name="Код сотрудника")
    year = models.PositiveSmallIntegerField(verbose_name="Год")
    month = models.PositiveSmallIntegerField(verbose_name="Месяц")
    advance_closed = models.BooleanField(
        default=False,
        verbose_name="Аванс учтён",
        help_text="Отметка: аванс за период учтён / сверен.",
    )
    payroll_closed = models.BooleanField(
        default=False,
        verbose_name="Расчёт ЗП завершён",
        help_text="Отметка: расчёт заработной платы за месяц по сотруднику закрыт.",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    updated_by = models.CharField(max_length=200, blank=True, default="", verbose_name="Кем обновлено")

    class Meta:
        verbose_name = "Статус ЗП сотрудника за месяц"
        verbose_name_plural = "Статусы ЗП по месяцам"
        constraints = [
            models.UniqueConstraint(
                fields=("emp_code", "year", "month"),
                name="uniq_employee_payroll_month_status_ym",
            )
        ]

    def __str__(self):
        return f"{self.emp_code} {self.year}-{self.month:02d}"


DEFECT_PAYROLL_ADJUST_KIND_CHOICES = [
    ("bonus_percent", "Премия, % от начисления по табелю"),
    ("bonus_rub", "Премия, ₽ (фикс)"),
    ("penalty_quality_pct", "Качество, % от начисления (0–20)"),
    ("penalty_result_pct", "Результат, % от начисления (0–20)"),
    ("penalty_mode_pct", "Режим, % от начисления (0–10)"),
    ("penalty_rub", "Штраф, ₽"),
]


class EmployeeDefectPayrollAdjustment(models.Model):
    """Добавка к полям расчёта ЗП за месяц, привязанная к конкретной записи учёта брака."""

    defect_record = models.ForeignKey(
        EmployeeDefectRecord,
        on_delete=models.CASCADE,
        related_name="payroll_adjustments",
        verbose_name="Запись брака",
    )
    adjust_kind = models.CharField(
        max_length=40,
        choices=DEFECT_PAYROLL_ADJUST_KIND_CHOICES,
        verbose_name="Поле в карточке ЗП",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Добавка",
        help_text="Суммируется с соответствующим полем в расчёте; для процентов — п.п.; допускается «−».",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    updated_by = models.CharField(max_length=200, blank=True, default="", verbose_name="Кем обновлено")

    class Meta:
        verbose_name = "Корректировка ЗП по записи брака"
        verbose_name_plural = "Корректировки ЗП по браку"
        constraints = [
            models.UniqueConstraint(
                fields=("defect_record", "adjust_kind"),
                name="uniq_defect_payroll_adj_kind",
            )
        ]

    def __str__(self):
        return f"#{self.defect_record_id} {self.adjust_kind} {self.amount}"


class Product(models.Model):
    """Карточка изделия: чертёж, 3D, наладка, программа."""

    name = models.CharField(max_length=300, verbose_name="Название")
    description = models.TextField(blank=True, default="", verbose_name="Описание")
    drawing_pdf = models.FileField(
        upload_to="products/drawings/",
        blank=True,
        verbose_name="Чертёж (PDF)",
        validators=[FileExtensionValidator(["pdf"])],
    )
    cad_model = models.FileField(
        upload_to="products/cad/",
        blank=True,
        verbose_name="3D-модель (STL, STP, STEP)",
        validators=[FileExtensionValidator(["stl", "stp", "step"])],
        help_text="Скачивание; для STP/STEP в окне — отдельный STL ниже.",
    )
    preview_stl = models.FileField(
        upload_to="products/preview_stl/",
        blank=True,
        verbose_name="STL для предпросмотра",
        validators=[FileExtensionValidator(["stl"])],
        help_text="Сетка для 3D в карточке; для STP/STEP — экспорт в STL сюда.",
    )
    list_preview_image = models.FileField(
        upload_to="products/list_previews/",
        blank=True,
        verbose_name="Превью для списка изделий (PNG)",
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp"])],
        help_text="Сохраняется из 3D-окна кнопкой «Сохранить превью».",
    )
    setup_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Наладка (текст)",
        help_text="Заготовка, привязка, инструмент, прочее.",
    )
    program_file = models.FileField(
        upload_to="products/programs/",
        blank=True,
        verbose_name="Программа (G/M, любой файл)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("-updated_at", "-id")
        verbose_name = "Изделие"
        verbose_name_plural = "Изделия"

    def __str__(self):
        return self.name

    def cad_filename_endswith_stl(self) -> bool:
        n = (self.cad_model.name or "").lower() if self.cad_model else ""
        return n.endswith(".stl")

    @property
    def program_filename(self) -> str:
        if not self.program_file:
            return ""
        return os.path.basename(self.program_file.name or "")

    @property
    def preview_stl_list_label(self) -> str:
        if self.preview_stl:
            return "отдельный"
        if self.cad_filename_endswith_stl():
            return "из основного"
        return "—"


class ProductSetup(models.Model):
    """Установка изделия: наладка и программа."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="setups",
    )
    name = models.CharField(max_length=180, verbose_name="Название установки")
    binding_x = models.CharField(max_length=64, blank=True, default="", verbose_name="Привязка X")
    binding_y = models.CharField(max_length=64, blank=True, default="", verbose_name="Привязка Y")
    binding_z = models.CharField(max_length=64, blank=True, default="", verbose_name="Привязка Z")
    gcode_system = models.CharField(max_length=3, blank=True, default="G54", verbose_name="Система координат G")
    binding_x_photo = models.FileField(
        upload_to="products/setup_bindings/",
        blank=True,
        verbose_name="Фото привязки X",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
    )
    binding_y_photo = models.FileField(
        upload_to="products/setup_bindings/",
        blank=True,
        verbose_name="Фото привязки Y",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
    )
    binding_z_photo = models.FileField(
        upload_to="products/setup_bindings/",
        blank=True,
        verbose_name="Фото привязки Z",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
    )
    workpiece_photo = models.FileField(
        upload_to="products/setup_bindings/",
        blank=True,
        verbose_name="Фото заготовки",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "gif"])],
    )
    workpiece = models.CharField(max_length=220, blank=True, default="", verbose_name="Заготовка")
    material = models.CharField(max_length=180, blank=True, default="", verbose_name="Материал")
    size = models.CharField(max_length=180, blank=True, default="", verbose_name="Размер")
    tool_pdf = models.FileField(
        upload_to="products/setup_tools/",
        blank=True,
        verbose_name="Инструмент (PDF/HTML)",
        validators=[FileExtensionValidator(["pdf", "html", "htm"])],
    )
    setup_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Наладка (текст)",
    )
    program_file = models.FileField(
        upload_to="products/programs/",
        blank=True,
        verbose_name="Программа (G/M, любой файл)",
    )
    preview_stl = models.FileField(
        upload_to="products/setup_preview_stl/",
        blank=True,
        verbose_name="STL предпросмотра установки",
        validators=[FileExtensionValidator(["stl"])],
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Установка изделия"
        verbose_name_plural = "Установки изделий"

    def __str__(self) -> str:
        return f"{self.product_id} / {self.name}"

    @property
    def program_filename(self) -> str:
        if not self.program_file:
            return ""
        return os.path.basename(self.program_file.name or "")


class ProductSetupProgramFile(models.Model):
    """Файл программы (G/M и др.) в составе установки; может быть несколько штук."""

    setup = models.ForeignKey(
        ProductSetup,
        on_delete=models.CASCADE,
        related_name="program_files",
        verbose_name="Установка",
    )
    file = models.FileField(
        upload_to="products/setup_programs/",
        verbose_name="Файл программы",
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Файл программы установки"
        verbose_name_plural = "Файлы программ установки"

    def __str__(self) -> str:
        return self.display_name or f"#{self.pk}"

    @property
    def display_name(self) -> str:
        if not self.file:
            return ""
        return os.path.basename(self.file.name or "")


class ProductSetupToolRow(models.Model):
    """
    Строка таблицы инструмента внутри установки.
    Данные редактируются на странице редактирования установки и отображаются в карточке продукта.
    """

    setup = models.ForeignKey(
        ProductSetup,
        on_delete=models.CASCADE,
        related_name="tools",
        verbose_name="Установка",
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    tool_number = models.CharField(max_length=20, blank=True, default="", verbose_name="Номер")
    kor_n = models.CharField(max_length=20, blank=True, default="", verbose_name="Кор. н")
    kor_d = models.CharField(max_length=20, blank=True, default="", verbose_name="Кор. д")

    tool_type = models.CharField(max_length=80, blank=True, default="", verbose_name="Тип")
    tap_hole_type = models.CharField(max_length=20, blank=True, default="", verbose_name="Метчик: тип отверстия")
    name = models.CharField(max_length=180, blank=True, default="", verbose_name="Наименование")

    diameter = models.CharField(max_length=40, blank=True, default="", verbose_name="Диаметр")
    overhang = models.CharField(max_length=40, blank=True, default="", verbose_name="Вылет")

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Строка инструмента"
        verbose_name_plural = "Строки инструмента"

    def __str__(self) -> str:
        return f"{self.tool_number or self.name}".strip() or f"#{self.pk}"


class ProductSetupPhoto(models.Model):
    """Фото в блоке «Наладка»."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="setup_photos",
    )
    setup = models.ForeignKey(
        ProductSetup,
        on_delete=models.CASCADE,
        related_name="photos",
        null=True,
        blank=True,
        verbose_name="Установка",
    )
    image = models.FileField(
        upload_to="products/setup/",
        verbose_name="Фото",
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    caption = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Подпись",
    )

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Фото наладки (изделие)"
        verbose_name_plural = "Фото наладки (изделие)"

    def __str__(self) -> str:
        return f"{self.product_id} #{self.pk}"
