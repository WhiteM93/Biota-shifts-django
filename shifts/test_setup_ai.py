from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from shifts.gpt_rate_limit import gpt_rate_limit_allow
from shifts.setup_ai import build_setup_analysis_prompt
from shifts.setup_stock_match import SetupStockRowResult
from shifts.yandex_gpt import yandex_gpt_model_uri


class YandexGptModelUriTests(SimpleTestCase):
    @override_settings(YANDEX_GPT_FOLDER_ID="b1gtest", YANDEX_GPT_MODEL="yandexgpt-5-lite")
    def test_new_lite_no_latest_suffix(self):
        self.assertEqual(yandex_gpt_model_uri(), "gpt://b1gtest/yandexgpt-5-lite")

    @override_settings(YANDEX_GPT_FOLDER_ID="b1gtest", YANDEX_GPT_MODEL="yandexgpt-5.1")
    def test_pro_51(self):
        self.assertEqual(yandex_gpt_model_uri(), "gpt://b1gtest/yandexgpt-5.1")

    @override_settings(YANDEX_GPT_FOLDER_ID="b1gtest", YANDEX_GPT_MODEL="yandexgpt-lite")
    def test_legacy_adds_latest(self):
        self.assertEqual(yandex_gpt_model_uri(), "gpt://b1gtest/yandexgpt-lite/latest")


class GptRateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_admin_unlimited(self):
        self.assertTrue(gpt_rate_limit_allow("admin", scope="t", cooldown_sec=60)[0])
        self.assertTrue(gpt_rate_limit_allow("admin", scope="t", cooldown_sec=60)[0])

    def test_user_once_per_minute(self):
        ok1, _ = gpt_rate_limit_allow("worker1", scope="setup_ai", cooldown_sec=60)
        ok2, retry = gpt_rate_limit_allow("worker1", scope="setup_ai", cooldown_sec=60)
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertGreater(retry, 0)

        ok_chat, _ = gpt_rate_limit_allow("worker1", scope="inv_chat", cooldown_sec=60)
        ok_chat2, _ = gpt_rate_limit_allow("worker1", scope="inv_chat", cooldown_sec=60)
        self.assertTrue(ok_chat)
        self.assertFalse(ok_chat2)


class SetupAiPromptTests(SimpleTestCase):
    def test_prompt_contains_row_status(self):
        class P:
            pk = 1
            name = "Деталь"

        class S:
            pk = 2
            name = "Уст.1"
            workpiece = "плита"
            material = "Д16Т"
            size = "100x50"
            binding_x = "0"
            binding_y = "0"
            binding_z = "0"
            gcode_system = "G54"
            setup_notes = "зажать в тисках"

        row = SetupStockRowResult(
            row_id=1,
            tool_number="1",
            tool_type="Метчик",
            diameter="M3",
            overhang="",
            tap_hole_type="Сквозной",
            note="",
            status="empty",
            status_label="На складе не найдено",
            total_qty=0,
        )
        from shifts.setup_stock_match import OpenHolder

        row.open_holders = [
            OpenHolder(
                issue_id=1,
                employee="Сидоров",
                remaining=1,
                movement_date="2026-09-20",
                tool_label="Метчик M3",
            )
        ]
        text = build_setup_analysis_prompt(product=P(), setup=S(), match_rows=[row])
        self.assertIn("Метчик", text)
        self.assertIn("На складе не найдено", text)
        self.assertIn("зажать в тисках", text)
        self.assertIn("Сидоров", text)
        self.assertIn("на руках", text)
