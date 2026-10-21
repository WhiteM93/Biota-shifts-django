"""Тесты склада: пластинки, приход, отображение."""
from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from shifts.insert_constants import insert_search_tokens, normalize_insert_machining_apps
from shifts.inventory_views import _arrival_bulk_row_validation_errors, _insert_spec_fields_from_mapping
from shifts.models import (
    DrillSpec,
    EndMillSpec,
    FastenerSpec,
    FastenerType,
    InsertSpec,
    StockMovement,
    ToolItem,
)


class InsertSearchTokensTests(TestCase):
    def test_formfactor_mb07_finds_catalog_code(self):
        tokens = insert_search_tokens("MB‑07‑T3")
        self.assertIn("MB07", tokens)
        self.assertTrue(any(t.startswith("MB-07") or t.startswith("MB‑07") or "MB07" in t for t in tokens))

    def test_catalog_name_contains_family_core(self):
        tokens = insert_search_tokens("MB-07-T3")
        name = "3MB07GR200-4.5-D17 M30"
        self.assertTrue(any(tok in name.upper().replace(" ", "") or tok in name.upper() for tok in tokens))

    def test_plain_iso_still_works(self):
        tokens = insert_search_tokens("CNMG120408")
        self.assertIn("CNMG120408", tokens)


class InsertMachiningAppsTests(TestCase):
    def test_multi_apps(self):
        self.assertEqual(normalize_insert_machining_apps("3,1,2"), "1,2,3")

    def test_insert_spec_save(self):
        tool = ToolItem.objects.create(
            category="insert",
            name="ins",
            tool_material="carbide",
            quantity=2,
        )
        spec = InsertSpec(
            tool=tool,
            insert_shape="C",
            relief_angle="N",
            tolerance_class="M",
            mounting_chip="G",
            cutting_edge_length_code="12",
            thickness_code="04",
            nose_radius_code="08",
            machining_application="1,3",
        )
        spec.save()
        spec.refresh_from_db()
        self.assertEqual(spec.machining_application, "1,3")


class ArrivalBulkValidationTests(TestCase):
    def test_insert_requires_name(self):
        row = {"category": "insert", "ins_brand": "Sandvik", "ins_name": ""}
        errs = _arrival_bulk_row_validation_errors(row, 1)
        self.assertTrue(any("наименование" in e.lower() for e in errs))

    def test_insert_ok_with_name_and_brand(self):
        row = {
            "category": "insert",
            "ins_brand": "Sandvik",
            "ins_name": "CNMG120408",
            "coating_type": "yellow",
        }
        errs = _arrival_bulk_row_validation_errors(row, 1)
        self.assertEqual(errs, [])

    def test_end_mill_requires_diameter(self):
        row = {"category": "end_mill", "em_diameter_mm": ""}
        errs = _arrival_bulk_row_validation_errors(row, 1)
        self.assertTrue(any("диаметр" in e.lower() for e in errs))

    def test_insert_spec_mapping_simple(self):
        fields = _insert_spec_fields_from_mapping(
            {
                "ins_brand": "Sandvik",
                "ins_name": "CNMG120408",
                "ins_kind": "milling",
                "ins_edge_code": "12",
                "ins_thread_size": "16",
            }
        )
        self.assertEqual(fields["insert_kind"], "other")
        self.assertEqual(fields["brand"], "SANDVIK")
        self.assertEqual(fields["item_name"], "CNMG120408")
        self.assertEqual(fields["cutting_edge_length_code"], "")
        self.assertEqual(fields["thread_size"], "")
        self.assertEqual(fields["custom_type"], "")
        self.assertEqual(fields["chipbreaker_grade"], "")


class InventoryViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()

    def _create_minimal_per_category(self):
        d = Decimal("6")
        em = ToolItem.objects.create(
            category="end_mill",
            name="Фреза тест",
            tool_material="carbide",
            quantity=5,
        )
        EndMillSpec.objects.create(
            tool=em,
            mill_type="end",
            diameter_mm=d,
            overall_length_mm=Decimal("50"),
            cutting_length_mm=Decimal("20"),
            flutes_count=4,
        )
        ins_tool = ToolItem.objects.create(
            category="insert",
            name="CNMG120408 Sandvik",
            tool_material="",
            quantity=3,
        )
        InsertSpec.objects.create(
            tool=ins_tool,
            insert_kind="other",
            brand="Sandvik",
            item_name="CNMG120408",
        )

    def test_stock_page_loads(self):
        self._create_minimal_per_category()
        for cat in ("end_mill", "insert", "drill"):
            url = reverse("inventory") + f"?panel=stock&category={cat}"
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, msg=f"category={cat}")
            content = resp.content.decode("utf-8", errors="replace")
            self.assertIn("inv-page--stock", content)
            if cat == "end_mill":
                self.assertIn("Ø6", content)
            if cat == "insert":
                self.assertIn("CNMG120408", content)
                self.assertIn("sandvik", content.casefold())

    def test_stock_row_shows_who_added(self):
        tool = ToolItem.objects.create(
            category="drill",
            name="Сверло автор",
            tool_material="carbide",
            quantity=3,
        )
        DrillSpec.objects.create(tool=tool, diameter_mm=Decimal("5"))
        StockMovement.objects.create(
            movement_type="restock",
            tool=tool,
            quantity=3,
            movement_date=date.today(),
            created_by_account="admin",
            comment="приход",
        )
        resp = self.client.get(reverse("inventory") + "?panel=stock&category=drill")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", errors="replace")
        self.assertIn("inv-stock-added-tip", html)
        self.assertIn("Добавил на склад:", html)
        self.assertIn("inv-stock-row-actions", html)

    def test_arrival_page_has_inv_options(self):
        resp = self.client.get(reverse("inventory") + "?panel=arrival")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("insert_chipbreaker_grades", resp.content.decode("utf-8", errors="replace"))
        self.assertNotIn("work_material_types", resp.content.decode("utf-8", errors="replace"))

    def test_history_filters_by_movement_type(self):
        tool = ToolItem.objects.create(category="drill", name="d-hist", quantity=10)
        today = date.today()
        StockMovement.objects.create(
            movement_type="restock", tool=tool, quantity=5, movement_date=today, created_by_account="admin"
        )
        StockMovement.objects.create(
            movement_type="issue", tool=tool, quantity=2, movement_date=today, created_by_account="admin"
        )
        StockMovement.objects.create(
            movement_type="writeoff", tool=tool, quantity=1, movement_date=today, created_by_account="admin"
        )
        base = reverse("inventory") + "?panel=history"
        all_resp = self.client.get(base)
        self.assertEqual(all_resp.status_code, 200)
        all_html = all_resp.content.decode("utf-8", errors="replace")
        self.assertIn("Пополнение", all_html)
        self.assertIn("Выдача", all_html)
        self.assertIn("Списание", all_html)

        issue_resp = self.client.get(base + "&history_movement_type=issue")
        issue_html = issue_resp.content.decode("utf-8", errors="replace")
        self.assertIn("Выдача", issue_html)
        self.assertNotIn("inv-history-card--restock", issue_html)
        self.assertNotIn("inv-history-card--writeoff", issue_html)
        self.assertIn("inv-hist-list", all_html)
        self.assertIn("Сегодня", all_html)

    def test_fastener_stock_filter_by_size(self):
        fast_m6 = ToolItem.objects.create(
            category="fast_screw",
            name="Винт ISO 10642 M6x16",
            quantity=120,
            notes="Для наладки",
        )
        FastenerSpec.objects.create(
            tool=fast_m6,
            fastener_type=FastenerType.objects.get(code="iso10642"),
            thread_diameter_mm=Decimal("6"),
            length_mm=16,
            strength_class="8.8",
            material="Сталь",
            coating="Цинк",
        )
        fast_m8 = ToolItem.objects.create(
            category="fast_screw",
            name="Винт ISO 4762 M8x20",
            quantity=70,
        )
        FastenerSpec.objects.create(
            tool=fast_m8,
            fastener_type=FastenerType.objects.get(code="iso4762"),
            thread_diameter_mm=Decimal("8"),
            length_mm=20,
            strength_class="10.9",
            material="Сталь",
            coating="Оксид",
        )

        by_exact = self.client.get(
            reverse("inventory") + "?panel=stock&category=fast_screw&fast_thread_mm=6&fast_length_mm=16"
        )
        self.assertEqual(by_exact.status_code, 200)
        exact_html = by_exact.content.decode("utf-8", errors="replace")
        self.assertIn("M6x16", exact_html)
        self.assertNotIn("M8x20", exact_html)
        self.assertNotIn('name="fast_size"', exact_html)

        by_thread = self.client.get(
            reverse("inventory") + "?panel=stock&category=fast_screw&fast_thread_mm=6"
        )
        self.assertEqual(by_thread.status_code, 200)
        thread_html = by_thread.content.decode("utf-8", errors="replace")
        self.assertIn("M6x16", thread_html)
        self.assertNotIn("M8x20", thread_html)

        screw = FastenerType.objects.get(code="iso10642")
        by_type = self.client.get(
            reverse("inventory")
            + f"?panel=stock&category=fast_screw&fast_type={screw.id}&fast_thread_mm=6&fast_length_mm=16"
        )
        type_html = by_type.content.decode("utf-8", errors="replace")
        self.assertIn(f'data-tool-id="{fast_m6.id}"', type_html)
        self.assertNotIn(f'data-tool-id="{fast_m8.id}"', type_html)
        self.assertIn("Винт с потайной головкой", type_html)

    def test_fastener_subcategories_are_separate_categories(self):
        def mk(cat, code, thread, length):
            tool = ToolItem.objects.create(category=cat, name=f"{code} M{thread}", quantity=10)
            FastenerSpec.objects.create(
                tool=tool,
                fastener_type=FastenerType.objects.get(code=code),
                thread_diameter_mm=Decimal(thread),
                length_mm=length,
            )
            return tool

        screw = mk("fast_screw", "iso4762", "6", 16)
        nut = mk("fast_nut", "iso4032", "6", None)
        washer = mk("fast_washer", "iso7089", "6", None)
        nuts_html = self.client.get(
            reverse("inventory") + "?panel=stock&category=fast_nut&fast_thread_mm=6"
        ).content.decode("utf-8", errors="replace")
        self.assertIn(f'data-tool-id="{nut.id}"', nuts_html)
        self.assertNotIn(f'data-tool-id="{screw.id}"', nuts_html)
        self.assertNotIn(f'data-tool-id="{washer.id}"', nuts_html)
        self.assertNotIn('name="fast_length_mm"', nuts_html)
        self.assertIn("Гайка шестигранная (ISO 4032)", nuts_html)
        self.assertNotIn("Шайба плоская", nuts_html.split('name="fast_type"', 1)[1].split("</select>", 1)[0])

    def test_issue_panel_contains_fastener_filter_metrics(self):
        fast = ToolItem.objects.create(
            category="fast_screw",
            name="Винт ISO 4762 M10x30",
            quantity=24,
            notes="Пробная партия",
        )
        FastenerSpec.objects.create(
            tool=fast,
            fastener_type=FastenerType.objects.get(code="iso4762"),
            thread_diameter_mm=Decimal("10"),
            length_mm=30,
            strength_class="10.9",
            material="Нерж.",
            coating="Без покрытия",
        )
        resp = self.client.get(reverse("inventory") + "?panel=issue")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-cat="fast_screw fast_bolt fast_nut fast_washer"', html)
        self.assertIn('data-f-fast_size="M10x30"', html)
        self.assertIn('data-f-fast_thread="10"', html)
        self.assertIn('data-f-fast_group="Винты"', html)


class HistoryDayGroupTests(TestCase):
    def test_groups_today_and_kind_labels(self):
        import os

        os.environ["BIOTA_INVENTORY_NOTIFY"] = "0"
        from shifts.inventory_views import _history_day_groups

        tool = ToolItem.objects.create(category="drill", name="d-day", quantity=10)
        m = StockMovement.objects.create(
            movement_type="issue",
            tool=tool,
            quantity=2,
            employee_name="Иванов",
            movement_date=date.today(),
        )
        groups = _history_day_groups(
            [
                {
                    "kind": "movement",
                    "ts": m.created_at,
                    "tid": m.id,
                    "movement": m,
                    "show_rollback": False,
                    "account_label": "",
                }
            ]
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["label"], "Сегодня")
        self.assertEqual(groups[0]["rows"][0]["kind_label"], "Выдача")
        self.assertEqual(groups[0]["rows"][0]["who"], "Иванов")
        self.assertEqual(groups[0]["rows"][0]["issued_by"], "")

        groups2 = _history_day_groups(
            [
                {
                    "kind": "movement",
                    "ts": m.created_at,
                    "tid": m.id,
                    "movement": m,
                    "show_rollback": False,
                    "account_label": "Админ",
                }
            ]
        )
        self.assertEqual(groups2[0]["rows"][0]["who"], "Иванов")
        self.assertEqual(groups2[0]["rows"][0]["issued_by"], "Админ")

    def test_edit_event_shows_short_kind_and_address(self):
        from shifts.inventory_views import _history_day_groups
        from shifts.models import InventoryStockEvent

        tool = ToolItem.objects.create(category="center_drill", name="ТЕСТ центровка #03", quantity=1)
        event = InventoryStockEvent.objects.create(
            actor_username="admin",
            event_type=InventoryStockEvent.EVENT_TOOL_EDIT,
            tool=tool,
            summary="edit",
            details={"field": "warehouse_address", "value": "A-01-01"},
        )
        groups = _history_day_groups(
            [
                {
                    "kind": "event",
                    "ts": event.created_at,
                    "tid": event.id,
                    "event": event,
                    "event_title": tool.name,
                    "event_subtitle": "Центровки",
                    "event_note": "Адрес: A-01-01",
                    "actor_label": "admin",
                }
            ]
        )
        row = groups[0]["rows"][0]
        self.assertEqual(row["kind_label"], "Правка")
        self.assertEqual(row["kind_label_full"], "Редактирование позиции")
        self.assertEqual(row["line_note"], "Адрес: A-01-01")
        self.assertFalse(row["has_more"])


class FastenerTopCategoryTests(TestCase):
    def test_fasteners_is_own_top_level_group(self):
        from shifts.models import stock_category_grouped_choices

        groups = {code: (title, items) for code, title, items in stock_category_grouped_choices()}
        self.assertFalse([k for k, _ in groups["tooling"][1] if k.startswith("fast")])
        title, items = groups["fasteners"]
        self.assertEqual(title, "Метизы")
        self.assertEqual(
            items,
            [("fast_screw", "Винты"), ("fast_bolt", "Болты"), ("fast_nut", "Гайки"), ("fast_washer", "Шайбы")],
        )

    def test_inventory_dropdown_has_metizy_optgroup(self):
        from shifts.models import stock_category_grouped_choices
        from django.template.loader import render_to_string

        html = render_to_string(
            "shifts/includes/stock_category_optgroups.html",
            {"stock_category_groups": stock_category_grouped_choices(), "selected_category": ""},
        )
        self.assertIn('<optgroup label="Метизы">', html)
        tooling = html.split('<optgroup label="Оснастка">', 1)[1].split("</optgroup>", 1)[0]
        self.assertNotIn('value="fast_', tooling)
        metizy = html.split('<optgroup label="Метизы">', 1)[1].split("</optgroup>", 1)[0]
        for key, label in (("fast_screw", "Винты"), ("fast_bolt", "Болты"), ("fast_nut", "Гайки"), ("fast_washer", "Шайбы")):
            self.assertIn(f'value="{key}"', metizy)
            self.assertIn(label, metizy)