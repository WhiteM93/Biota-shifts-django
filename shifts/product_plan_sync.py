"""Параметры изделия на карточке наладки (Product + первая установка). Без раздела «План»."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from .models import (
    PLANNED_PRODUCT_WORKPIECE_TYPE_CHOICES,
    PLANNED_PRODUCT_WORKPIECE_TYPE_VALUES,
    Product,
    ProductSetup,
)


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


def plan_material_suggestions() -> list[str]:
    """Уникальные материалы из карточек изделий и установок."""
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

    for raw in Product.objects.exclude(card_material="").order_by("id").values_list("card_material", flat=True):
        add(str(raw))
    for raw in ProductSetup.objects.exclude(material="").order_by("id").values_list("material", flat=True):
        add(str(raw))
    return out


def laser_material_marking_suggestions() -> list[str]:
    return plan_material_suggestions()


def _card_material_display(product: Product | None) -> str:
    if not product:
        return ""
    mat = (product.card_material or "").strip()
    if mat:
        return mat
    return _first_setup_material(product)


def _first_setup_material(product: Product | None) -> str:
    if not product or not getattr(product, "pk", None):
        return ""
    setup = (
        ProductSetup.objects.filter(product_id=product.pk)
        .order_by("sort_order", "id")
        .first()
    )
    return (setup.material or "").strip() if setup else ""


def _laser_thickness_str(product: Product | None) -> str:
    if not product or product.card_laser_thickness_mm is None:
        return ""
    d = product.card_laser_thickness_mm
    s = format(d, "f").rstrip("0").rstrip(".")
    return s if s else "0"


def validate_product_plan_post(post: Any) -> str | None:
    product_type = normalize_plan_product_type(
        post.get("product_type") or post.get("plan_product_type")
    )
    if not product_type:
        return "Выберите тип изделия (Изделие, Сборка или ПКИ)."

    if product_type == "made":
        workpiece_type = (post.get("workpiece_type") or "").strip()
        if not workpiece_type:
            return "Для изделия выберите вид заготовки."
        if workpiece_type not in PLANNED_PRODUCT_WORKPIECE_TYPE_VALUES:
            return "Неизвестный вид заготовки. Выберите: ленточная пила, лазерная резка или ПКИ."

        if workpiece_type == "laser":
            laser_thickness = (post.get("laser_thickness") or post.get("laser_sheet_thickness_mm") or "").strip()
            if not laser_thickness:
                return "Укажите толщину листа (мм)."
            try:
                thickness_value = float(laser_thickness.replace(",", "."))
                if thickness_value <= 0:
                    return "Толщина листа должна быть больше 0."
                if thickness_value >= 500:
                    return "Толщина листа должна быть меньше 500 мм."
            except (ValueError, TypeError):
                return "Толщина листа должна быть числовым значением."
            material = (post.get("material") or post.get("plan_material") or "").strip()
            if not material:
                return "Укажите материал для лазерной резки."

        elif workpiece_type == "preparatory":
            material = (post.get("material") or post.get("plan_material") or "").strip()
            if not material:
                return "Укажите материал для ленточной пилы."
            if not (post.get("workpiece_size") or "").strip():
                return "Укажите размер заготовки."
            if not (post.get("workpiece_type_enum") or "").strip():
                return "Выберите тип заготовки."
            wte = (post.get("workpiece_type_enum") or "").strip()
            if wte not in ("plate", "circle", "rod"):
                return "Неизвестный тип заготовки."

        elif workpiece_type == "pki":
            material = (post.get("material") or post.get("plan_material") or "").strip()
            if not material:
                return "Укажите материал для ПКИ заготовки."
            if not (post.get("workpiece_size") or "").strip():
                return "Укажите размер заготовки."

    elif product_type == "assembly":
        material = (post.get("material") or post.get("plan_material") or "").strip()
        if not material:
            return "Укажите материал для сборки."

    elif product_type == "pki":
        material = (post.get("material") or post.get("plan_material") or "").strip()
        if not material:
            return "Укажите материал для ПКИ."
        if not (post.get("workpiece_size") or "").strip():
            return "Укажите размер заготовки для ПКИ."

    return None


def plan_inline_state_payload(product: Product | None) -> dict[str, str]:
    ctx = plan_form_context(product)
    pt = ctx.get("plan_product_type") or ""
    return {
        "product_type": pt,
        "plan_product_type": pt,
        "workpiece_type": ctx.get("plan_workpiece_type_value") or "",
        "laser_thickness": ctx.get("plan_laser_sheet_thickness_value") or "",
        "laser_sheet_thickness_mm": ctx.get("plan_laser_sheet_thickness_value") or "",
        "material": ctx.get("plan_material_value") or "",
        "plan_material": ctx.get("plan_material_value") or "",
        "laser_material_marking": ctx.get("plan_material_value") or "",
        "workpiece_size": ctx.get("plan_workpiece_size_value") or "",
        "workpiece_type_enum": ctx.get("plan_workpiece_type_enum_value") or "",
    }


def plan_card_summary(product: Product | None = None, _legacy=None) -> dict[str, str]:
    """Короткие строки для блока параметров (тип / заготовка / материал)."""
    summary = {
        "product_kind_line": "—",
        "type_line": "—",
        "workpiece_line": "—",
        "material_line": "—",
    }
    if not product:
        return summary

    t = normalize_plan_product_type(product.card_product_type)
    mat = _card_material_display(product) or "—"

    if t == "assembly":
        summary["product_kind_line"] = "Сборка"
        summary["type_line"] = "Сборка"
        summary["material_line"] = mat
        return summary
    if t == "pki":
        summary["product_kind_line"] = "ПКИ"
        summary["type_line"] = "ПКИ"
        summary["workpiece_line"] = (product.card_workpiece_size or "").strip() or "—"
        summary["material_line"] = mat
        return summary
    if not t:
        summary["material_line"] = mat if mat != "—" else "—"
        return summary

    summary["product_kind_line"] = "Деталь"
    wp = (product.card_workpiece_type or "").strip()
    if wp == "laser":
        thick = _laser_thickness_str(product)
        summary["type_line"] = "Лазер"
        summary["workpiece_line"] = f"Лазерный · лист {thick} мм" if thick else "Лазерный"
        summary["material_line"] = mat
    elif wp == "preparatory":
        summary["type_line"] = "Заготовительный"
        summary["workpiece_line"] = "Заготовительный"
        summary["material_line"] = mat
    elif wp == "pki":
        summary["type_line"] = "ПКИ (заготовка)"
        summary["workpiece_line"] = "ПКИ"
        summary["material_line"] = mat
    else:
        summary["type_line"] = "Изделие"
        summary["workpiece_line"] = "—"
        summary["material_line"] = mat
    return summary


def plan_form_context(product: Product | None) -> dict[str, Any]:
    plan_product_type = ""
    workpiece_type_value = ""
    laser_sheet_thickness_value = ""
    workpiece_size_value = ""
    workpiece_type_enum_value = ""
    plan_material_value = ""

    if product is not None and getattr(product, "pk", None):
        plan_product_type = normalize_plan_product_type(product.card_product_type)
        workpiece_type_value = (product.card_workpiece_type or "").strip()
        laser_sheet_thickness_value = _laser_thickness_str(product)
        workpiece_size_value = (product.card_workpiece_size or "").strip()
        workpiece_type_enum_value = (product.card_workpiece_type_enum or "").strip()
        plan_material_value = _card_material_display(product)

    card = plan_card_summary(product)

    return {
        "plan_piece": None,
        "plan_product_type": plan_product_type,
        "plan_workpiece_type_value": workpiece_type_value,
        "plan_workpiece_type_choices": PLANNED_PRODUCT_WORKPIECE_TYPE_CHOICES,
        "plan_laser_sheet_thickness_value": laser_sheet_thickness_value,
        "plan_laser_material_marking_value": plan_material_value,
        "plan_made_material_value": plan_material_value,
        "plan_material_value": plan_material_value,
        "plan_workpiece_size_value": workpiece_size_value,
        "plan_workpiece_type_enum_value": workpiece_type_enum_value,
        "plan_laser_material_marking_suggestions": plan_material_suggestions(),
        "plan_material_suggestions": plan_material_suggestions(),
        "plan_display_type_line": card["type_line"],
        "plan_display_product_kind_line": card["product_kind_line"],
        "plan_display_workpiece_line": card["workpiece_line"],
        "plan_display_material_line": card["material_line"],
    }


def _sync_setup_material_and_size(product: Product, material: str, size: str) -> None:
    setup0 = (
        ProductSetup.objects.filter(product_id=product.pk)
        .order_by("sort_order", "id")
        .first()
    )
    if not setup0:
        return
    changed: list[str] = []
    if material and setup0.material != material:
        setup0.material = material
        changed.append("material")
    if size and setup0.size != size:
        setup0.size = size
        changed.append("size")
    if changed:
        setup0.save(update_fields=changed + ["updated_at"])


def apply_product_plan_post(product: Product, post: Any) -> str | None:
    """Сохранить параметры изделия на карточке. Возвращает текст ошибки или None."""
    err = validate_product_plan_post(post)
    if err:
        return err
    if not product.pk:
        return "Сначала сохраните изделие."

    t = normalize_plan_product_type(post.get("product_type") or post.get("plan_product_type"))
    if not t:
        return "Выберите тип изделия (Деталь, Сборка или ПКИ)."

    mat = (post.get("material") or post.get("plan_material") or "").strip()[:240]
    size = (post.get("workpiece_size") or "").strip()[:100]
    wte = (post.get("workpiece_type_enum") or "").strip()[:50]

    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product.pk)
        product.card_product_type = t

        if t == "made":
            wp = (post.get("workpiece_type") or "").strip()
            product.card_workpiece_type = wp
            if wp == "laser":
                thick, thick_err = parse_laser_sheet_thickness_mm(
                    post.get("laser_thickness") or post.get("laser_sheet_thickness_mm")
                )
                if thick is None:
                    return thick_err or "Укажите толщину листа, мм."
                product.card_laser_thickness_mm = thick
                product.card_material = mat
                product.card_workpiece_size = ""
                product.card_workpiece_type_enum = ""
            elif wp == "preparatory":
                product.card_laser_thickness_mm = None
                product.card_material = mat
                product.card_workpiece_size = size
                product.card_workpiece_type_enum = wte
            elif wp == "pki":
                product.card_laser_thickness_mm = None
                product.card_material = mat
                product.card_workpiece_size = size
                product.card_workpiece_type_enum = ""
            else:
                product.card_laser_thickness_mm = None
                product.card_material = ""
                product.card_workpiece_size = ""
                product.card_workpiece_type_enum = ""

        elif t == "assembly":
            product.card_workpiece_type = ""
            product.card_laser_thickness_mm = None
            product.card_material = mat
            product.card_workpiece_size = size
            product.card_workpiece_type_enum = ""

        elif t == "pki":
            product.card_workpiece_type = ""
            product.card_laser_thickness_mm = None
            product.card_material = mat
            product.card_workpiece_size = size
            product.card_workpiece_type_enum = ""

        product.save(
            update_fields=[
                "card_product_type",
                "card_workpiece_type",
                "card_laser_thickness_mm",
                "card_material",
                "card_workpiece_size",
                "card_workpiece_type_enum",
                "updated_at",
            ]
        )
        if mat or size:
            _sync_setup_material_and_size(product, mat, size)

    return None


# Обратная совместимость (старые импорты)
validate_product_specs_post = validate_product_plan_post
apply_product_specs_post = apply_product_plan_post
product_specs_form_context = plan_form_context
specs_inline_state_payload = plan_inline_state_payload
specs_card_summary = plan_card_summary
