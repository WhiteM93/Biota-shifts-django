from django.db import models


class RegulationPlan(models.Model):
    SHIFT_CHOICES = (("д", "Дневная"), ("н", "Ночная"))

    plan_date = models.DateField()
    employee_code = models.CharField(max_length=64, db_index=True)
    employee_name = models.CharField(max_length=255)
    department = models.CharField(max_length=255, blank=True, default="")
    position = models.CharField(max_length=255, blank=True, default="")
    shift = models.CharField(max_length=1, choices=SHIFT_CHOICES, default="д")
    breakfast_start = models.TimeField()
    breakfast_end = models.TimeField()
    lunch_start = models.TimeField()
    lunch_end = models.TimeField()
    locked = models.BooleanField(
        default=False,
        help_text="Закрепить строку: нельзя случайно сдвинуть время на шкале.",
    )
    eight_hour_shift = models.BooleanField(
        default=False,
        help_text="8-часовая смена: один перерыв на питание вместо двух.",
    )

    class Meta:
        ordering = ["employee_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan_date", "employee_code", "shift"],
                name="uniq_regulation_employee_day_shift",
            )
        ]

    def __str__(self) -> str:
        return f"{self.plan_date} | {self.employee_name} ({self.employee_code})"
