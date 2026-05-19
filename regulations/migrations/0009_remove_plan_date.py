"""
Миграция 0009: убрать plan_date из RegulationPlan.

Шаги:
1. Оставить только строки с plan_date = 2026-04-01 (утверждённый регламент апреля).
   Если апрельских строк нет — оставить самый последний месяц.
2. Удалить старый UniqueConstraint (plan_date, employee_code, shift).
3. Добавить новый UniqueConstraint (employee_code, shift).
4. Удалить поле plan_date.
"""
import datetime

from django.db import migrations, models


def keep_only_april(apps, schema_editor):
    RegulationPlan = apps.get_model("regulations", "RegulationPlan")
    APRIL = datetime.date(2026, 4, 1)

    # Проверяем есть ли апрельские записи
    if RegulationPlan.objects.filter(plan_date=APRIL).exists():
        # Удаляем всё кроме апреля
        RegulationPlan.objects.exclude(plan_date=APRIL).delete()
    else:
        # Апреля нет — берём самый последний месяц
        latest = RegulationPlan.objects.order_by("-plan_date").values_list("plan_date", flat=True).first()
        if latest:
            RegulationPlan.objects.exclude(plan_date=latest).delete()
        # Если записей вообще нет — ничего не делаем


def reverse_keep(apps, schema_editor):
    # Откат невозможен без данных — просто оставляем как есть
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("regulations", "0008_regulationplan_breaks"),
    ]

    operations = [
        # 1. Оставляем только апрельские данные
        migrations.RunPython(keep_only_april, reverse_code=reverse_keep),

        # 2. Удаляем старый уникальный индекс (включал plan_date)
        migrations.RemoveConstraint(
            model_name="regulationplan",
            name="uniq_regulation_employee_day_shift",
        ),

        # 3. Добавляем новый уникальный индекс без даты
        migrations.AddConstraint(
            model_name="regulationplan",
            constraint=models.UniqueConstraint(
                fields=["employee_code", "shift"],
                name="uniq_regulation_employee_shift",
            ),
        ),

        # 4. Удаляем поле plan_date
        migrations.RemoveField(
            model_name="regulationplan",
            name="plan_date",
        ),
    ]
