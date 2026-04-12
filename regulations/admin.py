from django.contrib import admin

from .models import RegulationPlan


@admin.register(RegulationPlan)
class RegulationPlanAdmin(admin.ModelAdmin):
    list_display = (
        "plan_date",
        "employee_code",
        "employee_name",
        "shift",
        "locked",
        "eight_hour_shift",
        "breakfast_start",
        "breakfast_end",
        "lunch_start",
        "lunch_end",
    )
    list_filter = ("plan_date", "shift", "department", "locked", "eight_hour_shift")
    search_fields = ("employee_code", "employee_name")
