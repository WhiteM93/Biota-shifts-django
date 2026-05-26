"""
python manage.py create_inventory_bulk
python manage.py create_inventory_bulk --count 20 --prefix "ТЕСТ"
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from shifts.insert_constants import build_insert_display_name, normalize_insert_machining_apps
from shifts.models import (
    CenterDrillSpec,
    CountersinkSpec,
    DrillSpec,
    EndMillSpec,
    InsertSpec,
    TapSpec,
    ToolItem,
    normalize_work_material_codes,
)

CATEGORIES = ("end_mill", "tap", "center_drill", "countersink", "drill", "insert")
END_MILL_TYPES_CYCLE = ("end", "roughing", "ball", "radius", "t_slot")
COATINGS = ("none", "yellow", "black", "brown", "multicolor")
MATERIALS = ("hss", "hss_co", "carbide")
WORK_MATS = ("P", "M", "K", "N", "P,M", "M,K", "P,K,N", "S", "H", "PW")


class Command(BaseCommand):
    help = "Создать N тестовых позиций склада в каждой категории инструмента"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=20, help="Позиций на категорию (по умолчанию 20)")
        parser.add_argument("--prefix", type=str, default="ТЕСТ", help="Префикс наименования")

    def handle(self, *args, **options):
        count = max(1, int(options["count"]))
        prefix = (options["prefix"] or "ТЕСТ").strip()
        created = 0

        for i in range(1, count + 1):
            d = Decimal("3") + Decimal(i)
            coating = COATINGS[(i - 1) % len(COATINGS)]
            material = MATERIALS[(i - 1) % len(MATERIALS)]
            work = normalize_work_material_codes(WORK_MATS[(i - 1) % len(WORK_MATS)])
            qty = 5 + (i % 15)

            n = f"{prefix} фреза #{i:02d}"
            tool = ToolItem.objects.create(
                category="end_mill",
                name=n,
                tool_material=material,
                coating_type=coating,
                work_material=work,
                main_diameter_mm=d,
                quantity=qty,
                notes="Автотест склада",
            )
            EndMillSpec.objects.create(
                tool=tool,
                mill_type=END_MILL_TYPES_CYCLE[(i - 1) % len(END_MILL_TYPES_CYCLE)],
                diameter_mm=d,
                corner_radius_mm=(d / 2 if i % 3 == 0 else None),
                overall_length_mm=d * Decimal("8"),
                cutting_length_mm=d * Decimal("2"),
                flutes_count=2 + (i % 5),
            )
            created += 1

            m = 3 + i
            n = f"{prefix} метчик M{m} #{i:02d}"
            tool = ToolItem.objects.create(
                category="tap",
                name=n,
                tool_material=material,
                coating_type=coating,
                work_material=work,
                main_diameter_mm=Decimal(m),
                quantity=qty,
                notes="Автотест склада",
            )
            TapSpec.objects.create(
                tool=tool,
                thread_standard="metric",
                size_label=f"M{m}",
                pitch_mm=Decimal("1.000") + Decimal(i % 5) * Decimal("0.25"),
                hole_type=("through", "blind", "any")[(i - 1) % 3],
                tap_type=("cutting", "forming", "thread_mill")[(i - 1) % 3],
                overall_length_mm=Decimal("50") + d,
                cutting_length_mm=Decimal("12") + Decimal(i),
            )
            created += 1

            n = f"{prefix} центровка #{i:02d}"
            tool = ToolItem.objects.create(
                category="center_drill",
                name=n,
                tool_material=material,
                coating_type=coating,
                work_material=work,
                main_diameter_mm=d,
                quantity=qty,
                notes="Автотест склада",
            )
            CenterDrillSpec.objects.create(
                tool=tool,
                diameter_mm=Decimal("1") + Decimal(i % 6) * Decimal("0.5"),
                overall_length_mm=Decimal("25") + d,
                angle_deg=("60", "90", "120")[(i - 1) % 3],
            )
            created += 1

            n = f"{prefix} зенкер #{i:02d}"
            tool = ToolItem.objects.create(
                category="countersink",
                name=n,
                tool_material=material,
                coating_type=coating,
                work_material=work,
                main_diameter_mm=d + Decimal("2"),
                quantity=qty,
                notes="Автотест склада",
            )
            CountersinkSpec.objects.create(
                tool=tool,
                countersink_type=("machine", "hand")[(i - 1) % 2],
                diameter_mm=d + Decimal("2"),
                angle_deg=("90", "60", "75", "120")[(i - 1) % 4],
                overall_length_mm=Decimal("40") + d,
                flutes_count=3 + (i % 4),
                size_label=f"DIN-{i:02d}",
            )
            created += 1

            n = f"{prefix} сверло Ø{d} #{i:02d}"
            tool = ToolItem.objects.create(
                category="drill",
                name=n,
                tool_material=material,
                coating_type=coating,
                work_material=work,
                main_diameter_mm=d,
                quantity=qty,
                notes="Автотест склада",
            )
            DrillSpec.objects.create(
                tool=tool,
                diameter_mm=d,
                overall_length_mm=Decimal("60") + d * Decimal("5"),
                cutting_length_mm=Decimal("30") + d * Decimal("3"),
                angle_deg=Decimal("118.00") if i % 2 else Decimal("140.00"),
            )
            created += 1

            shapes = ("C", "D", "S", "T", "V", "W")
            shape = shapes[(i - 1) % len(shapes)]
            edge = ("09", "12", "16", "19", "20", "25")[i % 6]
            th = ("03", "04", "05", "06")[i % 4]
            nr = ("04", "08", "12", "16")[i % 4]
            n = f"{prefix} пластина {shape}{edge} #{i:02d}"
            tool = ToolItem.objects.create(
                category="insert",
                name=n,
                tool_material=material,
                coating_type=coating,
                work_material=work,
                main_diameter_mm=None,
                quantity=qty,
                notes="Автотест склада",
            )
            mach_apps = ("1", "2", "3", "1,2", "2,3", "1,3", "1,2,3")
            spec = InsertSpec(
                tool=tool,
                insert_shape=shape,
                relief_angle="N",
                tolerance_class="M",
                mounting_chip="G",
                cutting_edge_length_code=edge,
                thickness_code=th,
                nose_radius_code=nr,
                milling_family="APKT" if i % 2 else "SEHT",
                chipbreaker_grade=f"YG50{i % 10}" if i % 3 else f"PM{4200 + i}",
                machining_application=normalize_insert_machining_apps(mach_apps[(i - 1) % len(mach_apps)]),
            )
            spec.save()
            iso_name = build_insert_display_name(spec.iso_designation, spec.milling_family, spec.chipbreaker_grade)
            tool.name = f"{prefix} {iso_name}".strip()
            tool.save(update_fields=["name"])
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} items ({count} per category, {len(CATEGORIES)} categories)."
            )
        )
