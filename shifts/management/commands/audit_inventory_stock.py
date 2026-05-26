"""Проверка целостности данных склада после наполнения."""
from django.core.management.base import BaseCommand
from django.db.models import Count

from shifts.insert_constants import INSERT_MACHINING_APPLICATION_VALUES
from shifts.models import (
    WORK_MATERIAL_CODE_SET,
    CenterDrillSpec,
    CountersinkSpec,
    DrillSpec,
    EndMillSpec,
    InsertSpec,
    TapSpec,
    ToolItem,
)


class Command(BaseCommand):
    help = "Аудит позиций склада: количество по категориям, спеки, мультивыбор WM"

    def add_arguments(self, parser):
        parser.add_argument("--prefix", type=str, default="", help="Фильтр по префиксу name")
        parser.add_argument(
            "--notes-tag",
            type=str,
            default="Автотест склада",
            help="Если prefix не задан — фильтр по полю notes (пусто = все позиции)",
        )

    def handle(self, *args, **options):
        prefix = (options.get("prefix") or "").strip()
        notes_tag = (options.get("notes_tag") or "Автотест склада").strip()
        qs = ToolItem.objects.filter(is_deleted=False)
        if prefix:
            qs = qs.filter(name__startswith=prefix)
        elif notes_tag:
            qs = qs.filter(notes=notes_tag)

        errors: list[str] = []
        warnings: list[str] = []
        lines: list[str] = []

        by_cat = dict(qs.values_list("category").annotate(c=Count("id")).values_list("category", "c"))
        lines.append("=== Позиций по категориям ===")
        for cat in ("end_mill", "tap", "center_drill", "countersink", "drill", "insert"):
            n = by_cat.get(cat, 0)
            lines.append(f"  {cat}: {n}")

        spec_map = {
            "end_mill": ("end_mill_spec", EndMillSpec),
            "tap": ("tap_spec", TapSpec),
            "center_drill": ("center_drill_spec", CenterDrillSpec),
            "countersink": ("countersink_spec", CountersinkSpec),
            "drill": ("drill_spec", DrillSpec),
            "insert": ("insert_spec", InsertSpec),
        }
        lines.append("\n=== Спецификации ===")
        for cat, (rel_name, _model) in spec_map.items():
            tools = qs.filter(category=cat)
            missing = tools.filter(**{f"{rel_name}__isnull": True}).count()
            if missing:
                errors.append(f"{cat}: {missing} позиций без спецификации")
            lines.append(f"  {cat}: {tools.count() - missing}/{tools.count()} со спекой")

        lines.append("\n=== Материал обработки (мультивыбор) ===")
        multi_wm = 0
        bad_wm = 0
        for t in qs.exclude(work_material="").iterator():
            codes = t.work_material_codes_list()
            if len(codes) > 1:
                multi_wm += 1
            for c in codes:
                if c not in WORK_MATERIAL_CODE_SET:
                    bad_wm += 1
                    errors.append(f"Tool #{t.id} ({t.name}): неверный код WM «{c}»")
        lines.append(f"  с несколькими группами: {multi_wm}")
        lines.append(f"  неверных кодов: {bad_wm}")

        lines.append("\n=== Пластинки: виды обработки ===")
        ins_qs = qs.filter(category="insert").select_related("insert_spec")
        multi_mach = 0
        for t in ins_qs:
            spec = getattr(t, "insert_spec", None)
            if not spec:
                continue
            apps = [a.strip() for a in (spec.machining_application or "").split(",") if a.strip()]
            if len(apps) > 1:
                multi_mach += 1
            for a in apps:
                if a not in INSERT_MACHINING_APPLICATION_VALUES:
                    errors.append(f"Insert #{t.id}: неверный вид обработки «{a}»")
            if not spec.iso_designation:
                warnings.append(f"Insert #{t.id}: пустая ISO маркировка")
        lines.append(f"  с несколькими видами обработки: {multi_mach}")

        lines.append("\n=== Итог ===")
        if errors:
            lines.append(f"  ОШИБКИ: {len(errors)}")
            for e in errors[:20]:
                lines.append(f"    - {e}")
            if len(errors) > 20:
                lines.append(f"    ... и ещё {len(errors) - 20}")
        else:
            lines.append("  Ошибок данных не найдено.")
        if warnings:
            lines.append(f"  Предупреждений: {len(warnings)}")

        self.stdout.write("\n".join(lines))
        if errors:
            raise SystemExit(1)
