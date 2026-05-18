"""
Команда: python manage.py create_test_inventory

Создаёт тестовые данные для страницы склада:
  - позиции (ToolItem + спецификации)
  - приходы (StockMovement type=restock)
  - выдачи и возвраты (StockMovement type=issue / restock с parent_issue)
  - заявки на закупку (PurchaseRequest)

Безопасна для повторного запуска: пропускает создание, если позиции уже есть.
"""

import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

from shifts.models import (
    ToolItem,
    EndMillSpec,
    TapSpec,
    CenterDrillSpec,
    CountersinkSpec,
    DrillSpec,
    StockMovement,
    PurchaseRequest,
)


def _date(days_ago: int) -> datetime.date:
    return (datetime.date.today() - datetime.timedelta(days=days_ago))


class Command(BaseCommand):
    help = "Создать тестовые данные склада (позиции, приходы, выдачи, возвраты, закупки)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Удалить все существующие данные склада и пересоздать",
        )

    def handle(self, *args, **options):
        force = options["force"]
        if force:
            self.stdout.write(self.style.WARNING("--force: удаляю существующие данные…"))
            PurchaseRequest.objects.all().delete()
            StockMovement.objects.all().delete()
            ToolItem.objects.all().delete()
        elif ToolItem.objects.filter(is_deleted=False).exists():
            self.stdout.write(self.style.WARNING(
                "Позиции уже есть — создаю только недостающие разделы. "
                "Используйте --force чтобы пересоздать всё с нуля."
            ))
            self._create_purchases_if_missing()
            return

        self.stdout.write("Создаю тестовые позиции склада…")

        # --- ФРЕЗЫ ---
        em1 = ToolItem.objects.create(
            category="end_mill", name="Концевая фреза IZAR",
            tool_material="carbide", coating_type="black",
            work_material="P", main_diameter_mm="6.00", quantity=8,
            notes="Для черновой обработки стали",
        )
        EndMillSpec.objects.create(
            tool=em1, mill_type="end",
            diameter_mm="6.00", corner_radius_mm=None,
            overall_length_mm="57.00", cutting_length_mm="13.00", flutes_count=4,
        )

        em2 = ToolItem.objects.create(
            category="end_mill", name="Сферическая фреза Sandvik",
            tool_material="carbide", coating_type="yellow",
            work_material="P", main_diameter_mm="8.00", quantity=3,
        )
        EndMillSpec.objects.create(
            tool=em2, mill_type="ball",
            diameter_mm="8.00", corner_radius_mm="4.00",
            overall_length_mm="63.00", cutting_length_mm="19.00", flutes_count=2,
        )

        em3 = ToolItem.objects.create(
            category="end_mill", name="Обдирочная фреза GARANT",
            tool_material="carbide", coating_type="brown",
            work_material="P", main_diameter_mm="16.00", quantity=5,
            notes="Черновые проходы, высокая подача",
        )
        EndMillSpec.objects.create(
            tool=em3, mill_type="roughing",
            diameter_mm="16.00", corner_radius_mm=None,
            overall_length_mm="100.00", cutting_length_mm="45.00", flutes_count=6,
        )

        em4 = ToolItem.objects.create(
            category="end_mill", name="Радиусная фреза YG-1",
            tool_material="carbide", coating_type="multicolor",
            work_material="K", main_diameter_mm="10.00", quantity=2,
        )
        EndMillSpec.objects.create(
            tool=em4, mill_type="radius",
            diameter_mm="10.00", corner_radius_mm="2.00",
            overall_length_mm="75.00", cutting_length_mm="25.00", flutes_count=4,
        )

        em5 = ToolItem.objects.create(
            category="end_mill", name="Т-образная фреза JBO",
            tool_material="carbide", coating_type="none",
            work_material="P", main_diameter_mm="20.00", quantity=1,
            notes="Пазы типа «ласточкин хвост»",
        )
        EndMillSpec.objects.create(
            tool=em5, mill_type="t_slot",
            diameter_mm="20.00", corner_radius_mm=None,
            overall_length_mm="80.00", cutting_length_mm="8.00", flutes_count=3,
        )

        # --- РЕЗЬБОВОЙ ИНСТРУМЕНТ ---
        tap1 = ToolItem.objects.create(
            category="tap", name="Метчик M6 GÜHRING",
            tool_material="hss_co", coating_type="yellow",
            work_material="P", main_diameter_mm="6.00", quantity=10,
        )
        TapSpec.objects.create(
            tool=tap1, thread_standard="metric", size_label="M6",
            pitch_mm="1.000", tpi=None,
            hole_type="through", tap_type="cutting",
            overall_length_mm="66.00", cutting_length_mm="15.00",
        )

        tap2 = ToolItem.objects.create(
            category="tap", name="Метчик M8×1,25 DORMER",
            tool_material="hss_co", coating_type="black",
            work_material="P", main_diameter_mm="8.00", quantity=7,
            notes="Для глухих отверстий",
        )
        TapSpec.objects.create(
            tool=tap2, thread_standard="metric", size_label="M8",
            pitch_mm="1.250", tpi=None,
            hole_type="blind", tap_type="cutting",
            overall_length_mm="80.00", cutting_length_mm="18.00",
        )

        tap3 = ToolItem.objects.create(
            category="tap", name="Резьбофреза M10 Vardex",
            tool_material="carbide", coating_type="multicolor",
            work_material="M", main_diameter_mm="10.00", quantity=2,
            notes="Нержавейка, одновременное фрезерование и нарезка",
        )
        TapSpec.objects.create(
            tool=tap3, thread_standard="metric", size_label="M10",
            pitch_mm="1.500", tpi=None,
            hole_type="any", tap_type="thread_mill",
            overall_length_mm="60.00", cutting_length_mm="12.00",
        )

        # --- ЦЕНТРОВКИ ---
        cd1 = ToolItem.objects.create(
            category="center_drill", name="Центровочное сверло A2",
            tool_material="hss", coating_type="none",
            work_material="P", main_diameter_mm="6.30", quantity=12,
        )
        CenterDrillSpec.objects.create(
            tool=cd1,
            diameter_mm="2.00", overall_length_mm="31.50", angle_deg="60",
        )

        cd2 = ToolItem.objects.create(
            category="center_drill", name="Центровочное сверло A4",
            tool_material="hss", coating_type="none",
            work_material="P", main_diameter_mm="10.00", quantity=6,
        )
        CenterDrillSpec.objects.create(
            tool=cd2,
            diameter_mm="4.00", overall_length_mm="40.00", angle_deg="60",
        )

        # --- ЗЕНКЕРА ---
        cs1 = ToolItem.objects.create(
            category="countersink", name="Зенкер машинный DIN 335",
            tool_material="hss", coating_type="none",
            work_material="P", main_diameter_mm="12.00", quantity=4,
        )
        CountersinkSpec.objects.create(
            tool=cs1, countersink_type="machine",
            diameter_mm="12.00", angle_deg="90",
            overall_length_mm="56.00", flutes_count=6, size_label="DIN 335",
        )

        cs2 = ToolItem.objects.create(
            category="countersink", name="Зенкер ручной 90° HSS",
            tool_material="hss", coating_type="none",
            work_material="P", main_diameter_mm="20.00", quantity=2,
        )
        CountersinkSpec.objects.create(
            tool=cs2, countersink_type="hand",
            diameter_mm="20.00", angle_deg="90",
            overall_length_mm="73.00", flutes_count=3, size_label="",
        )

        # --- СВЕРЛА ---
        dr1 = ToolItem.objects.create(
            category="drill", name="Сверло HSS-Co Ø4",
            tool_material="hss_co", coating_type="none",
            work_material="P", main_diameter_mm="4.00", quantity=20,
        )
        DrillSpec.objects.create(
            tool=dr1,
            diameter_mm="4.00", overall_length_mm="75.00",
            cutting_length_mm="43.00", angle_deg="118.00",
        )

        dr2 = ToolItem.objects.create(
            category="drill", name="Сверло HSS-Co Ø6,5",
            tool_material="hss_co", coating_type="none",
            work_material="P", main_diameter_mm="6.50", quantity=15,
        )
        DrillSpec.objects.create(
            tool=dr2,
            diameter_mm="6.50", overall_length_mm="101.00",
            cutting_length_mm="63.00", angle_deg="118.00",
        )

        dr3 = ToolItem.objects.create(
            category="drill", name="Сверло твердосплав Ø10",
            tool_material="carbide", coating_type="yellow",
            work_material="P", main_diameter_mm="10.00", quantity=5,
            notes="Для сквозных отверстий под развёртку",
        )
        DrillSpec.objects.create(
            tool=dr3,
            diameter_mm="10.00", overall_length_mm="130.00",
            cutting_length_mm="87.00", angle_deg="140.00",
        )

        dr4 = ToolItem.objects.create(
            category="drill", name="Сверло HSS Ø3,3 (под M4)",
            tool_material="hss", coating_type="none",
            work_material="P", main_diameter_mm="3.30", quantity=30,
            notes="Предварительное сверление под метчик M4",
        )
        DrillSpec.objects.create(
            tool=dr4,
            diameter_mm="3.30", overall_length_mm="65.00",
            cutting_length_mm="36.00", angle_deg="118.00",
        )

        all_tools = [em1, em2, em3, em4, em5, tap1, tap2, tap3, cd1, cd2, cs1, cs2, dr1, dr2, dr3, dr4]
        self.stdout.write(f"  Создано {len(all_tools)} позиций.")

        # --- ПРИХОДЫ (restock) ---
        self.stdout.write("Создаю приходы…")
        restocks = [
            StockMovement(
                movement_type="restock", tool=em1, quantity=10,
                employee_name="", movement_date=_date(45),
                comment="Поставка IZAR, счёт №1042",
                created_by_account="admin",
            ),
            StockMovement(
                movement_type="restock", tool=tap1, quantity=20,
                employee_name="", movement_date=_date(40),
                comment="Поставка GÜHRING, заказ #GH-2024-08",
                created_by_account="admin",
            ),
            StockMovement(
                movement_type="restock", tool=dr4, quantity=50,
                employee_name="", movement_date=_date(38),
                comment="Оптовая закупка, 2 упаковки по 25 шт.",
                created_by_account="admin",
            ),
            StockMovement(
                movement_type="restock", tool=em3, quantity=5,
                employee_name="", movement_date=_date(25),
                comment="Поставка GARANT, экспресс-заказ",
                created_by_account="admin",
            ),
            StockMovement(
                movement_type="restock", tool=tap2, quantity=10,
                employee_name="", movement_date=_date(18),
                comment="Поставка DORMER",
                created_by_account="skladsik",
            ),
            StockMovement(
                movement_type="restock", tool=dr1, quantity=20,
                employee_name="", movement_date=_date(12),
                comment="",
                created_by_account="skladsik",
            ),
            StockMovement(
                movement_type="restock", tool=cs1, quantity=6,
                employee_name="", movement_date=_date(7),
                comment="Получено по накладной 188/24",
                created_by_account="admin",
            ),
        ]
        StockMovement.objects.bulk_create(restocks)
        self.stdout.write(f"  Создано {len(restocks)} приходов.")

        # --- ВЫДАЧИ (issue) ---
        self.stdout.write("Создаю выдачи…")
        issue1 = StockMovement.objects.create(
            movement_type="issue", tool=em1, quantity=2,
            employee_name="Иванов Алексей Петрович",
            movement_date=_date(30),
            comment="Токарный участок, заказ 301",
            created_by_account="skladsik",
        )
        issue2 = StockMovement.objects.create(
            movement_type="issue", tool=tap1, quantity=5,
            employee_name="Сидоров Дмитрий Николаевич",
            movement_date=_date(28),
            comment="",
            created_by_account="skladsik",
        )
        issue3 = StockMovement.objects.create(
            movement_type="issue", tool=dr2, quantity=3,
            employee_name="Петров Сергей Иванович",
            movement_date=_date(20),
            comment="Фрезерный станок №3",
            created_by_account="skladsik",
        )
        issue4 = StockMovement.objects.create(
            movement_type="issue", tool=em3, quantity=1,
            employee_name="Козлов Виктор Андреевич",
            movement_date=_date(15),
            comment="Для корпусной детали 10.4412",
            created_by_account="skladsik",
        )
        issue5 = StockMovement.objects.create(
            movement_type="issue", tool=tap2, quantity=2,
            employee_name="Иванов Алексей Петрович",
            movement_date=_date(10),
            comment="Повторная выдача, предыдущие сломались",
            created_by_account="skladsik",
        )
        issue6 = StockMovement.objects.create(
            movement_type="issue", tool=dr4, quantity=10,
            employee_name="Фролов Константин Олегович",
            movement_date=_date(6),
            comment="",
            created_by_account="skladsik",
        )
        self.stdout.write("  Создано 6 выдач.")

        # --- ВОЗВРАТЫ (restock с parent_issue) ---
        self.stdout.write("Создаю возвраты…")
        returns = [
            StockMovement(
                movement_type="restock", tool=em1, quantity=1,
                employee_name="Иванов Алексей Петрович",
                movement_date=_date(14),
                comment="Возврат: остаток после заказа 301",
                created_by_account="skladsik",
                parent_issue=issue1,
            ),
            StockMovement(
                movement_type="restock", tool=tap1, quantity=3,
                employee_name="Сидоров Дмитрий Николаевич",
                movement_date=_date(10),
                comment="Возврат: не использовали",
                created_by_account="skladsik",
                parent_issue=issue2,
            ),
            StockMovement(
                movement_type="restock", tool=dr2, quantity=1,
                employee_name="Петров Сергей Иванович",
                movement_date=_date(5),
                comment="Возврат: 1 шт. целое",
                created_by_account="skladsik",
                parent_issue=issue3,
            ),
        ]
        StockMovement.objects.bulk_create(returns)
        self.stdout.write(f"  Создано {len(returns)} возвратов.")

        # --- СПИСАНИЯ (writeoff) ---
        self.stdout.write("Создаю списания…")
        StockMovement.objects.create(
            movement_type="writeoff", tool=em2, quantity=1,
            employee_name="Сидоров Дмитрий Николаевич",
            movement_date=_date(22),
            comment="Сломана в процессе работы",
            created_by_account="skladsik",
        )
        StockMovement.objects.create(
            movement_type="writeoff", tool=cd1, quantity=2,
            employee_name="",
            movement_date=_date(9),
            comment="Износ, списание по инвентаризации",
            created_by_account="admin",
        )
        self.stdout.write("  Создано 2 списания.")

        # --- ЗАЯВКИ НА ЗАКУПКУ (PurchaseRequest) ---
        self.stdout.write("Создаю заявки на закупку…")
        purchases = [
            PurchaseRequest(
                requested_item="Концевая фреза Ø12 Z4 carbide TiAlN",
                article="IZAR-1234-12",
                quantity=5,
                unit_price="1850.00",
                status="processing",
                request_comment="Срочно — заканчиваются фрезы под алюминий",
                requested_by="Иванов Алексей Петрович",
                status_updated_by="",
            ),
            PurchaseRequest(
                requested_item="Метчик M4×0,7 HSS-Co глухое",
                article="DORMER-M4-B",
                quantity=20,
                unit_price="320.00",
                status="processing",
                request_comment="Обычный запас, расходный материал",
                requested_by="Козлов Виктор Андреевич",
                status_updated_by="",
            ),
            PurchaseRequest(
                requested_item="Сверло Ø8,5 HSS-Co (под M10)",
                article="",
                quantity=10,
                unit_price="185.00",
                status="ordered",
                request_comment="",
                status_comment="Заказано у поставщика 24.04, ожидаем 7-10 дней",
                requested_by="Петров Сергей Иванович",
                status_updated_by="admin",
            ),
            PurchaseRequest(
                requested_item="Зенкер машинный DIN 335 Ø16 90°",
                article="DIN335-16-HSS",
                quantity=3,
                unit_price="740.00",
                status="ordered",
                request_comment="Для финишной обработки фасок",
                status_comment="Заказ оформлен, счёт выставлен",
                requested_by="Иванов Алексей Петрович",
                status_updated_by="admin",
            ),
            PurchaseRequest(
                requested_item="Центровочные свёрла A1 Ø1 мм, уп. 10 шт.",
                article="CDR-A1-HSS-10PK",
                quantity=2,
                unit_price="890.00",
                status="delivered",
                request_comment="",
                status_comment="Получено на склад 02.05, ожидает оприходования",
                requested_by="Фролов Константин Олегович",
                status_updated_by="skladsik",
            ),
            PurchaseRequest(
                requested_item="Метчик M6×1 HSS-Co GÜHRING, 10 шт.",
                article="GH-M6-1.0-10PK",
                quantity=1,
                unit_price="3200.00",
                status="stocked",
                request_comment="Регулярный запас",
                status_comment="Оприходовано 05.04, 10 шт. на складе",
                requested_by="Сидоров Дмитрий Николаевич",
                status_updated_by="admin",
            ),
        ]
        PurchaseRequest.objects.bulk_create(purchases)
        self.stdout.write(f"  Создано {len(purchases)} заявок на закупку.")

        self.stdout.write(self.style.SUCCESS("Тестовые данные успешно созданы."))

    def _create_purchases_if_missing(self):
        if PurchaseRequest.objects.exists():
            self.stdout.write("  Заявки на закупку уже есть — пропускаю.")
            return
        self.stdout.write("Создаю заявки на закупку…")
        purchases = [
            PurchaseRequest(
                requested_item="Концевая фреза Ø12 Z4 carbide TiAlN",
                article="IZAR-1234-12", quantity=5, unit_price="1850.00",
                status="processing",
                request_comment="Срочно — заканчиваются фрезы под алюминий",
                requested_by="Иванов Алексей Петрович", status_updated_by="",
            ),
            PurchaseRequest(
                requested_item="Метчик M4×0,7 HSS-Co глухое",
                article="DORMER-M4-B", quantity=20, unit_price="320.00",
                status="processing",
                request_comment="Обычный запас, расходный материал",
                requested_by="Козлов Виктор Андреевич", status_updated_by="",
            ),
            PurchaseRequest(
                requested_item="Сверло Ø8,5 HSS-Co (под M10)",
                article="", quantity=10, unit_price="185.00",
                status="ordered",
                request_comment="",
                status_comment="Заказано у поставщика, ожидаем 7-10 дней",
                requested_by="Петров Сергей Иванович", status_updated_by="admin",
            ),
            PurchaseRequest(
                requested_item="Зенкер машинный DIN 335 Ø16 90°",
                article="DIN335-16-HSS", quantity=3, unit_price="740.00",
                status="ordered",
                request_comment="Для финишной обработки фасок",
                status_comment="Заказ оформлен, счёт выставлен",
                requested_by="Иванов Алексей Петрович", status_updated_by="admin",
            ),
            PurchaseRequest(
                requested_item="Центровочные свёрла A1 Ø1 мм, уп. 10 шт.",
                article="CDR-A1-HSS-10PK", quantity=2, unit_price="890.00",
                status="delivered",
                request_comment="",
                status_comment="Получено на склад, ожидает оприходования",
                requested_by="Фролов Константин Олегович", status_updated_by="skladsik",
            ),
            PurchaseRequest(
                requested_item="Метчик M6×1 HSS-Co GÜHRING, 10 шт.",
                article="GH-M6-1.0-10PK", quantity=1, unit_price="3200.00",
                status="stocked",
                request_comment="Регулярный запас",
                status_comment="Оприходовано, 10 шт. на складе",
                requested_by="Сидоров Дмитрий Николаевич", status_updated_by="admin",
            ),
        ]
        PurchaseRequest.objects.bulk_create(purchases)
        self.stdout.write(self.style.SUCCESS(f"  Создано {len(purchases)} заявок на закупку."))
