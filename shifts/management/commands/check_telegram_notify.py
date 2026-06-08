"""Проверка настроек Telegram-уведомлений (токен, chat_id)."""
from django.core.management.base import BaseCommand

from biota_shifts.notification_settings import NOTIFICATION_SETTINGS_PATH, load_notification_settings
from biota_shifts.telegram_notify import resolve_telegram_bot_token, telegram_notify_configured


class Command(BaseCommand):
    help = "Показать, видит ли приложение токен и chat_id для сводок СКУД."

    def handle(self, *args, **options):
        settings = load_notification_settings()
        token = resolve_telegram_bot_token(settings)
        chats = settings.get("telegram_chat_ids") or []

        self.stdout.write(f"Файл настроек: {NOTIFICATION_SETTINGS_PATH} ({'есть' if NOTIFICATION_SETTINGS_PATH.exists() else 'нет'})")
        if token:
            self.stdout.write(f"Токен: задан ({token[:8]}…{token[-4:]}, длина {len(token)})")
        else:
            self.stdout.write(self.style.ERROR("Токен: НЕ задан"))
            self.stdout.write("  → .env.secrets: BIOTA_TELEGRAM_BOT_TOKEN=… или BOT_TOKEN=…")

        if chats:
            self.stdout.write(f"Chat ID ({len(chats)}): {', '.join(str(c) for c in chats)}")
        else:
            self.stdout.write(self.style.ERROR("Chat ID: не заданы"))
            self.stdout.write("  → кабинет /cabinet/notifications/ или .biota_notification_settings.json")
            self.stdout.write("  → или .env.secrets: BIOTA_TELEGRAM_CHAT_IDS=577292537")

        if telegram_notify_configured(settings):
            self.stdout.write(self.style.SUCCESS("Итог: Telegram настроен, можно отправлять сводки."))
        else:
            self.stdout.write(self.style.ERROR("Итог: Telegram НЕ настроен (нужны и токен, и chat_id)."))
