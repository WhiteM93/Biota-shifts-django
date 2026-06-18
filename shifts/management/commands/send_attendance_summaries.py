"""Отправка сводок по СКУД (cron, МСК).

Пример crontab:
20 8 * * *  cd /path/to/Biota-shifts-django && .venv/bin/python manage.py send_attendance_summaries --slot=morning >> /var/log/biota-notify.log 2>&1
20 20 * * * cd /path/to/Biota-shifts-django && .venv/bin/python manage.py send_attendance_summaries --slot=evening >> /var/log/biota-notify.log 2>&1
"""
from django.core.management.base import BaseCommand

from biota_shifts.attendance_summary import (
    SLOT_EVENING,
    SLOT_MORNING,
    format_summary_text,
    load_attendance_summary_from_db,
    send_summary_telegram,
)
from biota_shifts.notification_settings import load_notification_settings, telegram_token_configured
from biota_shifts.notify_relay import notify_delivery_configured, notify_relay_configured


class Command(BaseCommand):
    help = "Сводка: кто по графику не отметился в СКУД (утро 08:20 / вечер 20:20)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slot",
            choices=[SLOT_MORNING, SLOT_EVENING],
            required=True,
            help="morning — дневная смена; evening — ночная",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только вывести текст сводки, без отправки",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Отправить даже если уведомления выключены",
        )

    def handle(self, *args, **options):
        slot = options["slot"]
        settings = load_notification_settings()

        if not settings.get("enabled") and not options["force"]:
            self.stdout.write("Уведомления выключены (enabled=false). Используйте --force для теста.")
            return

        if slot == SLOT_MORNING and not settings.get("morning_enabled") and not options["force"]:
            self.stdout.write("Утренняя сводка выключена.")
            return
        if slot == SLOT_EVENING and not settings.get("evening_enabled") and not options["force"]:
            self.stdout.write("Вечерняя сводка выключена.")
            return

        if not notify_delivery_configured(settings) and not options["dry_run"]:
            from biota_shifts.notify_relay import resolve_notify_relay_url
            from biota_shifts.telegram_notify import resolve_telegram_bot_token

            parts = []
            if not resolve_notify_relay_url(settings):
                parts.append("URL сервера бота (BIOTA_NOTIFY_RELAY_URL)")
            if not resolve_telegram_bot_token(settings):
                parts.append("токен Telegram (если без relay)")
            chats = settings.get("telegram_chat_ids") or []
            if not chats and not resolve_notify_relay_url(settings):
                parts.append("chat_id")
            self.stderr.write("Доставка не настроена. Нужен хотя бы relay URL или пара токен + chat_id.")
            if parts:
                self.stderr.write("Не хватает: " + ", ".join(parts) + ".")
            self.stderr.write("Диагностика: python manage.py check_telegram_notify")
            return

        summary = load_attendance_summary_from_db(slot)
        text = format_summary_text(summary)
        self.stdout.write(text)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry-run: уведомление не отправлено"))
            return

        if notify_relay_configured(settings):
            n = send_summary_telegram(summary, settings)
            self.stdout.write(self.style.SUCCESS(f"Сводка отправлена на сервер бота"))
            return

        if not telegram_token_configured(settings):
            self.stderr.write("Не задан токен Telegram-бота.")
            return

        n = send_summary_telegram(summary, settings)
        self.stdout.write(self.style.SUCCESS(f"Отправлено в {n} чат(ов) Telegram"))
