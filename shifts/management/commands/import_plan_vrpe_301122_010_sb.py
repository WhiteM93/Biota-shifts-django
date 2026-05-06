"""Импорт сборки ВРПЕ.301122.010 СБ и состава из спецификации (идempotentно)."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from shifts.models import PlannedAssemblyComponent, PlannedProduct, PlannedProductStage


SHARED_ROUTE_STAGES = [
    ("Сборка", "запрессовка шпильки резьбовой"),
    ("Сборка", "установка заклепки гаечной"),
    ("Сборка", "установка стоек+радиатор"),
    ("Покраска", "Изоляция под покраску"),
    ("Покраска", "Окраска"),
    ("Покраска", "Снятие изоляции"),
    ("Маркировка", ""),
]


def _set_stages(product: PlannedProduct, stages: list[tuple[str, str]]) -> None:
    product.stages.all().delete()
    PlannedProductStage.objects.bulk_create(
        [
            PlannedProductStage(product=product, sort_order=i, department=dep, description=(desc or "").strip())
            for i, (dep, desc) in enumerate(stages)
            if dep
        ]
    )


def _ensure_planned_product(
    *,
    name: str,
    is_assembly: bool,
    is_purchased: bool,
    workpiece_type: str = "",
    laser_sheet_thickness_mm: Decimal | None = None,
    laser_material_marking: str = "",
) -> PlannedProduct:
    d = dict(
        is_assembly=is_assembly,
        is_purchased=is_purchased,
        workpiece_type=workpiece_type if (not is_assembly and not is_purchased) else "",
        laser_sheet_thickness_mm=laser_sheet_thickness_mm if (not is_assembly and not is_purchased) else None,
        laser_material_marking=(laser_material_marking or "") if (not is_assembly and not is_purchased) else "",
    )
    obj, created = PlannedProduct.objects.get_or_create(name=name, defaults=d)
    if not created:
        for k, v in d.items():
            setattr(obj, k, v)
        obj.save(
            update_fields=(
                "is_assembly",
                "is_purchased",
                "workpiece_type",
                "laser_sheet_thickness_mm",
                "laser_material_marking",
                "updated_at",
            )
        )
    return obj


class Command(BaseCommand):
    help = 'Импортирует сборку ВРПЕ.301122.010 СБ «Кожух» и строки BOM в раздел «План»'

    def handle(self, *args, **options):
        route_suffix = "/".join(
            [
                "Сборочная (запрессовка шпильки резьбовой)",
                "Сборочная (установка заклепки гаечной)",
                "Сборочная(установка стоек+радиатор)",
                "Изоляция под покраску",
                "Покраска",
                "Снятие изоляции",
                "Маркировочная",
            ]
        )

        nm_assembly = f"ВРПЕ.301122.010 СБ - Кожух {route_suffix}"

        nm_kozhukh_laser = (
            f"ВРПЕ.745535.020 - Кожух 1шт заготовка лазерный 2.5 АМг2М {route_suffix}"
        )
        nm_radiator = f"ВРПЕ.752694.034-01 - Радиатор 1шт заготовка пки, изделие {route_suffix}"

        bom_lines: list[tuple[str, int]] = [
            (nm_kozhukh_laser, 1),
            (nm_radiator, 1),
            (
                "Винт В2.М3-6gx6.21.12Х18Н10Т ГОСТ 17473-80 10 шт ПКИ",
                10,
            ),
            (
                "Шайба C.3.21 ГОСТ 11371-78 10 шт ПКИ",
                10,
            ),
            (
                "Заклепка гаечная ITSG М4 с насечкой потайной бортик арт. 00ITSGM04C060A2 18 шт ПКИ",
                18,
            ),
            (
                "Резьбовая закрытая заклепка М4 с потайным бортиком и насечками, нержавеющая сталь А2 2 шт ПКИ",
                2,
            ),
            (
                "Стойка для печатных плат PCHNN-22SS М3, нержавеющая сталь 3 шт ПКИ",
                3,
            ),
            (
                "Стойка для печатных плат PCHNN-24SS М3, нержавеющая сталь 1 шт ПКИ",
                1,
            ),
            (
                "Шпилька резьбовая запрессовочная М3х10 мм тип FHS, нержавеющая сталь А2 2 шт ПКИ",
                2,
            ),
        ]

        with transaction.atomic():
            kozh = _ensure_planned_product(
                name=nm_kozhukh_laser,
                is_assembly=False,
                is_purchased=False,
                workpiece_type="laser",
                laser_sheet_thickness_mm=Decimal("2.5"),
                laser_material_marking="АМг2М",
            )
            _set_stages(kozh, SHARED_ROUTE_STAGES)

            rad = _ensure_planned_product(
                name=nm_radiator,
                is_assembly=False,
                is_purchased=False,
                workpiece_type="pki",
            )
            _set_stages(rad, SHARED_ROUTE_STAGES)

            pki_objs: dict[str, PlannedProduct] = {}
            for comp_name, _qty in bom_lines[2:]:
                pki_objs[comp_name] = _ensure_planned_product(
                    name=comp_name,
                    is_assembly=False,
                    is_purchased=True,
                )

            assembly, _ = PlannedProduct.objects.update_or_create(
                name=nm_assembly,
                defaults={
                    "is_assembly": True,
                    "is_purchased": False,
                    "workpiece_type": "",
                    "laser_sheet_thickness_mm": None,
                    "laser_material_marking": "",
                },
            )

            _set_stages(assembly, SHARED_ROUTE_STAGES)

            assembly.assembly_components.all().delete()

            bulk_comp: list[PlannedAssemblyComponent] = []
            for i, (comp_name, qty) in enumerate(bom_lines):
                if i == 0:
                    comp = kozh
                elif i == 1:
                    comp = rad
                else:
                    comp = pki_objs[comp_name]
                bulk_comp.append(
                    PlannedAssemblyComponent(
                        assembly=assembly,
                        component=comp,
                        sort_order=i,
                        quantity=qty,
                    )
                )
            PlannedAssemblyComponent.objects.bulk_create(bulk_comp)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: сборка «{nm_assembly}» (pk={assembly.pk}), строк состава: {len(bulk_comp)}"
            )
        )
