"""Проверка настроек уведомлений (relay / Telegram)."""
from django.core.management.base import BaseCommand

from biota_shifts.notification_settings import NOTIFICATION_SETTINGS_PATH, load_notification_settings
from biota_shifts.notify_relay import (
    notify_delivery_configured,
    notify_relay_configured,
    resolve_notify_relay_secret,
    resolve_notify_relay_url,
    send_notify_test,
)
from biota_shifts.telegram_notify import (
    fetch_telegram_bot_username,
    resolve_telegram_bot_token,
    resolve_telegram_proxy,
    telegram_notify_configured,
)


class Command(BaseCommand):
    help = "Показать настройки доставки сводок СКУД (сервер бота или Telegram)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send",
            action="store_true",
            help="Отправить тестовое сообщение (через relay или Telegram)",
        )

    def handle(self, *args, **options):
        settings = load_notification_settings()
        token = resolve_telegram_bot_token(settings)
        chats = settings.get("telegram_chat_ids") or []
        relay_url = resolve_notify_relay_url(settings)

        self.stdout.write(f"Файл настроек: {NOTIFICATION_SETTINGS_PATH} ({'есть' if NOTIFICATION_SETTINGS_PATH.exists() else 'нет'})")

        if relay_url:
            self.stdout.write(self.style.SUCCESS(f"Relay URL: {relay_url}"))
            secret = resolve_notify_relay_secret(settings)
            self.stdout.write(f"Relay secret: {'задан' if secret else 'не задан'}")
            self.stdout.write("Режим: Biota → сервер бота → Telegram")
        else:
            self.stdout.write("Relay URL: не задан (прямая отправка в Telegram из Biota)")

        proxy = resolve_telegram_proxy()
        if proxy:
            self.stdout.write(f"Прокси Telegram: {proxy[:40]}{'…' if len(proxy) > 40 else ''}")
        elif not relay_url:
            self.stdout.write("Прокси: не задан (прямое подключение к api.telegram.org)")

        if token:
            self.stdout.write(f"Токен Telegram: задан ({token[:8]}…{token[-4:]})")
            if not relay_url:
                username = fetch_telegram_bot_username(token)
                if username:
                    self.stdout.write(f"Бот: @{username}")
        elif not relay_url:
            self.stdout.write(self.style.WARNING("Токен Telegram: не задан"))

        if chats:
            self.stdout.write(f"Chat ID ({len(chats)}): {', '.join(str(c) for c in chats)}")
        elif not relay_url:
            self.stdout.write(self.style.WARNING("Chat ID: не заданы"))

        if notify_delivery_configured(settings):
            if notify_relay_configured(settings):
                self.stdout.write(self.style.SUCCESS("Итог: доставка через сервер бота настроена."))
            elif telegram_notify_configured(settings):
                self.stdout.write(self.style.SUCCESS("Итог: прямая доставка в Telegram настроена."))
        else:
            self.stdout.write(self.style.ERROR("Итог: доставка НЕ настроена."))
            self.stdout.write("  → BIOTA_NOTIFY_RELAY_URL=… (сервер бота)")
            self.stdout.write("  → или BIOTA_TELEGRAM_BOT_TOKEN + chat_id")
            return

        if not options["send"]:
            self.stdout.write("Проверка доставки: python manage.py check_telegram_notify --send")
            return

        try:
            n = send_notify_test(settings)
            if notify_relay_configured(settings):
                self.stdout.write(self.style.SUCCESS("Тест отправлен на сервер бота. Проверьте Telegram."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Тестовое сообщение отправлено в {n} чат(ов). Проверьте Telegram."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Ошибка отправки: {exc}"))
