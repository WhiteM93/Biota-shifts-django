"""Поля связанной позиции PlannedProduct при редактировании из карточки наладки."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from .models import (
    PLANNED_PRODUCT_WORKPIECE_TYPE_CHOICES,
    PLANNED_PRODUCT_WORKPIECE_TYPE_VALUES,
    PlannedProduct,
    Product,
    ProductSetup,
)
from .plan_naladki_bridge import ensure_plan_piece_for_naladki_product, finalize_plan_piece_naladki_link


def normalize_plan_product_type(raw: str | None) -> str:
    """Пустая строка остаётся пустой (не подставляем made по умолчанию)."""
    t = (raw or "").strip().lower()
    return t if t in ("made", "assembly", "pki") else ""


def flags_from_plan_product_type(t: str) -> tuple[bool, bool]:
    if t == "assembly":
        return True, False
    if t == "pki":
        return False, True
    return False, False


def parse_laser_sheet_thickness_mm(raw: str | None) -> tuple[Decimal | None, str | None]:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        return None, "Укажите толщину листа, мм."
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None, "Толщина листа: введите число (мм)."
    if d <= 0:
        return None, "Толщина листа должна быть больше нуля."
    if d > Decimal("500"):
        return None, "Слишком большая толщина листа."
    return d, None


def laser_material_marking_suggestions() -> list[str]:
    """Обратная совместимость — см. plan_material_suggestions()."""
    return plan_material_suggestions()


def plan_material_suggestions() -> list[str]:
    """Уникальные материалы из плана (лазер) и наладок (setup.material)."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        s = (raw or "").strip()
        if not s:
            return
        key = s.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(s)

    for raw in (
        PlannedProduct.objects.exclude(laser_material_marking="")
        .order_by("id")
        .values_list("laser_material_marking", flat=True)
    ):
        add(str(raw))
    for raw in (
        ProductSetup.objects.exclude(material="")
        .order_by("id")
        .values_list("material", flat=True)
    ):
        add(str(raw))
    return out


def _plan_material_value(product: Product | None, plan_piece: PlannedProduct | None) -> str:
    if plan_piece and (plan_piece.workpiece_type or "").strip() == "laser":
        return (plan_piece.laser_material_marking or "").strip()
    return _first_setup_material(product)


def _plan_material_from_post(post: Any) -> str:
    for key in ("plan_material", "made_material", "laser_material_marking"):
        val = (post.get(key) or "").strip()
        if val:
            return val[:180]
    return ""


def validate_product_plan_post(post: Any) -> str | None:
    """
    Валидация формы планирования изделия с поддержкой каскадной логики.

    Проверяет обязательные поля в зависимости от выбранного пути каскада:
    1. Деталь → Лазерная резка: требуется толщина листа и материал
    2. Деталь → Ленточная пила: требуется материал, размер и тип заготовки
    3. Деталь → ПКИ (вид): требуется материал и размер
    4. Сборка: требуется материал и размер
    5. ПКИ (тип): требуется материал и размер

    Args:
        post: POST данные или QueryDict

    Returns:
        Строка ошибки для messages.error или None если валидация пройдена
    """
    # Получить тип изделия (product_type или старый план_product_type)
    product_type = (post.get("product_type") or post.get("plan_product_type") or "").strip()
    product_type = normalize_plan_product_type(product_type)

    if not product_type:
        return "Выберите тип изделия (Изделие, Сборка или ПКИ)."

    # Путь 1: Изделие
    if product_type == "made":
        workpiece_type = (post.get("workpiece_type") or "").strip()

        if not workpiece_type:
            return "Для изделия выберите вид заготовки."

        if workpiece_type not in PLANNED_PRODUCT_WORKPIECE_TYPE_VALUES:
            return "Неизвестный вид заготовки. Выберите: ленточная пила, лазерная резка или ПКИ."

        # Путь 1a: Лазерная резка
        if workpiece_type == "laser":
            # Проверить толщину листа
            laser_thickness = (post.get("laser_thickness") or post.get("laser_sheet_thickness_mm") or "").strip()
            if not laser_thickness:
                return "Укажите толщину листа (мм)."

            try:
                thickness_value = float(laser_thickness)
                if thickness_value <= 0:
                    return "Толщина листа должна быть больше 0."
                if thickness_value >= 500:
                    return "Толщина листа должна быть меньше 500 мм."
            except (ValueError, TypeError):
                return "Толщина листа должна быть числовым значением."

            # Проверить материал
            material = (post.get("material") or post.get("plan_material") or "").strip()
            if not material:
                return "Укажите материал для лазерной резки."

        # Путь 1b: Ленточная пила (preparatory)
        elif workpiece_type == "preparatory":
            # Проверить материал
            material = (post.get("material") or post.get("plan_material") or "").strip()
            if not material:
                return "Укажите материал для ленточной пилы."

            # Проверить размер заготовки
            workpiece_size = (post.get("workpiece_size") or "").strip()
            if not workpiece_size:
                return "Укажите размер заготовки."

            # Проверить тип заготовки
            workpiece_type_enum = (post.get("workpiece_type_enum") or "").strip()
            if not workpiece_type_enum:
                return "Выберите тип заготовки."
            if workpiece_type_enum not in ("plate", "circle", "rod"):
                return "Неизвестный тип заготовки."

        # Путь 1c: ПКИ (вид заготовки)
        elif workpiece_type == "pki":
            # Проверить материал
            material = (post.get("material") or post.get("plan_material") or "").strip()
            if not material:
                return "Укажите материал для ПКИ заготовки."

            # Проверить размер заготовки
            workpiece_size = (post.get("workpiece_size") or "").strip()
            if not workpiece_size:
                return "Укажите размер заготовки."

    # Путь 2: Сборка (размер опционален)
    elif product_type == "assembly":
        material = (post.get("material") or post.get("plan_material") or "").strip()
        if not material:
            return "Укажите материал для сборки."

    # Путь 3: ПКИ (тип изделия)
    elif product_type == "pki":
        # Проверить материал
        material = (post.get("material") or post.get("plan_material") or "").strip()
        if not material:
            return "Укажите материал для ПКИ."

        # Проверить размер заготовки
        workpiece_size = (post.get("workpiece_size") or "").strip()
        if not workpiece_size:
            return "Укажите размер заготовки для ПКИ."

    # Все проверки пройдены
    return None


def _first_setup_material(product: Product | None) -> str:
    if not product or not getattr(product, "pk", None):
        return ""
    setup = (
        ProductSetup.objects.filter(product_id=product.pk)
        .order_by("sort_order", "id")
        .first()
    )
    return (setup.material or "").strip() if setup else ""


def plan_piece_for_naladki_card(product: Product) -> PlannedProduct | None:
    pp = PlannedProduct.objects.filter(naladki_product_id=product.pk).first()
    if pp:
        return pp
    nm = (product.name or "").strip()
    if not nm:
        return None
    return PlannedProduct.objects.filter(name__iexact=nm).order_by("-updated_at", "-id").first()


def plan_inline_state_payload(product: Product | None) -> dict[str, str]:
    """
    Состояние полей плана после сохранения (для инлайна / синхронизации форм).

    Используется для обновления форм на клиенте после сохранения данных.
    Включает все поля каскадной формы.
    """
    ctx = plan_form_context(product)
    return {
        "product_type": ctx.get("plan_product_type") or "made",
        "plan_product_type": ctx.get("plan_product_type") or "made",
        "workpiece_type": ctx.get("plan_workpiece_type_value") or "",
        "laser_thickness": ctx.get("plan_laser_sheet_thickness_value") or "",
        "laser_sheet_thickness_mm": ctx.get("plan_laser_sheet_thickness_value") or "",
        "material": ctx.get("plan_material_value") or "",
        "plan_material": ctx.get("plan_material_value") or "",
        "laser_material_marking": ctx.get("plan_laser_material_marking_value") or "",
        "workpiece_size": ctx.get("plan_workpiece_size_value") or "",
        "workpiece_type_enum": ctx.get("plan_workpiece_type_enum_value") or "",
    }


def plan_card_summary(pp: PlannedProduct | None, product: Product | None = None) -> dict[str, str]:
    """Короткие строки для карточки наладки (тип изделия / заготовка / материал)."""
    summary = {
        "product_kind_line": "—",
        "type_line": "—",
        "workpiece_line": "—",
        "material_line": "—",
    }
    if not pp:
        return summary
    if pp.is_assembly:
        summary["product_kind_line"] = "Сборка"
        summary["type_line"] = "Сборка"
        summary["workpiece_line"] = "—"
        summary["material_line"] = "—"
        return summary
    if pp.is_purchased:
        summary["product_kind_line"] = "ПКИ"
        summary["type_line"] = "ПКИ"
        summary["workpiece_line"] = "—"
        summary["material_line"] = "—"
        return summary
    summary["product_kind_line"] = "Деталь"
    if pp.workpiece_type == "laser":
        summary["type_line"] = "Лазер"
        thick = ""
        if pp.laser_sheet_thickness_mm is not None:
            d = pp.laser_sheet_thickness_mm
            thick = format(d, "f").rstrip("0").rstrip(".")
        summary["workpiece_line"] = f"Лазерный · лист {thick} мм" if thick else "Лазерный"
        summary["material_line"] = (pp.laser_material_marking or "").strip() or "—"
    elif pp.workpiece_type == "preparatory":
        summary["type_line"] = "Заготовительный"
        summary["workpiece_line"] = "Заготовительный"
        summary["material_line"] = "—"
    elif pp.workpiece_type == "pki":
        summary["type_line"] = "ПКИ (заготовка)"
        summary["workpiece_line"] = "ПКИ"
        summary["material_line"] = "—"
    else:
        summary["type_line"] = "Изделие"
        summary["workpiece_line"] = pp.get_workpiece_type_display() if pp.workpiece_type else "—"
        summary["material_line"] = "—"
    if product and not pp.is_assembly and not pp.is_purchased:
        wpv = (pp.workpiece_type or "").strip()
        if wpv != "laser":
            mat = _first_setup_material(product)
            summary["material_line"] = mat or "—"
    return summary


def plan_form_context(product: Product | None) -> dict[str, Any]:
    """
    Контекст шаблона для формы планирования изделия.

    Возвращает все данные о плане изделия для отображения и редактирования:
    - Тип изделия (Изделие, Сборка, ПКИ)
    - Вид заготовки (Ленточная пила, Лазерная резка, ПКИ)
    - Параметры в зависимости от пути каскада
    """
    plan_product_type = "made"
    workpiece_type_value = ""
    laser_sheet_thickness_value = ""
    laser_material_marking_value = ""
    workpiece_size_value = ""
    workpiece_type_enum_value = ""
    plan_piece = None

    if product is not None and getattr(product, "pk", None):
        plan_piece = plan_piece_for_naladki_card(product)
        if plan_piece:
            if plan_piece.is_assembly:
                plan_product_type = "assembly"
            elif plan_piece.is_purchased:
                plan_product_type = "pki"
            else:
                plan_product_type = "made"

            workpiece_type_value = (plan_piece.workpiece_type or "").strip()

            if plan_piece.laser_sheet_thickness_mm is not None:
                d = plan_piece.laser_sheet_thickness_mm
                s = format(d, "f").rstrip("0").rstrip(".")
                laser_sheet_thickness_value = s if s else "0"

            laser_material_marking_value = (plan_piece.laser_material_marking or "").strip()
            workpiece_size_value = (plan_piece.workpiece_size or "").strip()
            workpiece_type_enum_value = (plan_piece.workpiece_type_enum or "").strip()

    plan_made_material_value = _plan_material_value(product, plan_piece)
    card = plan_card_summary(plan_piece, product)

    return {
        "plan_piece": plan_piece,
        "plan_product_type": plan_product_type,
        "plan_workpiece_type_value": workpiece_type_value,
        "plan_workpiece_type_choices": PLANNED_PRODUCT_WORKPIECE_TYPE_CHOICES,
        "plan_laser_sheet_thickness_value": laser_sheet_thickness_value,
        "plan_laser_material_marking_value": laser_material_marking_value,
        "plan_made_material_value": plan_made_material_value,
        "plan_material_value": plan_made_material_value,
        "plan_workpiece_size_value": workpiece_size_value,
        "plan_workpiece_type_enum_value": workpiece_type_enum_value,
        "plan_laser_material_marking_suggestions": plan_material_suggestions(),
        "plan_material_suggestions": plan_material_suggestions(),
        "plan_display_type_line": card["type_line"],
        "plan_display_product_kind_line": card["product_kind_line"],
        "plan_display_workpiece_line": card["workpiece_line"],
        "plan_display_material_line": card["material_line"],
    }


def apply_product_plan_post(product: Product, post: Any) -> str | None:
    """Обновить PlannedProduct по полям формы наладки. Возвращает текст ошибки или None."""
    err = validate_product_plan_post(post)
    if err:
        return err
    if not product.pk:
        return "Сначала сохраните изделие."

    with transaction.atomic():
        nm_product = (product.name or "").strip()
        nm_plan = nm_product[:400] if nm_product else ""

        pp = PlannedProduct.objects.select_for_update().filter(naladki_product_id=product.pk).first()
        if not pp and nm_plan:
            pp = (
                PlannedProduct.objects.select_for_update()
                .filter(name__iexact=nm_plan)
                .order_by("-updated_at", "-id")
                .first()
            )
        if not pp:
            ensure_plan_piece_for_naladki_product(product.pk)
            pp = (
                PlannedProduct.objects.select_for_update()
                .filter(naladki_product_id=product.pk)
                .first()
            )
        if not pp:
            return "Не удалось связать карточку наладки с планом. Обновите страницу."

        t = normalize_plan_product_type(post.get("product_type") or post.get("plan_product_type") or "")
        if not t:
            return "Выберите тип изделия (Деталь, Сборка или ПКИ)."
        is_asm, is_pki = flags_from_plan_product_type(t)

        pp.name = nm_plan or pp.name
        pp.is_assembly = is_asm
        pp.is_purchased = is_pki

        # Получить материал (общий для всех путей, если нужен)
        plan_mat = (post.get("material") or post.get("plan_material") or "").strip()

        if t == "made":
            wp = (post.get("workpiece_type") or "").strip()
            pp.workpiece_type = wp

            if wp == "laser":
                # Путь: Деталь → Лазерная резка
                thick, _ = parse_laser_sheet_thickness_mm(
                    post.get("laser_thickness") or post.get("laser_sheet_thickness_mm")
                )
                if thick is None:
                    return "Укажите толщину листа, мм."
                pp.laser_sheet_thickness_mm = thick
                pp.laser_material_marking = plan_mat
                pp.workpiece_size = ""
                pp.workpiece_type_enum = ""

            elif wp == "preparatory":
                # Путь: Деталь → Ленточная пила
                pp.laser_sheet_thickness_mm = None
                pp.laser_material_marking = ""
                pp.workpiece_size = (post.get("workpiece_size") or "").strip()
                pp.workpiece_type_enum = (post.get("workpiece_type_enum") or "").strip()

            elif wp == "pki":
                # Путь: Деталь → ПКИ (вид заготовки)
                pp.laser_sheet_thickness_mm = None
                pp.laser_material_marking = ""
                pp.workpiece_size = (post.get("workpiece_size") or "").strip()
                pp.workpiece_type_enum = ""

            else:
                # Неизвестный вид заготовки
                pp.laser_sheet_thickness_mm = None
                pp.laser_material_marking = ""
                pp.workpiece_size = ""
                pp.workpiece_type_enum = ""

        elif t == "assembly":
            # Путь: Сборка
            pp.workpiece_type = ""
            pp.laser_sheet_thickness_mm = None
            pp.laser_material_marking = ""
            pp.workpiece_size = (post.get("workpiece_size") or "").strip()
            pp.workpiece_type_enum = ""

        elif t == "pki":
            # Путь: ПКИ (тип изделия)
            pp.workpiece_type = ""
            pp.laser_sheet_thickness_mm = None
            pp.laser_material_marking = ""
            pp.workpiece_size = (post.get("workpiece_size") or "").strip()
            pp.workpiece_type_enum = ""

        else:
            # Нет типа изделия
            pp.workpiece_type = ""
            pp.laser_sheet_thickness_mm = None
            pp.laser_material_marking = ""
            pp.workpiece_size = ""
            pp.workpiece_type_enum = ""
            plan_mat = ""

        # Сохранить все поля PlannedProduct
        pp.save(
            update_fields=[
                "name",
                "is_assembly",
                "is_purchased",
                "workpiece_type",
                "laser_sheet_thickness_mm",
                "laser_material_marking",
                "workpiece_size",
                "workpiece_type_enum",
                "updated_at",
            ]
        )

        # Материал для ленточной пилы / сборки / ПКИ хранится в первой установке
        if plan_mat and t in ("made", "assembly", "pki"):
            setup0 = (
                ProductSetup.objects.filter(product_id=product.pk)
                .order_by("sort_order", "id")
                .first()
            )
            if setup0 and setup0.material != plan_mat:
                setup0.material = plan_mat
                setup0.save(update_fields=["material", "updated_at"])
        finalize_plan_piece_naladki_link(pp.pk)
    return None
