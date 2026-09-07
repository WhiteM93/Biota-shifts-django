"""Наполнение справочника «Типы склада» текущими категориями ToolItem."""
from __future__ import annotations

from django.db import transaction

from shifts.models import (
    CENTER_DRILL_ANGLES,
    COATING_TYPES,
    COUNTERSINK_ANGLES,
    COUNTERSINK_TYPES,
    END_MILL_TYPES,
    TAP_HOLE_TYPES,
    TAP_TOOL_TYPES,
    THREAD_KINDS,
    THREAD_STANDARDS,
    TOOL_MATERIAL_TYPES,
    StockToolField,
    StockToolSubtype,
    StockToolType,
)
from shifts.collet_constants import COLLET_TYPES
from shifts.body_tool_constants import (
    BALL_MILL_SHANK_TYPES,
    BODY_TOOL_FAMILIES,
    CHAMFER_MILL_SHANK_TYPES,
    END_MILL_SHANK_TYPES,
    FACE_MILL_ANGLES,
    HIGH_SPEED_ANGLE_OPTIONS,
    HIGH_SPEED_BODY_STYLES,
    HIGH_SPEED_SHANK_TYPES,
    INDEXABLE_MILL_CUTTER_TYPES,
    MODULAR_HEAD_THREADS,
    ROUND_INSERT_SHANK_TYPES,
)
from shifts.insert_constants import INSERT_SHAPES, MILLING_INSERT_FAMILIES

MAX_SUBTYPES_PER_TYPE = 60
MAX_FIELDS_PER_SCOPE = 40

# Группы справочника «Типы склада» (не путать с ToolItem.category).
STOCK_TOOL_TYPE_GROUPS = [
    (
        "cutting",
        "Режущий инструмент",
        10,
        ("end-mill", "tap", "center-drill", "countersink", "drill", "insert"),
    ),
    (
        "tooling",
        "Оснастка",
        20,
        ("collet",),  # корпусной — отдельный тип со своими подтипами фрез
    ),
]


def _choices(pairs) -> list[str]:
    return [str(lab) for _, lab in pairs if str(lab).strip()]


def _upsert_type(*, code: str, name: str, sort_order: int, notes: str = "") -> StockToolType:
    obj, _ = StockToolType.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "sort_order": sort_order,
            "notes": notes,
            "is_active": True,
        },
    )
    return obj


def _upsert_subtype(tool_type: StockToolType, *, code: str, name: str, sort_order: int) -> StockToolSubtype:
    obj, _ = StockToolSubtype.objects.update_or_create(
        tool_type=tool_type,
        code=code,
        defaults={
            "name": name,
            "sort_order": sort_order,
            "is_active": True,
        },
    )
    return obj


def _upsert_field(
    tool_type: StockToolType,
    *,
    key: str,
    label: str,
    field_kind: str,
    sort_order: int,
    subtype: StockToolSubtype | None = None,
    choices: list[str] | None = None,
    required: bool = False,
    unit: str = "",
    help_text: str = "",
) -> StockToolField:
    obj, _ = StockToolField.objects.update_or_create(
        tool_type=tool_type,
        subtype=subtype,
        key=key,
        defaults={
            "label": label,
            "field_kind": field_kind,
            "choices": list(choices or []),
            "required": required,
            "unit": unit,
            "help_text": help_text,
            "sort_order": sort_order,
        },
    )
    return obj


def _common_tool_fields(tool_type: StockToolType, *, with_material: bool = True, with_coating: bool = True) -> None:
    order = 10
    if with_material:
        _upsert_field(
            tool_type,
            key="tool-material",
            label="Материал инструмента",
            field_kind="select",
            choices=_choices(TOOL_MATERIAL_TYPES),
            sort_order=order,
        )
        order += 10
    if with_coating:
        _upsert_field(
            tool_type,
            key="coating-type",
            label="Покрытие",
            field_kind="select",
            choices=_choices(COATING_TYPES),
            sort_order=order,
        )
        order += 10
    _upsert_field(
        tool_type,
        key="main-diameter-mm",
        label="Ø зажима",
        field_kind="number",
        unit="мм",
        sort_order=order,
    )


def _norm_code(raw: str) -> str:
    text = (raw or "").strip().lower().replace("_", "-")
    text = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in text).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text[:64]


def _unique_subtype_code(tool_type: StockToolType, base: str) -> str:
    code = _norm_code(base) or "item"
    if not StockToolSubtype.objects.filter(tool_type=tool_type, code=code).exists():
        return code
    for i in range(2, 100):
        candidate = f"{code}-{i}"[:64]
        if not StockToolSubtype.objects.filter(tool_type=tool_type, code=candidate).exists():
            return candidate
    return f"{code[:50]}-x"[:64]


def _unique_field_key(subtype: StockToolSubtype, base: str) -> str:
    key = _norm_code(base) or "field"
    if not StockToolField.objects.filter(subtype=subtype, key=key).exists():
        return key
    for i in range(2, 100):
        candidate = f"{key}-{i}"[:64]
        if not StockToolField.objects.filter(subtype=subtype, key=candidate).exists():
            return candidate
    return f"{key[:50]}-x"[:64]


def move_type_into_parent(source: StockToolType, target: StockToolType) -> StockToolSubtype:
    """Превращает тип в подтип другого типа. Бывшие подтипы → характеристика «Вид»."""
    if source.pk == target.pk:
        raise ValueError("Нельзя переместить тип в самого себя")
    if target.subtypes.count() >= MAX_SUBTYPES_PER_TYPE:
        raise ValueError(f"Лимит подтипов у «{target.name}»: {MAX_SUBTYPES_PER_TYPE}")

    with transaction.atomic():
        new_code = _unique_subtype_code(target, source.code or source.name)
        max_order = (
            target.subtypes.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
        )
        new_sub = StockToolSubtype.objects.create(
            tool_type=target,
            name=source.name,
            code=new_code,
            notes=source.notes or "",
            is_active=bool(source.is_active),
            sort_order=max_order + 10,
        )

        for field in list(source.fields.filter(subtype__isnull=True)):
            field.tool_type = target
            field.subtype = new_sub
            field.key = _unique_field_key(new_sub, field.key)
            field.save(update_fields=["tool_type", "subtype", "key", "updated_at"])

        old_subs = list(source.subtypes.prefetch_related("fields").order_by("sort_order", "name", "id"))
        kind_choices: list[str] = []
        for old in old_subs:
            kind_choices.append(old.name)
            for field in list(old.fields.all()):
                field.tool_type = target
                field.subtype = new_sub
                prefixed = f"{old.code}-{field.key}" if old.code else field.key
                field.key = _unique_field_key(new_sub, prefixed)
                field.save(update_fields=["tool_type", "subtype", "key", "updated_at"])
            old.delete()

        if kind_choices:
            kind_key = _unique_field_key(new_sub, "kind")
            scope_count = StockToolField.objects.filter(tool_type=target, subtype=new_sub).count()
            if scope_count < MAX_FIELDS_PER_SCOPE:
                StockToolField.objects.create(
                    tool_type=target,
                    subtype=new_sub,
                    key=kind_key,
                    label="Вид",
                    field_kind="select",
                    choices=kind_choices,
                    required=False,
                    sort_order=0,
                )

        source.delete()
    return new_sub


def regroup_stock_tool_types_into_groups() -> dict[str, int]:
    """Сводит плоские типы категорий в «Режущий инструмент» и «Оснастка».

    Не трогает ToolItem / остатки склада — только справочник StockToolType.
    Идемпотентно: уже вложенные коды пропускает; лишние верхнеуровневые дубликаты удаляет.
    """
    stats = {"parents": 0, "moved": 0, "skipped": 0, "orphans_removed": 0}
    for parent_code, parent_name, sort_order, child_codes in STOCK_TOOL_TYPE_GROUPS:
        parent = StockToolType.objects.filter(code=parent_code).first()
        if parent is None:
            parent = StockToolType.objects.filter(name=parent_name).first()
        if parent is None:
            parent = _upsert_type(
                code=parent_code,
                name=parent_name,
                sort_order=sort_order,
                notes="Группа UI. Ключи ToolItem.category не меняются.",
            )
        else:
            updates: list[str] = []
            if parent.code != parent_code and not StockToolType.objects.filter(code=parent_code).exclude(
                pk=parent.pk
            ).exists():
                parent.code = parent_code
                updates.append("code")
            if parent.name != parent_name:
                parent.name = parent_name
                updates.append("name")
            if parent.sort_order != sort_order:
                parent.sort_order = sort_order
                updates.append("sort_order")
            if updates:
                parent.save(update_fields=[*updates, "updated_at"])
        stats["parents"] += 1
        for child_code in child_codes:
            if parent.subtypes.filter(code=child_code).exists():
                orphan = StockToolType.objects.filter(code=child_code).exclude(pk=parent.pk).first()
                if orphan:
                    orphan.delete()
                    stats["orphans_removed"] += 1
                else:
                    stats["skipped"] += 1
                continue
            source = StockToolType.objects.filter(code=child_code).first()
            if source is None or source.pk == parent.pk:
                stats["skipped"] += 1
                continue
            move_type_into_parent(source, parent)
            stats["moved"] += 1
    return stats


def _leaf_already_grouped(code: str) -> bool:
    for parent_code, _name, _order, child_codes in STOCK_TOOL_TYPE_GROUPS:
        if code not in child_codes:
            continue
        parent = StockToolType.objects.filter(code=parent_code).first()
        if parent and parent.subtypes.filter(code=code).exists():
            return True
    return False


def seed_stock_tool_types(*, replace_fields: bool = False) -> dict[str, int]:
    """Создаёт/обновляет типы, подтипы и характеристики по текущим категориям склада.

    Если replace_fields=True — удаляет поля у сидируемых типов перед записью
    (подтипы и типы сохраняются).

    В конце сводит категории в группы «Режущий инструмент» / «Оснастка».
    Остатки ToolItem не затрагиваются.
    """
    stats = {"types": 0, "subtypes": 0, "fields": 0}

    def _maybe_type(*, code: str, name: str, sort_order: int, notes: str = "") -> StockToolType | None:
        if _leaf_already_grouped(code):
            return None
        obj = _upsert_type(code=code, name=name, sort_order=sort_order, notes=notes)
        stats["types"] += 1
        return obj

    # --- Фрезы ---
    end_mill = _maybe_type(code="end-mill", name="Фрезы", sort_order=10, notes="Категория ToolItem: end_mill")
    if end_mill:
        if replace_fields:
            StockToolField.objects.filter(tool_type=end_mill).delete()
        for i, (code, label) in enumerate(END_MILL_TYPES):
            _upsert_subtype(end_mill, code=code.replace("_", "-"), name=label, sort_order=(i + 1) * 10)
            stats["subtypes"] += 1
        _common_tool_fields(end_mill)
        for key, label, kind, unit, req, order in (
            ("diameter-mm", "Диаметр", "number", "мм", True, 100),
            ("corner-radius-mm", "Радиус угла", "number", "мм", False, 110),
            ("overall-length-mm", "Общая длина", "number", "мм", False, 120),
            ("cutting-length-mm", "Длина реж. части", "number", "мм", False, 130),
            ("flutes-count", "Количество кромок", "number", "", False, 140),
        ):
            _upsert_field(end_mill, key=key, label=label, field_kind=kind, unit=unit, required=req, sort_order=order)
            stats["fields"] += 1

    # --- Резьбовой ---
    tap = _maybe_type(code="tap", name="Резьбовой инструмент", sort_order=20, notes="Категория ToolItem: tap")
    if tap:
        if replace_fields:
            StockToolField.objects.filter(tool_type=tap).delete()
        for i, (code, label) in enumerate(TAP_TOOL_TYPES):
            _upsert_subtype(tap, code=code.replace("_", "-"), name=label, sort_order=(i + 1) * 10)
            stats["subtypes"] += 1
        _common_tool_fields(tap)
        for spec in (
            ("thread-standard", "Стандарт резьбы", "select", _choices(THREAD_STANDARDS), True, "", 100),
            ("thread-kind", "Тип резьбы", "select", _choices(THREAD_KINDS), False, "", 110),
            ("size-label", "Размер", "text", [], True, "", 120),
            ("pitch-mm", "Шаг", "number", [], False, "мм", 130),
            ("tpi", "TPI", "number", [], False, "", 140),
            ("hole-type", "Отверстие", "select", _choices(TAP_HOLE_TYPES), True, "", 150),
            ("overall-length-mm", "Общая длина", "number", [], False, "мм", 160),
            ("cutting-length-mm", "Длина реж. части", "number", [], False, "мм", 170),
        ):
            key, label, kind, choices, req, unit, order = spec
            _upsert_field(
                tap,
                key=key,
                label=label,
                field_kind=kind,
                choices=choices,
                required=req,
                unit=unit,
                sort_order=order,
            )
            stats["fields"] += 1

    # --- Центровки ---
    center = _maybe_type(code="center-drill", name="Центровки", sort_order=30, notes="Категория ToolItem: center_drill")
    if center:
        if replace_fields:
            StockToolField.objects.filter(tool_type=center).delete()
        _common_tool_fields(center)
        for key, label, kind, choices, req, unit, order in (
            ("diameter-mm", "Диаметр", "number", [], True, "мм", 100),
            ("overall-length-mm", "Длина", "number", [], False, "мм", 110),
            ("angle-deg", "Угол", "select", _choices(CENTER_DRILL_ANGLES), True, "°", 120),
        ):
            _upsert_field(
                center,
                key=key,
                label=label,
                field_kind=kind,
                choices=choices,
                required=req,
                unit=unit,
                sort_order=order,
            )
            stats["fields"] += 1

    # --- Зенкера ---
    cs = _maybe_type(code="countersink", name="Зенкера", sort_order=40, notes="Категория ToolItem: countersink")
    if cs:
        if replace_fields:
            StockToolField.objects.filter(tool_type=cs).delete()
        for i, (code, label) in enumerate(COUNTERSINK_TYPES):
            _upsert_subtype(cs, code=str(code).replace("_", "-"), name=label, sort_order=(i + 1) * 10)
            stats["subtypes"] += 1
        _common_tool_fields(cs)
        for key, label, kind, choices, req, unit, order in (
            ("diameter-mm", "Диаметр", "number", [], False, "мм", 100),
            ("angle-deg", "Угол", "select", _choices(COUNTERSINK_ANGLES), True, "°", 110),
            ("overall-length-mm", "Длина", "number", [], False, "мм", 120),
            ("flutes-count", "Количество кромок", "number", [], False, "", 130),
            ("size-label", "Размер", "text", [], False, "", 140),
        ):
            _upsert_field(
                cs,
                key=key,
                label=label,
                field_kind=kind,
                choices=choices,
                required=req,
                unit=unit,
                sort_order=order,
            )
            stats["fields"] += 1

    # --- Сверла ---
    drill = _maybe_type(code="drill", name="Сверла", sort_order=50, notes="Категория ToolItem: drill")
    if drill:
        if replace_fields:
            StockToolField.objects.filter(tool_type=drill).delete()
        _common_tool_fields(drill)
        for key, label, kind, choices, req, unit, order in (
            ("diameter-mm", "Диаметр", "number", [], True, "мм", 100),
            ("overall-length-mm", "Длина", "number", [], False, "мм", 110),
            ("cutting-length-mm", "Длина реж. части", "number", [], False, "мм", 120),
            ("angle-deg", "Угол", "number", [], False, "°", 130),
        ):
            _upsert_field(
                drill,
                key=key,
                label=label,
                field_kind=kind,
                choices=choices,
                required=req,
                unit=unit,
                sort_order=order,
            )
            stats["fields"] += 1

    # --- Пластинки ---
    insert = _maybe_type(code="insert", name="Пластинки", sort_order=60, notes="Категория ToolItem: insert")
    if insert:
        if replace_fields:
            StockToolField.objects.filter(tool_type=insert).delete()
        for i, (code, label) in enumerate(MILLING_INSERT_FAMILIES):
            _upsert_subtype(insert, code=str(code).replace("_", "-"), name=label, sort_order=(i + 1) * 10)
            stats["subtypes"] += 1
        _common_tool_fields(insert, with_material=True, with_coating=True)
        for key, label, kind, choices, req, unit, order in (
            ("insert-shape", "Форма (ISO)", "select", _choices(INSERT_SHAPES), True, "", 100),
            ("iso-designation", "Маркировка ISO", "text", [], False, "", 110),
            ("cutting-edge-length-mm", "Длина кромки", "number", [], False, "мм", 120),
            ("thickness-mm", "Толщина", "number", [], False, "мм", 130),
            ("nose-radius-mm", "R вершины", "number", [], False, "мм", 140),
        ):
            _upsert_field(
                insert,
                key=key,
                label=label,
                field_kind=kind,
                choices=choices,
                required=req,
                unit=unit,
                sort_order=order,
            )
            stats["fields"] += 1

    # --- Цанги ---
    collet = _maybe_type(code="collet", name="Цанги", sort_order=70, notes="Категория ToolItem: collet")
    if collet:
        if replace_fields:
            StockToolField.objects.filter(tool_type=collet).delete()
        for i, (code, label) in enumerate(COLLET_TYPES):
            _upsert_subtype(collet, code=str(code).replace("_", "-"), name=label, sort_order=(i + 1) * 10)
            stats["subtypes"] += 1
        _upsert_field(collet, key="size-label", label="Размер", field_kind="text", required=False, sort_order=100)
        _upsert_field(
            collet,
            key="inner-diameter-mm",
            label="Внутренний Ø",
            field_kind="number",
            unit="мм",
            sort_order=110,
        )
        stats["fields"] += 2

    # Корпусной не кладём в плоский лист — после regroup поднимаем отдельным типом
    # с подтипами фрез СМП и полями по каждому виду.
    regroup = regroup_stock_tool_types_into_groups()
    stats["regroup_moved"] = regroup.get("moved", 0)
    stats["regroup_skipped"] = regroup.get("skipped", 0)
    body_stats = restore_body_tool_cutter_catalog(replace_fields=replace_fields)
    stats["body_subtypes"] = body_stats.get("subtypes", 0)
    stats["body_fields"] = body_stats.get("fields", 0)
    return stats


def _shank_choices(pairs) -> list[str]:
    return [str(lab) for code, lab in pairs if code]


def _yes_no() -> list[str]:
    return ["Нет", "Есть"]


def _angle_choices(pairs) -> list[str]:
    return [str(lab) for _, lab in pairs if str(lab).strip() and str(lab).strip() != "—"]


def restore_body_tool_cutter_catalog(*, replace_fields: bool = True) -> dict[str, int]:
    """Корпусной — отдельный тип: подтипы = виды фрез СМП с их характеристиками.

    Убирает схлопнутый subtype body-tool из «Оснастка» (после regroup) и
    восстанавливает детальные поля. ToolItem / остатки склада не трогает.
    """
    stats = {"subtypes": 0, "fields": 0, "removed_flat": 0}

    tooling = StockToolType.objects.filter(code="tooling").first()
    if tooling:
        flat = tooling.subtypes.filter(code="body-tool").first()
        if flat:
            StockToolField.objects.filter(subtype=flat).delete()
            flat.delete()
            stats["removed_flat"] += 1

    body = _upsert_type(
        code="body-tool",
        name="Корпусной инструмент",
        sort_order=30,
        notes="Категория ToolItem: body_tool. Подтипы — типы фрез СМП.",
    )
    if replace_fields:
        StockToolField.objects.filter(tool_type=body).delete()
        body.subtypes.all().delete()

    # Общее для всех подтипов (на уровне типа)
    _upsert_field(
        body,
        key="family",
        label="Семейство",
        field_kind="select",
        choices=_choices(BODY_TOOL_FAMILIES),
        required=True,
        sort_order=5,
    )
    stats["fields"] += 1

    insert_family_choices = _choices(MILLING_INSERT_FAMILIES)
    face_angles = _angle_choices(FACE_MILL_ANGLES)
    hs_angles = _angle_choices(HIGH_SPEED_ANGLE_OPTIONS)
    hs_styles = [lab for code, lab in HIGH_SPEED_BODY_STYLES if code]
    yes_no = _yes_no()
    thread_choices = [lab for code, lab in MODULAR_HEAD_THREADS if code]

    # (code, name, fields list of tuples)
    cutter_specs: list[tuple[str, str, list[tuple]]] = [
        (
            "face",
            "Торцевые насадные фрезы",
            [
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 10),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 20),
                ("mount-diameter-mm", "d посадки", "number", [], False, "мм", 30),
                ("coolant-through", "СОЖ", "select", yes_no, False, "", 40),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 50),
                ("insert-size", "Размер пластины", "text", [], False, "", 60),
                ("ap-max-mm", "ap max", "number", [], False, "мм", 70),
                ("approach-angle", "Угол подхода", "select", face_angles, False, "°", 80),
                ("brand", "Бренд", "text", [], False, "", 90),
            ],
        ),
        (
            "end",
            "Концевые насадные фрезы",
            [
                ("brand", "Бренд", "text", [], False, "", 10),
                ("shank-type", "Хвостовик", "select", _shank_choices(END_MILL_SHANK_TYPES), False, "", 20),
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 30),
                ("mount-diameter-mm", "d хвостовика", "number", [], False, "мм", 40),
                ("overall-length-mm", "Длина L", "number", [], False, "мм", 50),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 60),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 70),
                ("insert-size", "Размер пластины", "text", [], False, "", 80),
                ("coolant-through", "СОЖ", "select", yes_no, False, "", 90),
                ("approach-angle", "Угол подхода", "select", face_angles, False, "°", 100),
            ],
        ),
        (
            "chamfer",
            "Фасочные фрезы",
            [
                ("brand", "Бренд", "text", [], False, "", 10),
                ("shank-type", "Хвостовик", "select", _shank_choices(CHAMFER_MILL_SHANK_TYPES), False, "", 20),
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 30),
                ("mount-diameter-mm", "d", "number", [], False, "мм", 40),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 50),
                ("variable-angle", "Переменный угол", "select", ["Нет", "Да"], False, "", 60),
                ("coolant-through", "СОЖ", "select", yes_no, False, "", 70),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 80),
                ("insert-size", "Размер пластины", "text", [], False, "", 90),
            ],
        ),
        (
            "high-speed",
            "Высокоскоростные фрезы",
            [
                ("brand", "Бренд", "text", [], False, "", 10),
                ("shank-type", "Хвостовик", "select", _shank_choices(HIGH_SPEED_SHANK_TYPES), False, "", 20),
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 30),
                ("mount-diameter-mm", "d", "number", [], False, "мм", 40),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 50),
                ("hs-body-style", "Насадная / концевая", "select", hs_styles, False, "", 60),
                ("has-purpose", "Назначение", "select", yes_no, False, "", 70),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 80),
                ("insert-size", "Размер пластины", "text", [], False, "", 90),
                ("approach-angle", "Угол", "select", hs_angles, False, "", 100),
            ],
        ),
        (
            "round-insert",
            "Фрезы с круглыми пластинами",
            [
                ("brand", "Бренд", "text", [], False, "", 10),
                ("shank-type", "Хвостовик", "select", _shank_choices(ROUND_INSERT_SHANK_TYPES), False, "", 20),
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 30),
                ("mount-diameter-mm", "d", "number", [], False, "мм", 40),
                ("overall-length-mm", "Длина L", "number", [], False, "мм", 50),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 60),
                ("hs-body-style", "Насадная / концевая", "select", hs_styles, False, "", 70),
                ("corner-radius-mm", "Радиус пластины", "number", [], False, "мм", 80),
                ("coolant-through", "СОЖ", "select", yes_no, False, "", 90),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 100),
                ("insert-size", "Размер пластины", "text", [], False, "", 110),
            ],
        ),
        (
            "disc",
            "Дисковые фрезы",
            [
                ("brand", "Бренд", "text", [], False, "", 10),
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 20),
                ("mount-diameter-mm", "d посадки", "number", [], False, "мм", 30),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 40),
                ("cutting-length-mm", "Ширина H", "number", [], False, "мм", 50),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 60),
                ("insert-size", "Размер пластины", "text", [], False, "", 70),
            ],
        ),
        (
            "ball",
            "Сферические фрезы",
            [
                ("brand", "Бренд", "text", [], False, "", 10),
                ("shank-type", "Хвостовик", "select", _shank_choices(BALL_MILL_SHANK_TYPES), False, "", 20),
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 30),
                ("mount-diameter-mm", "d", "number", [], False, "мм", 40),
                ("overall-length-mm", "Длина L", "number", [], False, "мм", 50),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 60),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 70),
                ("insert-size", "Размер пластины", "text", [], False, "", 80),
                ("insert-compat", "Совместимые пластины", "text", [], False, "", 90),
            ],
        ),
        (
            "modular-head",
            "Фрезерные головки с пластинами",
            [
                ("brand", "Бренд", "text", [], False, "", 10),
                ("mount-thread", "Резьба крепления", "select", thread_choices, False, "", 20),
                ("diameter-mm", "Ø резания D", "number", [], True, "мм", 30),
                ("teeth-count", "Число зубьев Z", "number", [], False, "", 40),
                ("insert-family", "Семейство пластин", "select", insert_family_choices, False, "", 50),
                ("insert-size", "Размер пластины", "text", [], False, "", 60),
                ("insert-compat", "Совместимые пластины", "text", [], False, "", 70),
            ],
        ),
    ]

    # Сохраняем соответствие кодов INDEXABLE_MILL_CUTTER_TYPES (face → face, high_speed → high-speed)
    code_by_key = {k: k.replace("_", "-") for k, _ in INDEXABLE_MILL_CUTTER_TYPES}

    for i, (code, name, fields) in enumerate(cutter_specs):
        # normalize code from INDEXABLE keys if present
        canon = code_by_key.get(code.replace("-", "_"), code)
        sub = _upsert_subtype(body, code=canon, name=name, sort_order=(i + 1) * 10)
        stats["subtypes"] += 1
        for key, label, kind, choices, req, unit, order in fields:
            _upsert_field(
                body,
                key=key,
                label=label,
                field_kind=kind,
                choices=choices,
                required=req,
                unit=unit,
                sort_order=order,
                subtype=sub,
            )
            stats["fields"] += 1

    return stats
