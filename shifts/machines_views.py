"""Раздел «Станки» (учёт станков, план на станке)."""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import machines_quick_edit_for_user

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import MachinesBoardState, Product

# Версия «заглушечного» контента с сервера: при изменении дефолтов в коде увеличить,
# чтобы у клиентов сбросился локальный оверлей (localStorage) и подтянулись новые строки.
MACHINES_CONTENT_VERSION = 1

# Заглушка до расширения логики: список станков и строка «график» справа (если в БД нет сохранённой сводки).
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

MAX_MACHINE_ROWS = 60
MAX_SCHEDULE_ROWS = 120


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


def _normalize_machine_rows(raw) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for r in raw[:MAX_MACHINE_ROWS]:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "code": str(r.get("code") or "").strip()[:32],
                "current": str(r.get("current") or "").strip()[:500],
                "next": str(r.get("next") or "").strip()[:500],
                "extra": str(r.get("extra") or "").strip()[:2000],
                "tag": str(r.get("tag") or "").strip()[:64],
            }
        )
    return out


def _normalize_schedule_rows(raw, valid_pids: set[int]) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for r in raw[:MAX_SCHEDULE_ROWS]:
        if not isinstance(r, dict):
            continue
        pid = r.get("product_id")
        try:
            pid = int(pid) if pid not in (None, "") else None
        except (TypeError, ValueError):
            pid = None
        if pid is not None and pid not in valid_pids:
            pid = None
        out.append(
            {
                "label": str(r.get("label") or "").strip()[:500],
                "machine_code": str(r.get("machine_code") or "").strip()[:32],
                "product_id": pid,
            }
        )
    return out


def _board_payload_from_db() -> dict | None:
    row = MachinesBoardState.objects.filter(pk=1).first()
    if not row:
        return None
    p = row.payload
    if not isinstance(p, dict) or not p:
        return None
    return p


def _machines_post_save(request):
    u = biota_user(request)
    if not machines_quick_edit_for_user(u):
        return JsonResponse({"ok": False, "error": "Нет права на быстрое редактирование «Станки»."}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)
    if (body.get("action") or "").strip() != "save_machines_board":
        return JsonResponse({"ok": False, "error": "Неизвестное действие."}, status=400)
    valid_pids = set(Product.objects.values_list("id", flat=True))
    mrows = _normalize_machine_rows(body.get("machine_rows"))
    srows = _normalize_schedule_rows(body.get("schedule_rows"), valid_pids)
    if not mrows:
        return JsonResponse({"ok": False, "error": "Нужна хотя бы одна строка станка."}, status=400)
    if not srows:
        return JsonResponse({"ok": False, "error": "Нужна хотя бы одна строка плана."}, status=400)
    cv = body.get("content_version")
    try:
        cv = int(cv) if cv is not None and str(cv).strip() != "" else None
    except (TypeError, ValueError):
        cv = None
    payload = {
        "machine_rows": mrows,
        "schedule_rows": srows,
        "content_version": cv,
    }
    MachinesBoardState.objects.update_or_create(pk=1, defaults={"payload": payload})
    return JsonResponse({"ok": True})


@ensure_csrf_cookie
@biota_login_required
@nav_permission_required("machines")
@write_permission_required
@require_http_methods(["GET", "HEAD", "POST"])
def machines_view(request):
    product_options = list(Product.objects.order_by("name").values("id", "name"))
    product_by_id = {p["id"]: p["name"] for p in product_options}
    valid_pids = set(product_by_id.keys())

    machine_rows = list(_DEFAULT_MACHINE_ROWS)
    schedule_seed = list(_DEFAULT_SCHEDULE_ROWS)
    machines_board_has_server = False

    board_payload = _board_payload_from_db()
    if board_payload:
        mr = _normalize_machine_rows(board_payload.get("machine_rows"))
        sr = _normalize_schedule_rows(board_payload.get("schedule_rows"), valid_pids)
        if mr and sr:
            machine_rows = mr
            schedule_seed = sr
            machines_board_has_server = True

    schedule_rows = _schedule_rows_with_display(schedule_seed, product_by_id)

    if request.method == "POST":
        if (request.headers.get("X-Requested-With") or "").strip() != "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Ожидается AJAX."}, status=400)
        return _machines_post_save(request)

    return render(
        request,
        "shifts/machines.html",
        {
            "username": biota_user(request),
            "machines_content_version": MACHINES_CONTENT_VERSION,
            "machines_board_has_server": machines_board_has_server,
            "machine_rows": machine_rows,
            "schedule_rows": schedule_rows,
            "product_options": product_options,
            "machines_products_json": [{"id": p["id"], "name": p["name"]} for p in product_options],
        },
    )
