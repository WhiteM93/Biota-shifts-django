"""Проверка настроек Telegram-уведомлений (токен, chat_id)."""
from django.core.management.base import BaseCommand

from biota_shifts.notification_settings import NOTIFICATION_SETTINGS_PATH, load_notification_settings
from biota_shifts.telegram_notify import (
    fetch_telegram_bot_username,
    resolve_telegram_bot_token,
    resolve_telegram_proxy,
    send_telegram_test,
    telegram_notify_configured,
)


class Command(BaseCommand):
    help = "Показать, видит ли приложение токен и chat_id для сводок СКУД."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send",
            action="store_true",
            help="Отправить тестовое сообщение в Telegram (проверка доставки)",
        )

    def handle(self, *args, **options):
        settings = load_notification_settings()
        token = resolve_telegram_bot_token(settings)
        chats = settings.get("telegram_chat_ids") or []

        self.stdout.write(f"Файл настроек: {NOTIFICATION_SETTINGS_PATH} ({'есть' if NOTIFICATION_SETTINGS_PATH.exists() else 'нет'})")
        proxy = resolve_telegram_proxy()
        if proxy:
            self.stdout.write(f"Прокси: {proxy[:40]}{'…' if len(proxy) > 40 else ''}")
        else:
            self.stdout.write("Прокси: не задан (прямое подключение к api.telegram.org)")

        if token:
            self.stdout.write(f"Токен: задан ({token[:8]}…{token[-4:]}, длина {len(token)})")
            username = fetch_telegram_bot_username(token)
            if username:
                self.stdout.write(f"Бот в Telegram: @{username} — откройте его и нажмите /start")
            else:
                self.stdout.write(self.style.WARNING("Не удалось проверить токен через getMe (сеть или неверный токен)"))
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
            self.stdout.write(self.style.SUCCESS("Поля заполнены (токен + chat_id)."))
        else:
            self.stdout.write(self.style.ERROR("Итог: Telegram НЕ настроен (нужны и токен, и chat_id)."))
            return

        if not options["send"]:
            self.stdout.write("Проверка доставки: python manage.py check_telegram_notify --send")
            return

        try:
            n = send_telegram_test(settings)
            self.stdout.write(self.style.SUCCESS(f"Тестовое сообщение отправлено в {n} чат(ов). Проверьте Telegram."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Ошибка отправки: {exc}"))
