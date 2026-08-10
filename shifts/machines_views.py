"""Раздел «Станки» (учёт станков, план на станке)."""
import json
import re

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
MACHINES_CONTENT_VERSION = 15

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


def _schedule_sort_key(row: dict) -> tuple:
    """Меньший приоритет — выше в списке; при равном — большее кол-во выше."""
    priority_str = str(row.get("priority") or "").strip()
    qty_str = str(row.get("qty") or "").strip()
    try:
        priority = int(priority_str)
    except (ValueError, TypeError):
        priority = float("inf")
    try:
        qty = -int(qty_str)
    except (ValueError, TypeError):
        qty = 0
    return (priority, qty)


def _sort_schedule_rows(rows: list[dict]) -> list[dict]:
    out = list(rows)
    out.sort(key=_schedule_sort_key)
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
    return _sort_schedule_rows(out)


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
        tools_setup_id = None
        tsi_raw = r.get("tools_setup_id")
        if tsi_raw not in (None, ""):
            try:
                tools_setup_id = int(tsi_raw)
            except (TypeError, ValueError):
                tools_setup_id = None
        tools_product_id = None
        tpi_raw = r.get("tools_product_id")
        if tpi_raw not in (None, ""):
            try:
                tools_product_id = int(tpi_raw)
            except (TypeError, ValueError):
                tools_product_id = None
            if tools_product_id is not None and tools_product_id not in valid:
                tools_product_id = None
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
                "tools": _normalize_machine_tools(r.get("tools")),
                "tools_setup_id": tools_setup_id,
                "tools_product_id": tools_product_id,
                "tools_product_name": str(r.get("tools_product_name") or "").strip()[:300],
                "tools_setup_name": str(r.get("tools_setup_name") or "").strip()[:180],
                "tools_loaded_at": str(r.get("tools_loaded_at") or "").strip()[:40],
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


def _normalize_machine_tools(raw) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for t in raw[:80]:
        if not isinstance(t, dict):
            continue
        product_id = None
        setup_id = None
        for attr in ("product_id", "setup_id"):
            raw_id = t.get(attr)
            if raw_id in (None, ""):
                continue
            try:
                val = int(raw_id)
            except (TypeError, ValueError):
                continue
            if attr == "product_id":
                product_id = val
            else:
                setup_id = val
        out.append(
            {
                "tool_number": str(t.get("tool_number") or "").strip()[:20],
                "correction_enabled": bool(t.get("correction_enabled")),
                "kor_n": str(t.get("kor_n") or "").strip()[:20],
                "kor_d": str(t.get("kor_d") or "").strip()[:20],
                "tool_type": str(t.get("tool_type") or "").strip()[:80],
                "diameter": str(t.get("diameter") or "").strip()[:40],
                "overhang": str(t.get("overhang") or "").strip()[:40],
                "note": str(t.get("note") or t.get("name") or "").strip()[:300],
                "product_name": str(t.get("product_name") or "").strip()[:300],
                "setup_name": str(t.get("setup_name") or "").strip()[:180],
                "product_id": product_id,
                "setup_id": setup_id,
            }
        )
    return out


def _norm_tool_number_key(tool_number: str) -> str:
    raw = " ".join((tool_number or "").split()).strip().upper()
    if not raw:
        return ""
    m = re.match(r"^(?:T\s*)?(\d{1,4})$", raw)
    if m:
        n = int(m.group(1))
        if n < 100:
            return f"T{n:02d}"
        return f"T{n}"
    return raw


def _tools_snapshot_for_setup(setup: ProductSetup, *, product: Product | None = None) -> list[dict]:
    rows = list(setup.tools.all().order_by("sort_order", "id"))
    product_name = ((product.name if product else "") or "").strip()[:300]
    if not product_name and setup.product_id:
        product_name = (getattr(setup.product, "name", None) or "").strip()[:300]
    setup_name = (setup.name or "").strip()[:180]
    out: list[dict] = []
    for row in rows:
        tn = (row.tool_number or "").strip()[:20]
        if not tn:
            continue
        out.append(
            {
                "tool_number": tn,
                "correction_enabled": bool(row.correction_enabled),
                "kor_n": (row.kor_n or "").strip()[:20],
                "kor_d": (row.kor_d or "").strip()[:20],
                "tool_type": (row.tool_type or "").strip()[:80],
                "diameter": (row.diameter or "").strip()[:40],
                "overhang": (row.overhang or "").strip()[:40],
                "note": (row.name or "").strip()[:300],
                "product_name": product_name,
                "setup_name": setup_name,
                "product_id": product.pk if product else setup.product_id,
                "setup_id": setup.pk,
            }
        )
    return out


def _tool_number_sort_key(tool_number: str) -> tuple[int, int | str]:
    key = _norm_tool_number_key(tool_number)
    if key.startswith("T") and key[1:].isdigit():
        return (0, int(key[1:]))
    if key.startswith("__empty_"):
        return (2, key)
    return (1, key)


def _merge_machine_tools_by_number(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """Заменяет только совпадающие номера инструмента; остальные позиции станка сохраняет."""
    by_key: dict[str, dict] = {}
    for t in existing or []:
        if not isinstance(t, dict):
            continue
        key = _norm_tool_number_key(str(t.get("tool_number") or ""))
        if not key:
            key = f"__empty_{len(by_key)}"
        by_key[key] = dict(t)

    replaced = 0
    added = 0
    for t in incoming or []:
        if not isinstance(t, dict):
            continue
        key = _norm_tool_number_key(str(t.get("tool_number") or ""))
        if not key:
            continue
        if key in by_key:
            replaced += 1
        else:
            added += 1
        by_key[key] = dict(t)

    merged = sorted(
        by_key.values(),
        key=lambda row: _tool_number_sort_key(str(row.get("tool_number") or "")),
    )
    return merged[:80], replaced, added


def _merge_preserved_machine_tools(new_rows: list[dict], old_rows: list[dict]) -> list[dict]:
    """Сохраняет снимок инструмента при сохранении доски из UI станков (там tools не передаются)."""
    old_by_code = {_norm_machine_code_key(str(r.get("code") or "")): r for r in old_rows}
    out: list[dict] = []
    for r in new_rows:
        d = dict(r)
        code = _norm_machine_code_key(str(d.get("code") or ""))
        if not d.get("tools"):
            old = old_by_code.get(code)
            if old and old.get("tools"):
                d["tools"] = list(old.get("tools") or [])
                if old.get("tools_setup_id") not in (None, ""):
                    d["tools_setup_id"] = old.get("tools_setup_id")
                if old.get("tools_product_id") not in (None, ""):
                    d["tools_product_id"] = old.get("tools_product_id")
                if old.get("tools_product_name"):
                    d["tools_product_name"] = old.get("tools_product_name")
                if old.get("tools_setup_name"):
                    d["tools_setup_name"] = old.get("tools_setup_name")
                if old.get("tools_loaded_at"):
                    d["tools_loaded_at"] = old.get("tools_loaded_at")
        out.append(d)
    return out


def list_machine_codes() -> list[str]:
    valid_pids = set(Product.objects.values_list("id", flat=True))
    board = _board_payload_from_db()
    if board:
        rows = _normalize_machine_rows(board.get("machine_rows"), valid_pids)
    else:
        rows = _normalize_machine_rows(_DEFAULT_MACHINE_ROWS, valid_pids)
    codes: list[str] = []
    seen: set[str] = set()
    for r in rows:
        code = str(r.get("code") or "").strip()
        key = _norm_machine_code_key(code)
        if not code or key in seen:
            continue
        seen.add(key)
        codes.append(code)
    return codes


def assign_product_setup_to_machine(*, machine_code: str, product: Product, setup: ProductSetup) -> dict:
    """Ставит изделие+установку в «В работе» и подменяет в станке только совпадающие номера инструмента."""
    code_key = _norm_machine_code_key(machine_code)
    if not code_key:
        return {"ok": False, "error": "Укажите станок."}
    if setup.product_id != product.pk:
        return {"ok": False, "error": "Установка не принадлежит этому изделию."}

    valid_pids = set(Product.objects.values_list("id", flat=True))
    board = _board_payload_from_db()
    if board:
        mrows = _normalize_machine_rows(board.get("machine_rows"), valid_pids)
        srows = _normalize_schedule_rows(board.get("schedule_rows"), valid_pids)
        cv = board.get("content_version")
    else:
        mrows = _normalize_machine_rows(_DEFAULT_MACHINE_ROWS, valid_pids)
        srows = _normalize_schedule_rows(_DEFAULT_SCHEDULE_ROWS, valid_pids)
        cv = MACHINES_CONTENT_VERSION

    if not mrows:
        return {"ok": False, "error": "Список станков пуст."}
    if not srows:
        srows = _normalize_schedule_rows(_DEFAULT_SCHEDULE_ROWS, valid_pids)

    idx = None
    for i, r in enumerate(mrows):
        if _norm_machine_code_key(str(r.get("code") or "")) == code_key:
            idx = i
            break
    if idx is None:
        return {"ok": False, "error": f"Станок «{machine_code.strip()}» не найден в списке."}

    incoming = _tools_snapshot_for_setup(setup, product=product)
    if not incoming:
        return {"ok": False, "error": "В установке нет строк инструмента с номером (T01…)."}

    existing = list(mrows[idx].get("tools") or [])
    merged, replaced, added = _merge_machine_tools_by_number(existing, incoming)
    display_code = str(mrows[idx].get("code") or machine_code).strip()
    prev_current = str(mrows[idx].get("current") or "").strip()
    mrows[idx]["current"] = (product.name or "").strip()[:500]
    mrows[idx]["current_product_id"] = product.pk
    mrows[idx]["current_setup_id"] = setup.pk
    mrows[idx]["tools"] = merged
    mrows[idx]["tools_setup_id"] = setup.pk
    mrows[idx]["tools_product_id"] = product.pk
    mrows[idx]["tools_product_name"] = (product.name or "").strip()[:300]
    mrows[idx]["tools_setup_name"] = (setup.name or "").strip()[:180]
    from django.utils import timezone

    mrows[idx]["tools_loaded_at"] = timezone.now().isoformat(timespec="seconds")

    try:
        cv_int = int(cv) if cv is not None and str(cv).strip() != "" else int(MACHINES_CONTENT_VERSION)
    except (TypeError, ValueError):
        cv_int = int(MACHINES_CONTENT_VERSION)
    cv_int = max(cv_int, int(MACHINES_CONTENT_VERSION)) + 1

    payload = {
        "machine_rows": mrows,
        "schedule_rows": srows,
        "content_version": cv_int,
    }
    MachinesBoardState.objects.update_or_create(pk=1, defaults={"payload": payload})
    return {
        "ok": True,
        "machine_code": display_code,
        "tools_count": len(incoming),
        "tools_total": len(merged),
        "tools_replaced": replaced,
        "tools_added": added,
        "setup_id": setup.pk,
        "setup_name": (setup.name or "").strip(),
        "previous_current": prev_current,
        "content_version": cv_int,
    }


def _machines_post_save(request):
    u = biota_user(request)
    if not machines_quick_edit_for_user(u):
        return JsonResponse({"ok": False, "error": "Нет права на быстрое редактирование «Станки»."}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)
    action = (body.get("action") or "").strip()
    if action != "save_machines_board":
        return JsonResponse({"ok": False, "error": "Неизвестное действие."}, status=400)
    valid_pids = set(Product.objects.values_list("id", flat=True))
    old_board = _board_payload_from_db() or {}
    old_mrows = _normalize_machine_rows(old_board.get("machine_rows"), valid_pids)
    mrows = _merge_preserved_machine_tools(
        _normalize_machine_rows(body.get("machine_rows"), valid_pids),
        old_mrows,
    )
    srows = _sort_schedule_rows(_normalize_schedule_rows(body.get("schedule_rows"), valid_pids))
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
    plist = list(
        Product.objects.filter(catalog_section=Product.CATALOG_NALADKI)
        .order_by("name")
        .only("id", "name", "list_preview_image")
    )
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

    # Подтянуть имена детали/установки для старых снимков без сохранённых подписей
    missing_product_ids: set[int] = set()
    missing_setup_ids: set[int] = set()
    for r in machine_rows:
        if not r.get("tools"):
            continue
        if not (r.get("tools_product_name") or "").strip():
            pid = r.get("tools_product_id") or r.get("current_product_id")
            if pid is not None:
                try:
                    missing_product_ids.add(int(pid))
                except (TypeError, ValueError):
                    pass
        if not (r.get("tools_setup_name") or "").strip():
            sid = r.get("tools_setup_id") or r.get("current_setup_id")
            if sid is not None:
                try:
                    missing_setup_ids.add(int(sid))
                except (TypeError, ValueError):
                    pass
    product_name_by_id = {
        p.id: (p.name or "")
        for p in Product.objects.filter(pk__in=missing_product_ids).only("id", "name")
    } if missing_product_ids else {}
    setup_name_by_id = {
        s.id: (s.name or "")
        for s in ProductSetup.objects.filter(pk__in=missing_setup_ids).only("id", "name")
    } if missing_setup_ids else {}

    tools_by_machine_code: dict[str, dict] = {}
    for r in machine_rows:
        code = str(r.get("code") or "").strip()
        if not code:
            continue
        product_name = str(r.get("tools_product_name") or "").strip()
        setup_name = str(r.get("tools_setup_name") or "").strip()
        if not product_name:
            pid = r.get("tools_product_id") or r.get("current_product_id")
            try:
                product_name = product_name_by_id.get(int(pid), "") if pid is not None else ""
            except (TypeError, ValueError):
                product_name = ""
            if not product_name:
                product_name = str(r.get("current") or "").strip()
        if not setup_name:
            sid = r.get("tools_setup_id") or r.get("current_setup_id")
            try:
                setup_name = setup_name_by_id.get(int(sid), "") if sid is not None else ""
            except (TypeError, ValueError):
                setup_name = ""
        tools_by_machine_code[code] = {
            "tools": list(r.get("tools") or []),
            "product_name": product_name,
            "setup_name": setup_name,
            "product_id": r.get("tools_product_id") or r.get("current_product_id") or None,
            "setup_id": r.get("tools_setup_id") or r.get("current_setup_id") or None,
            "loaded_at": r.get("tools_loaded_at") or "",
        }

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
            "machines_tools_by_code": tools_by_machine_code,
            "product_detail_url_sentinel": product_detail_url_sentinel,
            "machines_detail_url_sentinel_pk": _MACHINES_DETAIL_URL_SENTINEL,
        },
    )
