"""Раздел «Станки» (учёт станков, план на станке)."""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import machines_quick_edit_for_user

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import MachinesBoardState, Product, ProductSetup

# Версия «заглушечного» контента с сервера: при изменении дефолтов в коде увеличить,
# чтобы у клиентов сбросился локальный оверлей (localStorage) и подтянулись новые строки.
MACHINES_CONTENT_VERSION = 5

# Заглушка до расширения логики: список станков и строка «график» справа (если в БД нет сохранённой сводки).
# PK-заглушка для шаблона URL карточки наладки в JS (подменяется на реальный id).
_MACHINES_DETAIL_URL_SENTINEL = 888_888_888

_DEFAULT_MACHINE_ROWS = [
    {
        "code": "F-05",
        "current": "Изделие которое сейчас стоит",
        "next": "следующее в план",
        "extra": "",
        "tag": "Т",
        "current_product_id": None,
        "next_product_id": None,
    },
    {
        "code": "F-10",
        "current": "",
        "next": "",
        "extra": "",
        "tag": "Т",
        "current_product_id": None,
        "next_product_id": None,
    },
]

_DEFAULT_SCHEDULE_ROWS = [
    {"label": "График по станку", "machine_code": "F-10", "product_id": None, "setup_id": None, "qty": "", "priority": "", "color": ""},
    {"label": "", "machine_code": "F-05", "product_id": None, "setup_id": None, "qty": "", "priority": "", "color": ""},
]

MAX_MACHINE_ROWS = 60
MAX_SCHEDULE_ROWS = 120


def _quick_field_label_parts(label: str) -> tuple[str, str]:
    """Две части подписи «сейчас/далее»: до первого « - » и после (как в списке изделий)."""
    s = " ".join((label or "").split())
    sep = " - "
    if sep not in s:
        return s, ""
    a, _, b = s.partition(sep)
    return a.strip(), b.strip()


def _machine_rows_with_label_parts(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        cs, ct = _quick_field_label_parts(str(d.get("current") or ""))
        ns, nt = _quick_field_label_parts(str(d.get("next") or ""))
        d["current_sku"], d["current_title"] = cs, ct
        d["next_sku"], d["next_title"] = ns, nt
        out.append(d)
    return out


def _norm_machine_code_key(code: str) -> str:
    return " ".join((code or "").split()).strip().upper()


def _schedule_setup_lines_by_machine_product(schedule_rows: list[dict]) -> dict[tuple[str, int], str]:
    """Строка установки из плана по паре (код станка, id изделия) — для колонок «сейчас/далее»."""
    out: dict[tuple[str, int], str] = {}
    for sr in schedule_rows:
        mc = _norm_machine_code_key(str(sr.get("machine_code") or ""))
        pid = sr.get("product_id")
        if not mc or pid in (None, ""):
            continue
        try:
            pi = int(pid)
        except (TypeError, ValueError):
            continue
        line = str(sr.get("setup_line") or "").strip()
        if not line:
            continue
        key = (mc, pi)
        if key not in out:
            out[key] = line
    return out


def _schedule_setup_ids_by_machine_product(schedule_rows: list[dict]) -> dict[tuple[str, int], int | None]:
    """Выбранная установка в плане по паре (код станка, id изделия)."""
    out: dict[tuple[str, int], int | None] = {}
    for sr in schedule_rows:
        mc = _norm_machine_code_key(str(sr.get("machine_code") or ""))
        pid = sr.get("product_id")
        if not mc or pid in (None, ""):
            continue
        try:
            pi = int(pid)
        except (TypeError, ValueError):
            continue
        sid_raw = sr.get("setup_id")
        si: int | None = None
        if sid_raw not in (None, ""):
            try:
                si = int(sid_raw)
            except (TypeError, ValueError):
                si = None
        key = (mc, pi)
        if key not in out:
            out[key] = si
    return out


def _machine_rows_with_quick_setup_slots(
    machine_rows: list[dict],
    schedule_rows: list[dict],
    setups_by_product: dict[int, list[dict[str, int | str]]],
) -> list[dict]:
    look_line = _schedule_setup_lines_by_machine_product(schedule_rows)
    look_sid = _schedule_setup_ids_by_machine_product(schedule_rows)
    out: list[dict] = []
    for r in machine_rows:
        d = dict(r)
        code = _norm_machine_code_key(str(d.get("code") or ""))
        cpi = d.get("current_product_id")
        npi = d.get("next_product_id")
        csl = ""
        nsl = ""
        csi: int | None = None
        nsi: int | None = None
        if code and cpi is not None:
            try:
                ik = (code, int(cpi))
                csl = look_line.get(ik, "") or ""
                csi = look_sid.get(ik)
            except (TypeError, ValueError):
                pass
        stored_csi = d.get("current_setup_id")
        if cpi is not None and stored_csi not in (None, ""):
            try:
                stored_csi_int = int(stored_csi)
            except (TypeError, ValueError):
                stored_csi_int = None
            if stored_csi_int is not None and any(int(s["id"]) == stored_csi_int for s in setups_by_product.get(int(cpi), [])):
                csi = stored_csi_int
        if code and npi is not None:
            try:
                ik = (code, int(npi))
                nsl = look_line.get(ik, "") or ""
                nsi = look_sid.get(ik)
            except (TypeError, ValueError):
                pass
        stored_nsi = d.get("next_setup_id")
        if npi is not None and stored_nsi not in (None, ""):
            try:
                stored_nsi_int = int(stored_nsi)
            except (TypeError, ValueError):
                stored_nsi_int = None
            if stored_nsi_int is not None and any(int(s["id"]) == stored_nsi_int for s in setups_by_product.get(int(npi), [])):
                nsi = stored_nsi_int
        d["current_setup_line"] = csl
        d["next_setup_line"] = nsl
        d["current_setup_id"] = "" if csi is None else csi
        d["next_setup_id"] = "" if nsi is None else nsi
        cpo: int | None = None
        npo: int | None = None
        if cpi is not None:
            try:
                cpo = int(cpi)
            except (TypeError, ValueError):
                cpo = None
        if npi is not None:
            try:
                npo = int(npi)
            except (TypeError, ValueError):
                npo = None
        d["current_setup_options"] = list(setups_by_product.get(cpo, [])) if cpo is not None else []
        d["next_setup_options"] = list(setups_by_product.get(npo, [])) if npo is not None else []
        out.append(d)
    return out


def _setups_by_product_id(product_ids: set[int]) -> dict[int, list[dict[str, int | str]]]:
    """Установки наладки по изделию (как вкладки «Уст. N» в карточке изделия)."""
    if not product_ids:
        return {}
    qs = ProductSetup.objects.filter(product_id__in=product_ids).order_by("product_id", "sort_order", "id")
    out: dict[int, list[dict[str, int | str]]] = {}
    for su in qs:
        out.setdefault(int(su.product_id), []).append({"id": int(su.pk), "name": (su.name or "").strip()[:200]})
    return out


def _schedule_rows_with_display(
    rows: list[dict],
    product_by_id: dict[int, str],
    setups_by_product: dict[int, list[dict[str, int | str]]],
) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        pid = r.get("product_id")
        if pid is not None and pid in product_by_id:
            display = product_by_id[pid]
        else:
            display = (r.get("label") or "").strip()
        pid_key: int | None = None
        if pid not in (None, ""):
            try:
                pid_key = int(pid)
            except (TypeError, ValueError):
                pid_key = None
        setups = setups_by_product.get(pid_key, []) if pid_key is not None else []
        setup_id_raw = r.get("setup_id")
        setup_id_res: int | None = None
        if isinstance(setup_id_raw, int):
            setup_id_res = setup_id_raw
        elif setup_id_raw not in (None, ""):
            try:
                setup_id_res = int(setup_id_raw)
            except (TypeError, ValueError):
                setup_id_res = None
        if setup_id_res is not None and not any(int(s["id"]) == setup_id_res for s in setups):
            setup_id_res = None
        if pid_key is not None and setups and setup_id_res is None and len(setups) == 1:
            setup_id_res = int(setups[0]["id"])
        setup_line = ""
        if setup_id_res is not None:
            for i, su in enumerate(setups, start=1):
                if int(su["id"]) == setup_id_res:
                    nm = str(su.get("name") or "").strip()
                    setup_line = f"Уст. {i} — {nm}" if nm else f"Уст. {i}"
                    break
        out.append(
            {
                **r,
                "product_id": "" if pid is None else pid,
                "display": display,
                "setup_id": setup_id_res if setup_id_res is not None else "",
                "setup_line": setup_line,
                "setup_options": list(setups),
            }
        )
    # Сортировка по приоритету, затем по кол-ву (по убыванию)
    def sort_key(row: dict) -> tuple:
        priority_str = str(row.get("priority") or "").strip()
        qty_str = str(row.get("qty") or "").strip()
        try:
            priority = int(priority_str)
        except (ValueError, TypeError):
            priority = float('inf')  # Пустые приоритеты в конец
        try:
            qty = -int(qty_str)  # Минус для сортировки по убыванию
        except (ValueError, TypeError):
            qty = 0
        return (priority, qty)

    out.sort(key=sort_key)
    return out


def _optional_product_id(raw, valid_pids: set[int]) -> int | None:
    if raw in (None, "", False):
        return None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None
    if pid not in valid_pids:
        return None
    return pid


def _normalize_machine_rows(raw, valid_pids: set[int] | None = None) -> list[dict]:
    valid = valid_pids if valid_pids is not None else set()
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for r in raw[:MAX_MACHINE_ROWS]:
        if not isinstance(r, dict):
            continue
        cpi = _optional_product_id(r.get("current_product_id"), valid)
        npi = _optional_product_id(r.get("next_product_id"), valid)
        tag_raw = str(r.get("tag") or "").strip()[:64]
        if not tag_raw or tag_raw.upper() == "GG":
            tag = "Т"
        else:
            tag = tag_raw
        current_setup_id = None
        next_setup_id = None
        for attr, product_id in (("current_setup_id", cpi), ("next_setup_id", npi)):
            if product_id is None:
                continue
            setup_raw = r.get(attr)
            if setup_raw in (None, ""):
                continue
            try:
                setup_id = int(setup_raw)
            except (TypeError, ValueError):
                continue
            if attr == "current_setup_id":
                current_setup_id = setup_id
            else:
                next_setup_id = setup_id
        out.append(
            {
                "code": str(r.get("code") or "").strip()[:32],
                "current": str(r.get("current") or "").strip()[:500],
                "next": str(r.get("next") or "").strip()[:500],
                "extra": str(r.get("extra") or "").strip()[:2000],
                "tag": tag,
                "current_product_id": cpi,
                "next_product_id": npi,
                "current_setup_id": current_setup_id,
                "next_setup_id": next_setup_id,
            }
        )
    return out


def _normalize_schedule_rows(raw, valid_pids: set[int]) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    staged: list[tuple[str, str, int | None, int | None]] = []
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
        sid_raw = r.get("setup_id")
        setup_id: int | None = None
        if sid_raw not in (None, ""):
            try:
                setup_id = int(sid_raw)
            except (TypeError, ValueError):
                setup_id = None
        staged.append(
            (
                str(r.get("label") or "").strip()[:500],
                str(r.get("machine_code") or "").strip()[:32],
                pid,
                setup_id,
                str(r.get("qty") or "").strip()[:32],
                str(r.get("priority") or "").strip()[:10],
                str(r.get("color") or "").strip()[:7],
            )
        )
    pids_for_setup = {p for _, _, p, _, _, _, _ in staged if p is not None}
    valid_pairs: set[tuple[int, int]] = set()
    if pids_for_setup:
        for su in ProductSetup.objects.filter(product_id__in=pids_for_setup).only("id", "product_id"):
            valid_pairs.add((int(su.product_id), int(su.pk)))
    for label, mcode, pid, setup_id, qty, priority, color in staged:
        if pid is None:
            setup_id = None
        elif setup_id is not None and (pid, setup_id) not in valid_pairs:
            setup_id = None
        out.append(
            {
                "label": label,
                "machine_code": mcode,
                "product_id": pid,
                "setup_id": setup_id,
                "qty": qty,
                "priority": priority,
                "color": color,
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
    mrows = _normalize_machine_rows(body.get("machine_rows"), valid_pids)
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
    plist = list(Product.objects.order_by("name").only("id", "name", "list_preview_image"))
    product_by_id = {p.id: (p.name or "") for p in plist}
    valid_pids = set(product_by_id.keys())
    product_options = [{"id": p.id, "name": p.name or ""} for p in plist]
    setups_by_product = _setups_by_product_id(valid_pids)

    machine_rows = list(_DEFAULT_MACHINE_ROWS)
    schedule_seed = list(_DEFAULT_SCHEDULE_ROWS)
    machines_board_has_server = False

    board_payload = _board_payload_from_db()
    if board_payload:
        mr = _normalize_machine_rows(board_payload.get("machine_rows"), valid_pids)
        sr = _normalize_schedule_rows(board_payload.get("schedule_rows"), valid_pids)
        if mr and sr:
            machine_rows = mr
            schedule_seed = sr
            machines_board_has_server = True

    schedule_rows = _schedule_rows_with_display(schedule_seed, product_by_id, setups_by_product)
    machine_rows = _machine_rows_with_quick_setup_slots(
        _machine_rows_with_label_parts(machine_rows),
        schedule_rows,
        setups_by_product,
    )

    if request.method == "POST":
        if (request.headers.get("X-Requested-With") or "").strip() != "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Ожидается AJAX."}, status=400)
        return _machines_post_save(request)

    machines_products_json: list[dict] = []
    for p in plist:
        url = ""
        if p.list_preview_image:
            url = request.build_absolute_uri(p.list_preview_image.url)
        machines_products_json.append(
            {
                "id": p.id,
                "name": p.name or "",
                "list_preview_url": url,
                "setups": setups_by_product.get(p.id, []),
            }
        )

    product_detail_url_sentinel = reverse("product_detail", args=[_MACHINES_DETAIL_URL_SENTINEL])

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
            "machines_products_json": machines_products_json,
            "product_detail_url_sentinel": product_detail_url_sentinel,
            "machines_detail_url_sentinel_pk": _MACHINES_DETAIL_URL_SENTINEL,
        },
    )
