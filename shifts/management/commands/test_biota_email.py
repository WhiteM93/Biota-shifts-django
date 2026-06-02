"""Проверка отправки почты (SMTP / console)."""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from shifts.email_verification import email_uses_console_backend


class Command(BaseCommand):
    help = "Отправить тестовое письмо и показать текущие настройки EMAIL_*"

    def add_arguments(self, parser):
        parser.add_argument("to", nargs="?", help="Адрес получателя")

    def handle(self, *args, **options):
        to = (options.get("to") or "").strip()
        if not to:
            raise CommandError("Укажите адрес: python manage.py test_biota_email user@example.com")

        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"EMAIL_BACKEND = {backend}")
        if email_uses_console_backend():
            self.stdout.write(
                self.style.WARNING(
                    "Используется console — письмо появится в stdout процесса Django, не в почтовом ящике."
                )
            )
        else:
            self.stdout.write(f"EMAIL_HOST = {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
            self.stdout.write(f"EMAIL_HOST_USER = {settings.EMAIL_HOST_USER or '(пусто)'}")
            self.stdout.write(f"DEFAULT_FROM_EMAIL = {settings.DEFAULT_FROM_EMAIL}")

        send_mail(
            "Biota — тест почты",
            "Если вы видите это письмо, SMTP настроен верно.",
            settings.DEFAULT_FROM_EMAIL,
            [to],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Отправлено на {to}"))
