"""Раздел «Станки» (учёт станков, план на станке)."""
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required
from .models import Product

# Заглушка до модели БД: список станков и строка «график» справа.
_DEFAULT_MACHINE_ROWS = [
    {
        "code": "F-05",
        "current": "Изделие которое сейчас стоит",
        "next": "следующее в план",
        "extra": "",
        "tag": "GG",
    },
    {
        "code": "F-10",
        "current": "",
        "next": "",
        "extra": "",
        "tag": "",
    },
]

_DEFAULT_SCHEDULE_ROWS = [
    {"label": "График по станку", "machine_code": "F-10", "product_id": None},
    {"label": "", "machine_code": "F-05", "product_id": None},
]


def _schedule_rows_with_display(rows: list[dict], product_by_id: dict[int, str]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        pid = r.get("product_id")
        if pid is not None and pid in product_by_id:
            display = product_by_id[pid]
        else:
            display = (r.get("label") or "").strip()
        out.append({**r, "product_id": "" if pid is None else pid, "display": display})
    return out


@biota_login_required
@nav_permission_required("machines")
@require_http_methods(["GET", "HEAD"])
def machines_view(request):
    product_options = list(Product.objects.order_by("name").values("id", "name"))
    product_by_id = {p["id"]: p["name"] for p in product_options}
    schedule_rows = _schedule_rows_with_display(_DEFAULT_SCHEDULE_ROWS, product_by_id)
    return render(
        request,
        "shifts/machines.html",
        {
            "username": biota_user(request),
            "machine_rows": _DEFAULT_MACHINE_ROWS,
            "schedule_rows": schedule_rows,
            "product_options": product_options,
            # Для поиска по списку изделий в плане (без дублирования тысяч <option> в DOM)
            "machines_products_json": [{"id": p["id"], "name": p["name"]} for p in product_options],
        },
    )
