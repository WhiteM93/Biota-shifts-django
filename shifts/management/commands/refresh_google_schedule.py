"""Обновить кэш Google-графика (cron: 21:00 МСК).

Пример crontab на сервере:
0 21 * * * cd /home/admin/Biota-shifts-django && .venv/bin/python manage.py refresh_google_schedule >> /var/log/biota-google-cache.log 2>&1
"""
from django.core.management.base import BaseCommand

from biota_shifts.schedule_google import google_schedule_configured
from biota_shifts.schedule_google_cache import refresh_for_cron


class Command(BaseCommand):
    help = "Загрузить Google-график в локальный кэш (текущий и предыдущий месяц)."

    def handle(self, *args, **options):
        if not google_schedule_configured():
            self.stderr.write("Google не настроен — пропуск.")
            return
        lines = refresh_for_cron()
        for line in lines:
            self.stdout.write(line)
