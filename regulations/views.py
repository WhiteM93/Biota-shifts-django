from datetime import date, timedelta

from django.forms import modelformset_factory
from django.shortcuts import redirect, render

from .models import RegulationPlan


def regulation_page(request):
    plan_date = request.GET.get("date") or (date.today() + timedelta(days=1)).isoformat()
    qs = RegulationPlan.objects.filter(plan_date=plan_date).order_by("employee_name")
    PlanFormSet = modelformset_factory(
        RegulationPlan,
        fields=(
            "employee_code",
            "employee_name",
            "department",
            "position",
            "shift",
            "breakfast_start",
            "breakfast_end",
            "lunch_start",
            "lunch_end",
        ),
        extra=0,
    )
    if request.method == "POST":
        formset = PlanFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            return redirect(f"/regulations/?date={plan_date}")
    else:
        formset = PlanFormSet(queryset=qs)
    return render(
        request,
        "regulations/page.html",
        {"formset": formset, "plan_date": plan_date},
    )
