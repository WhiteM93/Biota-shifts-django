from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from biota_shifts import db as biota_db
from biota_shifts.auth import _is_admin, employees_df_for_nav, inventory_stock_manage_for_user, nav_permissions_for_user
from biota_shifts.constants import MONTH_NAMES_RU
from biota_shifts.emp_codes import normalize_emp_code
from biota_shifts.schedule import employee_label_row
from .auth_utils import (
    biota_login_required,
    biota_user,
    inventory_route_nav_access_required,
    write_permission_required,
)
from .body_tool_constants import (
    BODY_TOOL_COUPLINGS,
    BODY_TOOL_FAMILIES,
    BODY_TOOL_SHANK_TYPES,
    BALL_MILL_SHANK_TYPES,
    CHAMFER_MILL_SHANK_TYPES,
    END_MILL_SHANK_TYPES,
    FACE_MILL_ANGLES,
    HIGH_SPEED_ANGLE_OPTIONS,
    HIGH_SPEED_BODY_STYLES,
    HIGH_SPEED_SHANK_TYPES,
    INDEXABLE_MILL_CUTTER_TYPES,
    INSERT_SIZE_OTHER,
    MODULAR_HEAD_THREADS,
    ROUND_INSERT_SHANK_TYPES,
    build_body_tool_display_name,
    coupling_from_shank,
    normalize_body_tool_coupling,
    normalize_body_tool_family,
    normalize_body_tool_shank,
    normalize_high_speed_body_style,
    normalize_indexable_mill_cutter,
    normalize_insert_size,
    normalize_modular_head_thread,
    parse_angle_or_variable,
)
from .collet_constants import (
    COLLET_THREAD_STANDARDS,
    COLLET_THREADING_SERIES,
    COLLET_THREADING_USE,
    COLLET_TYPES,
    COLLET_TYPE_TOOLTIPS,
    ER_CLAMP_RANGES,
    ER_COLLET_SIZES,
    COLLET_ER_G_INNER_DIAMETERS,
    build_collet_display_name,
    normalize_collet_er_g_inner_diameter,
    normalize_collet_square_size,
    normalize_collet_thread_standard,
    normalize_collet_threading_series,
    normalize_collet_threading_use,
    normalize_collet_type,
    normalize_er_clamp_range,
    normalize_er_collet_size,
)
from .inventory_analysis import analysis_context, normalize_group_field
from .insert_constants import (
    INSERT_EDGE_LENGTH_CODES,
    INSERT_NOSE_RADIUS_CODES,
    INSERT_RELIEF_ANGLES,
    INSERT_SHAPES,
    INSERT_THICKNESS_CODES,
    INSERT_TOLERANCE_CLASSES,
    INSERT_COLUMN_TOOLTIPS,
    INSERT_FAMILY_OTHER,
    INSERT_GRADE_OTHER,
    INSERT_MACHINING_APPLICATIONS,
    MILLING_INSERT_FAMILIES,
    merge_insert_chipbreaker_grades,
    normalize_insert_machining_apps,
    build_insert_display_name,
    normalize_milling_family,
)
from .models import (
    CENTER_DRILL_ANGLES,
    COUNTERSINK_ANGLES,
    COUNTERSINK_TYPES,
    COATING_TYPES,
    CountersinkSpec,
    DrillSpec,
    END_MILL_TYPES,
    BodyToolSpec,
    CenterDrillSpec,
    EndMillSpec,
    ColletSpec,
    InsertSpec,
    InventoryStockEvent,
    InventoryWatchTemplate,
    StockMovement,
    TapSpec,
    ToolItem,
    ToolMaterialExtra,
    UserInventoryStockFilterPrefs,
    PurchaseRequest,
    PurchaseStore,
    EmployeeDefectRecord,
    EmployeePayrollProfile,
    EmployeePayrollMonthStatus,
    TAP_HOLE_TYPES,
    TAP_TOOL_TYPES,
    THREAD_KINDS,
    THREAD_STANDARDS,
    TOOL_MATERIAL_TYPES,
    WORK_MATERIAL_TYPES,
    PURCHASE_STATUSES,
    normalize_thread_kind,
    normalize_work_material_codes,
    work_material_display_text,
)

TOOL_MATERIAL_FILTER_OTHER = "__other__"
PURCHASE_STORE_FILTER_OTHER = "__purchase_store_other__"
_TOOL_MATERIAL_STD_KEYS = frozenset(k for k, _ in TOOL_MATERIAL_TYPES)
_INVENTORY_CATEGORIES = frozenset(
    {"end_mill", "body_tool", "tap", "center_drill", "countersink", "drill", "insert", "collet"}
)
_HISTORY_MOVEMENT_TYPES = frozenset({"issue", "restock", "writeoff"})


def _analysis_panel_redirect(request, **extra: str) -> redirect:
    params: dict[str, str] = {"panel": "analysis"}
    cat = (extra.get("analysis_category") or request.POST.get("analysis_category") or request.GET.get("analysis_category") or "end_mill").strip()
    if cat in _INVENTORY_CATEGORIES:
        params["analysis_category"] = cat
    group_by = (extra.get("group_by") or request.POST.get("group_by") or request.GET.get("group_by") or "").strip()
    if group_by:
        params["group_by"] = group_by
    show_zero = (extra.get("show_zero") or request.POST.get("show_zero") or request.GET.get("show_zero") or "").strip()
    if show_zero == "1":
        params["show_zero"] = "1"
    search = (extra.get("analysis_search") or request.POST.get("analysis_search") or request.GET.get("analysis_search") or "").strip()
    if search:
        params["analysis_search"] = search
    return redirect(f"{request.path}?{urlencode(params)}")


def _history_panel_redirect(request):
    params: dict[str, str] = {"panel": "history"}
    ht = (request.GET.get("history_movement_type") or request.POST.get("history_movement_type") or "").strip()
    if ht in _HISTORY_MOVEMENT_TYPES:
        params["history_movement_type"] = ht
    return redirect(f"{request.path}?{urlencode(params)}")


_ARRIVAL_REQUIRED_DIAMETER: dict[str, tuple[str, str]] = {
    "drill": ("dr_diameter_mm", "диаметр D (мм) для сверла"),
    "end_mill": ("em_diameter_mm", "диаметр D (мм) для фрезы"),
    "center_drill": ("cd_diameter_mm", "диаметр D (мм) для центровки"),
    "countersink": ("cs_diameter_mm", "диаметр D (мм) для зенкера"),
}


def _arrival_bulk_row_validation_errors(row: dict, idx: int) -> list[str]:
    category = (row.get("category") or "").strip()
    errs: list[str] = []
    if category in _INVENTORY_CATEGORIES and category != "collet":
        if not normalize_work_material_codes(row.get("work_material")):
            errs.append(f"Строка {idx}: укажите хотя бы одну группу материала обработки (P, M, K…).")
    if category == "collet":
        ct = normalize_collet_type(row.get("collet_type"))
        if not ct:
            errs.append(f"Строка {idx}: укажите тип цанги.")
            return errs
        if ct == "er":
            if not normalize_er_collet_size(row.get("collet_er_size")):
                errs.append(f"Строка {idx}: укажите размер ER (ER32, ER16…).")
            if not normalize_er_clamp_range(row.get("collet_clamp_range")):
                errs.append(f"Строка {idx}: укажите диапазон зажима (3-4, 4-5…).")
        elif ct == "er_g":
            if not normalize_er_collet_size(row.get("collet_er_size")):
                errs.append(f"Строка {idx}: укажите размер ER (ER16, ER32…).")
            if not normalize_collet_er_g_inner_diameter(
                row.get("collet_inner_diameter") or row.get("collet_square_size")
            ):
                errs.append(f"Строка {idx}: укажите внутренний диаметр.")
        elif ct == "threading":
            if not normalize_collet_threading_use(row.get("collet_threading_use")):
                errs.append(f"Строка {idx}: укажите назначение (метчики / плашки).")
            if not normalize_collet_threading_series(row.get("collet_threading_series")):
                errs.append(f"Строка {idx}: укажите серию (TC820, GT12…).")
            if not normalize_collet_thread_standard(row.get("collet_thread_standard")):
                errs.append(f"Строка {idx}: укажите стандарт резьбы (DIN371, ISO…).")
        return errs
    if category == "body_tool":
        if not (row.get("body_cutter") or "").strip():
            errs.append(f"Строка {idx}: укажите тип корпусной фрезы.")
        if _to_decimal_or_none(row.get("bt_diameter_mm")) is None:
            errs.append(f"Строка {idx}: укажите диаметр D (мм) для корпусного инструмента.")
        return errs
    if category == "insert":
        shape = (row.get("ins_shape") or "").strip()
        edge = (row.get("ins_edge_code") or "").strip()
        th = (row.get("ins_thickness_code") or "").strip()
        nr = (row.get("ins_nose_code") or "").strip()
        mach = normalize_insert_machining_apps(
            row.get("ins_machining_app") or row.get("machining_application")
        )
        if not shape or not edge or not th or not nr:
            errs.append(f"Строка {idx}: для пластины укажите форму, L (длина), S (толщина) и R (радиус).")
        if not mach:
            errs.append(f"Строка {idx}: укажите хотя бы один вид обработки (чистовая / получистовая / черновая).")
        return errs
    spec = _ARRIVAL_REQUIRED_DIAMETER.get(category)
    if spec:
        key, label = spec
        if _to_decimal_or_none(row.get(key)) is None:
            errs.append(f"Строка {idx}: укажите {label}.")
    return errs


def _register_tool_material_extra(value: str) -> str | None:
    v = (value or "").strip()[:80]
    if not v or v in _TOOL_MATERIAL_STD_KEYS or v == TOOL_MATERIAL_FILTER_OTHER:
        return None
    ToolMaterialExtra.objects.get_or_create(value=v)
    return v


def _register_purchase_store(name: str) -> str | None:
    n = (name or "").strip()[:120]
    if not n or n == PURCHASE_STORE_FILTER_OTHER:
        return None
    PurchaseStore.objects.get_or_create(name=n)
    return n


def _purchase_store_options(*, extra_candidate: str = "") -> list[str]:
    from_vocab = set(PurchaseStore.objects.values_list("name", flat=True))
    from_requests = {
        v.strip()
        for v in PurchaseRequest.objects.exclude(store_name="").values_list("store_name", flat=True).distinct()
        if v and v.strip()
    }
    out = sorted(from_vocab | from_requests)
    cand = (extra_candidate or "").strip()[:120]
    if cand and cand not in out:
        out = sorted(set(out) | {cand})
    return out


def _store_name_from_url(url: str) -> str:
    from urllib.parse import urlparse

    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    try:
        host = (urlparse(raw).hostname or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) < 2:
        return host[:120]
    multi_tlds = {"co.uk", "com.ru", "org.ru", "net.ru"}
    if len(parts) >= 3 and ".".join(parts[-2:]) in multi_tlds:
        return parts[-3][:120]
    return parts[-2][:120]


def _resolve_purchase_store_name(post) -> str:
    sel = (post.get("store_name") or "").strip()
    custom = (post.get("store_name_custom") or "").strip()
    if sel == PURCHASE_STORE_FILTER_OTHER:
        return custom[:120]
    if sel:
        return sel[:120]
    store_link = (post.get("store_link") or "").strip()
    if store_link:
        return _store_name_from_url(store_link)
    return ""


def _tool_material_extra_options(*, tools_qs=None, extra_candidate: str = "") -> list[str]:
    qs = tools_qs if tools_qs is not None else ToolItem.objects.all()
    from_tools = {
        v
        for v in qs.exclude(tool_material="").values_list("tool_material", flat=True).distinct()
        if v and v not in _TOOL_MATERIAL_STD_KEYS and v != TOOL_MATERIAL_FILTER_OTHER
    }
    from_vocab = set(ToolMaterialExtra.objects.values_list("value", flat=True))
    out = sorted(from_tools | from_vocab)
    cand = (extra_candidate or "").strip()[:80]
    if cand and cand not in _TOOL_MATERIAL_STD_KEYS and cand not in out:
        out = sorted(set(out) | {cand})
    return out


def _log_inventory_stock_event(
    *,
    actor: str,
    event_type: str,
    summary: str,
    tool: ToolItem | None = None,
    stock_movement: StockMovement | None = None,
    details: dict | None = None,
) -> None:
    InventoryStockEvent.objects.create(
        actor_username=(actor or "")[:120],
        event_type=event_type,
        summary=(summary or "")[:500],
        tool=tool,
        stock_movement=stock_movement,
        details=details or {},
    )


def _issue_remaining_qty(issue: StockMovement) -> int:
    processed = (
        StockMovement.objects.filter(parent_issue=issue, movement_type__in=["restock", "writeoff"])
        .aggregate(total=Coalesce(Sum("quantity"), Value(0, output_field=IntegerField())))
        .get("total", 0)
    )
    return max(0, int(issue.quantity or 0) - int(processed or 0))


def _parse_legacy_audit_change(text: str) -> dict | None:
    """Parse legacy 'name: 2→4 (+2)' strings from older audit events."""
    raw = (text or "").strip()
    if not raw or ":" not in raw:
        return None
    name, rest = raw.split(":", 1)
    name = name.strip()
    rest = rest.strip()
    m = re.search(r"(\d+)\s*[→\-]\s*(\d+)", rest)
    if not m:
        return {
            "tool_id": None,
            "tool_name": name,
            "expected": None,
            "counted": None,
            "delta": None,
            "movement_id": None,
            "kind": "unknown",
            "note": "",
            "legacy_text": raw,
        }
    expected = int(m.group(1))
    counted = int(m.group(2))
    delta = counted - expected
    return {
        "tool_id": None,
        "tool_name": name,
        "expected": expected,
        "counted": counted,
        "delta": delta,
        "movement_id": None,
        "kind": "surplus" if delta > 0 else ("deficit" if delta < 0 else "ok"),
        "note": "",
        "legacy_text": raw,
    }


def _enrich_container_audit_details(details: dict | None) -> dict:
    """Human-readable audit card payload + open issues for surplus lines."""
    d = dict(details or {}) if isinstance(details, dict) else {}
    rows = d.get("change_rows")
    if not isinstance(rows, list) or not rows:
        rows = []
        for text in d.get("changes") or []:
            parsed = _parse_legacy_audit_change(str(text))
            if parsed:
                rows.append(parsed)

    # Подтянуть tool_id / movement_id из строк аудита (старые события без change_rows)
    audit_id = d.get("audit_id")
    try:
        audit_id_int = int(audit_id) if audit_id is not None else 0
    except (TypeError, ValueError):
        audit_id_int = 0
    if audit_id_int:
        from .models import VisualContainerAuditLine

        line_by_name: dict[str, object] = {}
        line_by_tool: dict[int, object] = {}
        for ln in VisualContainerAuditLine.objects.filter(audit_id=audit_id_int, delta__gt=0).select_related(
            "tool", "stock_movement"
        ):
            if ln.tool_id:
                line_by_tool[ln.tool_id] = ln
            if ln.tool and ln.tool.name:
                line_by_name[(ln.tool.name or "").strip().lower()] = ln
        for r in rows:
            if not isinstance(r, dict):
                continue
            if int(r.get("delta") or 0) <= 0:
                continue
            ln = None
            if r.get("tool_id"):
                ln = line_by_tool.get(int(r["tool_id"]))
            if ln is None and r.get("tool_name"):
                ln = line_by_name.get(str(r["tool_name"]).strip().lower())
            if ln is None:
                continue
            if not r.get("tool_id"):
                r["tool_id"] = ln.tool_id
            if not r.get("movement_id") and ln.stock_movement_id:
                r["movement_id"] = ln.stock_movement_id
            if r.get("expected") is None:
                r["expected"] = ln.expected_qty
            if r.get("counted") is None:
                r["counted"] = ln.counted_qty
            if r.get("delta") is None:
                r["delta"] = ln.delta

    enriched: list[dict] = []
    surplus_tool_ids = [
        int(r["tool_id"])
        for r in rows
        if isinstance(r, dict) and r.get("tool_id") and int(r.get("delta") or 0) > 0
    ]
    issues_by_tool: dict[int, list[dict]] = {tid: [] for tid in surplus_tool_ids}
    unallocated_by_tool: dict[int, int] = {tid: 0 for tid in surplus_tool_ids}
    if surplus_tool_ids:
        issues = (
            StockMovement.objects.filter(movement_type="issue", tool_id__in=surplus_tool_ids)
            .select_related("tool")
            .annotate(
                processed_qty=Coalesce(
                    Sum("issue_outcomes__quantity"),
                    Value(0, output_field=IntegerField()),
                )
            )
            .annotate(remaining_qty=F("quantity") - F("processed_qty"))
            .order_by("-movement_date", "-id")[:120]
        )
        for iss in issues:
            rem = int(iss.remaining_qty or 0)
            issues_by_tool.setdefault(iss.tool_id, []).append(
                {
                    "id": iss.id,
                    "employee_name": (iss.employee_name or "").strip() or "Без ФИО",
                    "date": iss.movement_date.strftime("%d.%m.%Y") if iss.movement_date else "",
                    "issued": int(iss.quantity or 0),
                    "remaining": max(0, rem),
                    "is_open": rem > 0,
                    "comment": (iss.comment or "").strip()[:120],
                }
            )
        for mid, tid, qty in (
            StockMovement.objects.filter(
                tool_id__in=surplus_tool_ids,
                movement_type="restock",
                parent_issue_id__isnull=True,
                is_reverted=False,
            )
            .filter(Q(comment__startswith="Инвентаризация"))
            .values_list("id", "tool_id", "quantity")
        ):
            unallocated_by_tool[tid] = unallocated_by_tool.get(tid, 0) + int(qty or 0)

    movement_ids = [
        int(r["movement_id"])
        for r in rows
        if isinstance(r, dict) and r.get("movement_id")
    ]
    linked_map: dict[int, int] = {}
    if movement_ids:
        for mid, pid in StockMovement.objects.filter(id__in=movement_ids).values_list("id", "parent_issue_id"):
            if pid:
                linked_map[int(mid)] = int(pid)

    for r in rows:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        delta = int(row.get("delta") or 0)
        mid = row.get("movement_id")
        tid = int(row["tool_id"]) if row.get("tool_id") else None
        row["kind"] = row.get("kind") or ("surplus" if delta > 0 else ("deficit" if delta < 0 else "ok"))
        row["return_linked"] = bool(mid and int(mid) in linked_map)
        row["linked_issue_id"] = linked_map.get(int(mid)) if mid else None
        takers = issues_by_tool.get(tid, []) if tid and delta > 0 else []
        row["takers"] = takers
        row["open_issues"] = [t for t in takers if t.get("is_open")]
        row["surplus_left"] = int(unallocated_by_tool.get(tid, 0)) if tid else 0
        row["can_link_return"] = bool(delta > 0 and tid and row["surplus_left"] > 0 and row["open_issues"])
        enriched.append(row)

    d["change_rows"] = enriched
    d["label"] = (d.get("label") or "").replace("\n", " ").strip()
    return d


def _can_rollback_stock_movement(m: StockMovement) -> bool:
    if getattr(m, "is_reverted", False):
        return False
    if m.parent_issue_id:
        return False
    if m.movement_type == "issue" and m.issue_outcomes.exists():
        return False
    return True


def _rollback_stock_movement(movement_id: int, actor: str) -> tuple[bool, str]:
    with transaction.atomic():
        m = (
            StockMovement.objects.select_for_update()
            .select_related("tool")
            .prefetch_related("issue_outcomes")
            .filter(id=movement_id)
            .first()
        )
        if not m:
            return False, "Запись не найдена."
        if not _can_rollback_stock_movement(m):
            return False, "Эту запись нельзя откатить (уже откатана, привязана к выдаче или по ней есть возврат/списание)."
        tool = ToolItem.objects.select_for_update().filter(id=m.tool_id).first()
        if not tool:
            return False, "Инструмент не найден."
        qty = int(m.quantity)
        mt = m.movement_type
        if mt == "issue":
            tool.quantity += qty
            tool.save(update_fields=["quantity", "updated_at"])
            StockMovement.objects.create(
                movement_type="restock",
                tool=tool,
                quantity=qty,
                employee_name="",
                movement_date=m.movement_date,
                comment=f"Откат движения №{m.id} (выдача {qty} шт.).",
                created_by_account=actor,
            )
        elif mt == "restock":
            if tool.quantity < qty:
                return False, f"Нельзя откатить пополнение: на складе только {tool.quantity} шт."
            tool.quantity -= qty
            tool.save(update_fields=["quantity", "updated_at"])
            StockMovement.objects.create(
                movement_type="issue",
                tool=tool,
                quantity=qty,
                employee_name="",
                movement_date=m.movement_date,
                comment=f"Откат движения №{m.id} (было пополнение {qty} шт.).",
                created_by_account=actor,
            )
        elif mt == "writeoff":
            tool.quantity += qty
            tool.save(update_fields=["quantity", "updated_at"])
            StockMovement.objects.create(
                movement_type="restock",
                tool=tool,
                quantity=qty,
                employee_name="",
                movement_date=m.movement_date,
                comment=f"Откат движения №{m.id} (было списание {qty} шт.).",
                created_by_account=actor,
            )
        else:
            return False, "Тип операции не поддерживается для отката."
        now = timezone.now()
        m.is_reverted = True
        m.reverted_at = now
        m.reverted_by = actor
        m.save(update_fields=["is_reverted", "reverted_at", "reverted_by"])
        _log_inventory_stock_event(
            actor=actor,
            event_type=InventoryStockEvent.EVENT_ROLLBACK,
            tool=tool,
            stock_movement=m,
            summary=f"Откат движения №{m.id} ({m.get_movement_type_display()}, {qty} шт., {tool.name})",
            details={"reverted_movement_id": m.id, "movement_type": mt},
        )
    return True, ""


def _distinct_text_values(qs, field_name: str):
    return [v for v in qs.exclude(**{f"{field_name}__isnull": True}).values_list(field_name, flat=True).distinct().order_by(field_name) if v]


def _distinct_numeric_values(qs, field_name: str):
    return list(
        qs.exclude(**{f"{field_name}__isnull": True}).values_list(field_name, flat=True).distinct().order_by(field_name)
    )


def _to_decimal(val: str, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal((val or "").strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return default


def _to_int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _to_decimal_or_none(val: str):
    parsed = _to_decimal(val, Decimal("-1"))
    return parsed if parsed >= 0 else None


def _to_int_or_none(val: str):
    parsed = _to_int(val, -1)
    return parsed if parsed >= 0 else None


def _to_bool(val) -> bool:
    v = str(val or "").strip().lower()
    return v in ("1", "true", "yes", "on", "есть")


_STOCK_FILTER_PARAM_KEYS = frozenset(
    {
        "show_all",
        "category",
        "diameter_mm",
        "mill_overall_length_mm",
        "mill_cutting_length_mm",
        "mill_flutes_count",
        "mill_corner_radius_mm",
        "mill_type",
        "tap_size",
        "tap_pitch",
        "tap_thread_standard",
        "tap_thread_kind",
        "tap_hole_type",
        "tap_tool_type",
        "tap_overall_length_mm",
        "tap_cutting_length_mm",
        "center_diameter_mm",
        "center_overall_length_mm",
        "center_angle_deg",
        "countersink_type",
        "countersink_diameter_mm",
        "countersink_angle_deg",
        "countersink_overall_length_mm",
        "countersink_flutes_count",
        "countersink_size_label",
        "drill_diameter_mm",
        "drill_overall_length_mm",
        "drill_cutting_length_mm",
        "drill_angle_deg",
        "ins_shape",
        "ins_relief",
        "ins_tolerance",
        "ins_edge_code",
        "ins_thickness_code",
        "ins_nose_code",
        "ins_family",
        "ins_grade",
        "ins_iso",
        "collet_type",
        "collet_er_size",
        "collet_clamp_range",
        "collet_square_size",
        "collet_inner_diameter",
        "collet_thread_standard",
        "collet_threading_use",
        "collet_threading_series",
        "tool_material",
        "tool_material_custom",
        "coating_type",
        "work_material",
        "body_family",
        "body_cutter",
        "bt_diameter_mm",
        "bt_overall_length_mm",
        "bt_cutting_length_mm",
        "bt_teeth_count",
        "bt_coupling",
        "bt_insert_family",
        "bt_insert_size",
        "bt_mount_diameter_mm",
        "bt_coolant",
        "bt_ap_max_mm",
        "bt_angle_deg",
        "bt_brand",
        "bt_shank_type",
        "bt_variable_angle",
        "bt_hs_body_style",
        "bt_has_purpose",
        "bt_corner_radius_mm",
        "bt_insert_compat",
        "bt_mount_thread",
    }
)


def _load_inventory_stock_filter_prefs(username: str) -> dict[str, str]:
    try:
        row = UserInventoryStockFilterPrefs.objects.only("params").get(username=username)
    except UserInventoryStockFilterPrefs.DoesNotExist:
        return {}
    raw = row.params or {}
    out: dict[str, str] = {}
    for k in _STOCK_FILTER_PARAM_KEYS:
        if k not in raw:
            continue
        v = raw[k]
        out[k] = "" if v is None else str(v).strip()
    return out


def _merge_inventory_stock_query(username: str, request_get, *, use_saved: bool) -> dict[str, str]:
    merged = _load_inventory_stock_filter_prefs(username) if use_saved else {}
    merged = dict(merged)
    for k in _STOCK_FILTER_PARAM_KEYS:
        if k in request_get:
            merged[k] = (request_get.get(k) or "").strip()
    # Форма фильтра всегда шлёт show_all: отсутствующий ключ = сброс («Все»), а не старое значение из prefs.
    if use_saved and "show_all" in request_get:
        cat_raw = (request_get.get("category") if "category" in request_get else merged.get("category") or "").strip()
        if cat_raw in ("", "all"):
            cat = ""
        elif cat_raw in _INVENTORY_CATEGORIES:
            cat = cat_raw
        else:
            cat = ""
        allow = _STOCK_GLOBAL_KEYS | _STOCK_KEYS_BY_CATEGORY.get(cat, frozenset())
        for k in allow:
            if k not in request_get:
                merged[k] = ""
    return merged


_STOCK_GLOBAL_KEYS = frozenset(
    {
        "show_all",
        "category",
        "tool_material",
        "tool_material_custom",
        "coating_type",
        "work_material",
    }
)
_STOCK_KEYS_BY_CATEGORY = {
    "end_mill": frozenset(
        {
            "diameter_mm",
            "mill_overall_length_mm",
            "mill_cutting_length_mm",
            "mill_flutes_count",
            "mill_corner_radius_mm",
            "mill_type",
        }
    ),
    "tap": frozenset(
        {
            "tap_size",
            "tap_pitch",
            "tap_thread_standard",
            "tap_thread_kind",
            "tap_hole_type",
            "tap_tool_type",
            "tap_overall_length_mm",
            "tap_cutting_length_mm",
        }
    ),
    "center_drill": frozenset({"center_diameter_mm", "center_overall_length_mm", "center_angle_deg"}),
    "countersink": frozenset(
        {
            "countersink_type",
            "countersink_diameter_mm",
            "countersink_angle_deg",
            "countersink_overall_length_mm",
            "countersink_flutes_count",
            "countersink_size_label",
        }
    ),
    "drill": frozenset(
        {"drill_diameter_mm", "drill_overall_length_mm", "drill_cutting_length_mm", "drill_angle_deg"}
    ),
    "insert": frozenset(
        {
            "ins_shape",
            "ins_relief",
            "ins_tolerance",
            "ins_edge_code",
            "ins_thickness_code",
            "ins_nose_code",
            "ins_family",
            "ins_grade",
            "ins_iso",
        }
    ),
    "collet": frozenset(
        {
            "collet_type",
            "collet_er_size",
            "collet_clamp_range",
            "collet_square_size",
            "collet_inner_diameter",
            "collet_thread_standard",
            "collet_threading_use",
            "collet_threading_series",
        }
    ),
    "body_tool": frozenset(
        {
            "body_family",
            "body_cutter",
            "bt_diameter_mm",
            "bt_overall_length_mm",
            "bt_cutting_length_mm",
            "bt_teeth_count",
            "bt_coupling",
            "bt_insert_family",
            "bt_insert_size",
            "bt_mount_diameter_mm",
            "bt_coolant",
            "bt_ap_max_mm",
            "bt_angle_deg",
            "bt_brand",
            "bt_shank_type",
            "bt_variable_angle",
            "bt_hs_body_style",
            "bt_has_purpose",
            "bt_corner_radius_mm",
            "bt_insert_compat",
            "bt_mount_thread",
        }
    ),
}
_STOCK_DECIMAL_PARAM_KEYS = frozenset(
    {
        "diameter_mm",
        "mill_overall_length_mm",
        "mill_cutting_length_mm",
        "mill_corner_radius_mm",
        "tap_pitch",
        "tap_overall_length_mm",
        "tap_cutting_length_mm",
        "center_diameter_mm",
        "center_overall_length_mm",
        "countersink_diameter_mm",
        "countersink_overall_length_mm",
        "drill_diameter_mm",
        "drill_overall_length_mm",
        "drill_cutting_length_mm",
        "drill_angle_deg",
        "bt_diameter_mm",
        "bt_overall_length_mm",
        "bt_cutting_length_mm",
        "bt_mount_diameter_mm",
        "bt_ap_max_mm",
        "bt_angle_deg",
        "bt_corner_radius_mm",
    }
)
_STOCK_INT_PARAM_KEYS = frozenset({"mill_flutes_count", "countersink_flutes_count", "bt_teeth_count"})


def _resolve_stock_tool_material(params: dict) -> str:
    tm_param = (params.get("tool_material") or "").strip()
    tm_custom = ((params.get("tool_material_custom") or "").strip())[:80]
    if tm_param == TOOL_MATERIAL_FILTER_OTHER:
        return tm_custom[:80]
    return tm_param[:80]


def _apply_stock_detail_filters(qs, *, category: str, params: dict, exclude: frozenset | None = None):
    """Apply stock sidebar filters; `exclude` skips keys (leave-one-out for option lists)."""
    ex = exclude or frozenset()

    def g(key: str) -> str:
        if key in ex:
            return ""
        return (params.get(key) or "").strip()

    if category == "end_mill":
        diameter_mm_raw = g("diameter_mm")
        if diameter_mm_raw:
            diameter_mm = _to_decimal(diameter_mm_raw, Decimal("0"))
            if diameter_mm > 0:
                qs = qs.filter(end_mill_spec__diameter_mm=diameter_mm)
        mill_overall_length_raw = g("mill_overall_length_mm")
        if mill_overall_length_raw:
            mill_overall_length = _to_decimal(mill_overall_length_raw, Decimal("0"))
            if mill_overall_length > 0:
                qs = qs.filter(end_mill_spec__overall_length_mm=mill_overall_length)
        mill_cutting_length_raw = g("mill_cutting_length_mm")
        if mill_cutting_length_raw:
            mill_cutting_length = _to_decimal(mill_cutting_length_raw, Decimal("0"))
            if mill_cutting_length > 0:
                qs = qs.filter(end_mill_spec__cutting_length_mm=mill_cutting_length)
        mill_flutes_count_raw = g("mill_flutes_count")
        if mill_flutes_count_raw:
            mill_flutes_count = _to_int(mill_flutes_count_raw, 0)
            if mill_flutes_count > 0:
                qs = qs.filter(end_mill_spec__flutes_count=mill_flutes_count)
        mill_corner_radius_raw = g("mill_corner_radius_mm")
        if mill_corner_radius_raw:
            mill_corner_radius = _to_decimal(mill_corner_radius_raw, Decimal("-1"))
            if mill_corner_radius >= 0:
                qs = qs.filter(end_mill_spec__corner_radius_mm=mill_corner_radius)
        mill_type_raw = g("mill_type")
        if mill_type_raw:
            qs = qs.filter(end_mill_spec__mill_type=mill_type_raw)
    elif category == "body_tool":
        body_family_raw = g("body_family")
        if body_family_raw:
            qs = qs.filter(body_tool_spec__family=body_family_raw)
        body_cutter_raw = g("body_cutter")
        if body_cutter_raw:
            qs = qs.filter(body_tool_spec__cutter_type=body_cutter_raw)
        bt_diameter_raw = g("bt_diameter_mm")
        if bt_diameter_raw:
            bt_diameter = _to_decimal(bt_diameter_raw, Decimal("0"))
            if bt_diameter > 0:
                qs = qs.filter(body_tool_spec__diameter_mm=bt_diameter)
        bt_overall_length_raw = g("bt_overall_length_mm")
        if bt_overall_length_raw:
            bt_overall_length = _to_decimal(bt_overall_length_raw, Decimal("0"))
            if bt_overall_length > 0:
                qs = qs.filter(body_tool_spec__overall_length_mm=bt_overall_length)
        bt_cutting_length_raw = g("bt_cutting_length_mm")
        if bt_cutting_length_raw:
            bt_cutting_length = _to_decimal(bt_cutting_length_raw, Decimal("0"))
            if bt_cutting_length > 0:
                qs = qs.filter(body_tool_spec__cutting_length_mm=bt_cutting_length)
        bt_teeth_count_raw = g("bt_teeth_count")
        if bt_teeth_count_raw:
            bt_teeth_count = _to_int(bt_teeth_count_raw, 0)
            if bt_teeth_count > 0:
                qs = qs.filter(body_tool_spec__teeth_count=bt_teeth_count)
        bt_coupling_raw = g("bt_coupling")
        if bt_coupling_raw:
            qs = qs.filter(body_tool_spec__coupling=bt_coupling_raw)
        bt_insert_family_raw = g("bt_insert_family")
        if bt_insert_family_raw:
            qs = qs.filter(body_tool_spec__insert_family__iexact=bt_insert_family_raw)
        bt_insert_size_raw = g("bt_insert_size")
        if bt_insert_size_raw:
            qs = qs.filter(body_tool_spec__insert_size__iexact=bt_insert_size_raw)
        bt_mount_raw = g("bt_mount_diameter_mm")
        if bt_mount_raw:
            bt_mount = _to_decimal(bt_mount_raw, Decimal("0"))
            if bt_mount > 0:
                qs = qs.filter(body_tool_spec__mount_diameter_mm=bt_mount)
        bt_coolant_raw = g("bt_coolant")
        if bt_coolant_raw in ("0", "1"):
            qs = qs.filter(body_tool_spec__coolant_through=(bt_coolant_raw == "1"))
        bt_ap_raw = g("bt_ap_max_mm")
        if bt_ap_raw:
            bt_ap = _to_decimal(bt_ap_raw, Decimal("0"))
            if bt_ap > 0:
                qs = qs.filter(body_tool_spec__ap_max_mm=bt_ap)
        bt_angle_raw = g("bt_angle_deg")
        if bt_angle_raw == "variable":
            qs = qs.filter(body_tool_spec__variable_angle=True)
        elif bt_angle_raw:
            bt_angle = _to_decimal(bt_angle_raw, Decimal("-1"))
            if bt_angle >= 0:
                qs = qs.filter(body_tool_spec__approach_angle_deg=bt_angle, body_tool_spec__variable_angle=False)
        bt_brand_raw = g("bt_brand")
        if bt_brand_raw:
            qs = qs.filter(body_tool_spec__brand__iexact=bt_brand_raw)
        bt_shank_raw = g("bt_shank_type")
        if bt_shank_raw:
            qs = qs.filter(body_tool_spec__shank_type=normalize_body_tool_shank(bt_shank_raw))
        bt_variable_raw = g("bt_variable_angle")
        if bt_variable_raw in ("0", "1"):
            qs = qs.filter(body_tool_spec__variable_angle=(bt_variable_raw == "1"))
        bt_hs_style_raw = g("bt_hs_body_style")
        if bt_hs_style_raw:
            qs = qs.filter(body_tool_spec__hs_body_style=normalize_high_speed_body_style(bt_hs_style_raw))
        bt_purpose_raw = g("bt_has_purpose")
        if bt_purpose_raw in ("0", "1"):
            qs = qs.filter(body_tool_spec__has_purpose=(bt_purpose_raw == "1"))
        bt_radius_raw = g("bt_corner_radius_mm")
        if bt_radius_raw:
            bt_radius = _to_decimal(bt_radius_raw, Decimal("-1"))
            if bt_radius >= 0:
                qs = qs.filter(body_tool_spec__corner_radius_mm=bt_radius)
        bt_compat_raw = g("bt_insert_compat")
        if bt_compat_raw:
            qs = qs.filter(body_tool_spec__insert_compat__icontains=bt_compat_raw)
        bt_thread_raw = g("bt_mount_thread")
        if bt_thread_raw:
            qs = qs.filter(body_tool_spec__mount_thread=normalize_modular_head_thread(bt_thread_raw))
    elif category == "tap":
        tap_size = g("tap_size")
        if tap_size:
            qs = qs.filter(tap_spec__size_label__iexact=tap_size)
        tap_pitch_raw = g("tap_pitch")
        if tap_pitch_raw:
            tap_pitch = _to_decimal(tap_pitch_raw, Decimal("0"))
            if tap_pitch > 0:
                qs = qs.filter(tap_spec__pitch_mm=tap_pitch)
        tap_thread_standard = g("tap_thread_standard")
        if tap_thread_standard:
            qs = qs.filter(tap_spec__thread_standard=tap_thread_standard)
        tap_thread_kind = g("tap_thread_kind")
        if tap_thread_kind:
            qs = qs.filter(tap_spec__thread_kind=normalize_thread_kind(tap_thread_kind))
        tap_hole_type = g("tap_hole_type")
        if tap_hole_type:
            qs = qs.filter(tap_spec__hole_type=tap_hole_type)
        tap_tool_type = g("tap_tool_type")
        if tap_tool_type:
            qs = qs.filter(tap_spec__tap_type=tap_tool_type)
        tap_overall_length_raw = g("tap_overall_length_mm")
        if tap_overall_length_raw:
            tap_overall_length = _to_decimal(tap_overall_length_raw, Decimal("0"))
            if tap_overall_length > 0:
                qs = qs.filter(tap_spec__overall_length_mm=tap_overall_length)
        tap_cutting_length_raw = g("tap_cutting_length_mm")
        if tap_cutting_length_raw:
            tap_cutting_length = _to_decimal(tap_cutting_length_raw, Decimal("0"))
            if tap_cutting_length > 0:
                qs = qs.filter(tap_spec__cutting_length_mm=tap_cutting_length)
    elif category == "center_drill":
        center_diameter_raw = g("center_diameter_mm")
        if center_diameter_raw:
            center_diameter = _to_decimal(center_diameter_raw, Decimal("0"))
            if center_diameter > 0:
                qs = qs.filter(center_drill_spec__diameter_mm=center_diameter)
        center_overall_length_raw = g("center_overall_length_mm")
        if center_overall_length_raw:
            center_overall_length = _to_decimal(center_overall_length_raw, Decimal("0"))
            if center_overall_length > 0:
                qs = qs.filter(center_drill_spec__overall_length_mm=center_overall_length)
        center_angle_raw = g("center_angle_deg")
        if center_angle_raw:
            qs = qs.filter(center_drill_spec__angle_deg=center_angle_raw)
    elif category == "countersink":
        countersink_type_raw = g("countersink_type")
        if countersink_type_raw:
            qs = qs.filter(countersink_spec__countersink_type=countersink_type_raw)
        countersink_diameter_raw = g("countersink_diameter_mm")
        if countersink_diameter_raw:
            countersink_diameter = _to_decimal(countersink_diameter_raw, Decimal("0"))
            if countersink_diameter > 0:
                qs = qs.filter(countersink_spec__diameter_mm=countersink_diameter)
        countersink_angle_raw = g("countersink_angle_deg")
        if countersink_angle_raw:
            qs = qs.filter(countersink_spec__angle_deg=countersink_angle_raw)
        countersink_length_raw = g("countersink_overall_length_mm")
        if countersink_length_raw:
            countersink_length = _to_decimal(countersink_length_raw, Decimal("0"))
            if countersink_length > 0:
                qs = qs.filter(countersink_spec__overall_length_mm=countersink_length)
        countersink_flutes_raw = g("countersink_flutes_count")
        if countersink_flutes_raw:
            countersink_flutes = _to_int(countersink_flutes_raw, 0)
            if countersink_flutes > 0:
                qs = qs.filter(countersink_spec__flutes_count=countersink_flutes)
        countersink_size_raw = g("countersink_size_label")
        if countersink_size_raw:
            qs = qs.filter(countersink_spec__size_label__iexact=countersink_size_raw)
    elif category == "drill":
        drill_diameter_raw = g("drill_diameter_mm")
        if drill_diameter_raw:
            drill_diameter = _to_decimal(drill_diameter_raw, Decimal("0"))
            if drill_diameter > 0:
                qs = qs.filter(drill_spec__diameter_mm=drill_diameter)
        drill_overall_length_raw = g("drill_overall_length_mm")
        if drill_overall_length_raw:
            drill_overall_length = _to_decimal(drill_overall_length_raw, Decimal("0"))
            if drill_overall_length > 0:
                qs = qs.filter(drill_spec__overall_length_mm=drill_overall_length)
        drill_cutting_length_raw = g("drill_cutting_length_mm")
        if drill_cutting_length_raw:
            drill_cutting_length = _to_decimal(drill_cutting_length_raw, Decimal("0"))
            if drill_cutting_length > 0:
                qs = qs.filter(drill_spec__cutting_length_mm=drill_cutting_length)
        drill_angle_raw = g("drill_angle_deg")
        if drill_angle_raw:
            drill_angle = _to_decimal(drill_angle_raw, Decimal("0"))
            if drill_angle > 0:
                qs = qs.filter(drill_spec__angle_deg=drill_angle)
    elif category == "insert":
        ins_shape_raw = g("ins_shape")
        if ins_shape_raw:
            qs = qs.filter(insert_spec__insert_shape=ins_shape_raw)
        ins_relief_raw = g("ins_relief")
        if ins_relief_raw:
            qs = qs.filter(insert_spec__relief_angle=ins_relief_raw)
        ins_tolerance_raw = g("ins_tolerance")
        if ins_tolerance_raw:
            qs = qs.filter(insert_spec__tolerance_class=ins_tolerance_raw)
        ins_edge_code_raw = g("ins_edge_code")
        if ins_edge_code_raw:
            qs = qs.filter(insert_spec__cutting_edge_length_code=ins_edge_code_raw)
        ins_thickness_code_raw = g("ins_thickness_code")
        if ins_thickness_code_raw:
            qs = qs.filter(insert_spec__thickness_code=ins_thickness_code_raw)
        ins_nose_code_raw = g("ins_nose_code")
        if ins_nose_code_raw:
            qs = qs.filter(insert_spec__nose_radius_code=ins_nose_code_raw)
        ins_family_raw = g("ins_family")
        if ins_family_raw:
            qs = qs.filter(insert_spec__milling_family=ins_family_raw)
        ins_grade_raw = g("ins_grade")
        if ins_grade_raw:
            qs = qs.filter(insert_spec__chipbreaker_grade__iexact=ins_grade_raw)
        ins_iso_raw = g("ins_iso")
        if ins_iso_raw:
            qs = qs.filter(insert_spec__iso_designation__iexact=ins_iso_raw)
    elif category == "collet":
        collet_type_raw = g("collet_type")
        if collet_type_raw:
            qs = qs.filter(collet_spec__collet_type=collet_type_raw)
        collet_er_size_raw = g("collet_er_size")
        if collet_er_size_raw:
            qs = qs.filter(collet_spec__er_size=collet_er_size_raw)
        collet_clamp_range_raw = g("collet_clamp_range")
        if collet_clamp_range_raw:
            qs = qs.filter(collet_spec__clamp_range=collet_clamp_range_raw)
        collet_inner_diameter_raw = g("collet_inner_diameter")
        collet_square_size_raw = g("collet_square_size")
        if collet_inner_diameter_raw:
            qs = qs.filter(collet_spec__inner_diameter=collet_inner_diameter_raw)
        elif collet_square_size_raw:
            qs = qs.filter(collet_spec__inner_diameter=normalize_collet_er_g_inner_diameter(collet_square_size_raw))
        collet_thread_standard_raw = g("collet_thread_standard")
        if collet_thread_standard_raw:
            qs = qs.filter(collet_spec__thread_standard=collet_thread_standard_raw)
        collet_threading_use_raw = g("collet_threading_use")
        if collet_threading_use_raw:
            qs = qs.filter(collet_spec__threading_use=collet_threading_use_raw)
        collet_threading_series_raw = g("collet_threading_series")
        if collet_threading_series_raw:
            qs = qs.filter(collet_spec__threading_series=collet_threading_series_raw)

    if category not in ("collet", "body_tool") and "tool_material" not in ex and "tool_material_custom" not in ex:
        tool_material = _resolve_stock_tool_material(params)
        if tool_material:
            qs = qs.filter(tool_material=tool_material)
    if category not in ("collet", "body_tool") and "coating_type" not in ex:
        coating_type = g("coating_type")
        if coating_type:
            qs = qs.filter(coating_type=coating_type)
    if category not in ("collet", "body_tool") and "work_material" not in ex:
        work_material = g("work_material")
        if work_material:
            wm = work_material.strip()
            qs = qs.filter(
                Q(work_material=wm)
                | Q(work_material__startswith=f"{wm},")
                | Q(work_material__endswith=f",{wm}")
                | Q(work_material__contains=f",{wm},")
            )
    return qs


def _prune_stock_prefs_params(category: str, params: dict[str, str]) -> dict[str, str]:
    allow = _STOCK_GLOBAL_KEYS | _STOCK_KEYS_BY_CATEGORY.get(category, frozenset())
    return {k: (params.get(k) or "").strip() for k in _STOCK_FILTER_PARAM_KEYS if k in allow}


def _save_inventory_stock_filter_prefs(username: str, params: dict[str, str], *, category: str) -> None:
    store = _prune_stock_prefs_params(category, params)
    UserInventoryStockFilterPrefs.objects.update_or_create(username=username, defaults={"params": store})


def _norm_stock_decimal_str(raw: str) -> str:
    if not (raw or "").strip():
        return ""
    try:
        d = Decimal(str(raw).replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        return (raw or "").strip()
    try:
        d = d.normalize()
    except InvalidOperation:
        return (raw or "").strip()
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _norm_stock_int_filter_str(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    n = _to_int(s, -1)
    return str(n) if n >= 0 else s


def _sorted_unique_decimal_strings(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in values:
        if x is None:
            continue
        s = _norm_stock_decimal_str(str(x))
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    out.sort(key=lambda t: _to_decimal(t, Decimal("0")))
    return out


def _sorted_unique_int_strings(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in values:
        if x is None:
            continue
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        s = str(n)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    out.sort(key=lambda t: int(t))
    return out


def _fmt_unknown(v, prefix: str = "") -> str:
    if v is None or str(v) == "":
        return f"{prefix}неизв."
    return f"{prefix}{v}"


def _build_end_mill_name(diameter_mm, flutes_count, tool_material: str, work_material: str) -> str:
    tool_mat_label = dict(TOOL_MATERIAL_TYPES).get(tool_material, tool_material)
    work_mat_label = work_material_display_text(work_material) or work_material
    parts = [f"Фреза D{_fmt_unknown(diameter_mm)}", f"{_fmt_unknown(flutes_count)} кром."]
    if tool_mat_label:
        parts.append(tool_mat_label)
    if work_mat_label:
        parts.append(f"по {work_mat_label}")
    return " / ".join(parts)


def _build_tap_name(size_label: str, thread_standard: str, tap_type: str, hole_type: str) -> str:
    std_map = dict(THREAD_STANDARDS)
    ttype_map = dict(TAP_TOOL_TYPES)
    htype_map = dict(TAP_HOLE_TYPES)
    return f"{size_label} / {std_map.get(thread_standard, thread_standard)} / {ttype_map.get(tap_type, tap_type)} / {htype_map.get(hole_type, hole_type)}"


def _build_center_drill_name(diameter_mm, angle_deg: str) -> str:
    return f"Центровка D{_fmt_unknown(diameter_mm)} / {angle_deg or '60'}°"


def _build_countersink_name(countersink_type: str, diameter_mm, angle_deg: str, size_label: str) -> str:
    type_label = dict(COUNTERSINK_TYPES).get(countersink_type, countersink_type or "машинный")
    size_part = f" / {size_label}" if size_label else ""
    return f"Зенкер {type_label} D{_fmt_unknown(diameter_mm)} / {angle_deg or '90'}°{size_part}"


def _build_drill_name(diameter_mm, overall_length_mm, cutting_length_mm, angle_deg) -> str:
    return (
        f"Сверло D{_fmt_unknown(diameter_mm)} / "
        f"L{_fmt_unknown(overall_length_mm)} / "
        f"Lc{_fmt_unknown(cutting_length_mm)} / "
        f"{_fmt_unknown(angle_deg)}°"
    )


def _milling_family_from_request(data) -> str:
    sel = (data.get("ins_family") or data.get("milling_family") or "").strip()
    if sel == INSERT_FAMILY_OTHER:
        return normalize_milling_family(data.get("ins_family_custom") or "")
    return normalize_milling_family(sel)


def _body_insert_family_from_row(data) -> str:
    sel = (data.get("bt_insert_family") or data.get("ins_family") or "").strip()
    if sel == INSERT_FAMILY_OTHER:
        return normalize_milling_family(data.get("bt_insert_family_custom") or data.get("ins_family_custom") or "")
    return normalize_milling_family(sel)


def _body_insert_size_from_row(data) -> str:
    sel = (data.get("bt_insert_size") or "").strip()
    if sel == INSERT_SIZE_OTHER:
        return normalize_insert_size(data.get("bt_insert_size_custom") or "")
    return normalize_insert_size(sel)


def _body_tool_name_from_spec(bt) -> str:
    return build_body_tool_display_name(
        family=bt.family,
        cutter_type=bt.cutter_type,
        diameter_mm=bt.diameter_mm,
        teeth_count=bt.teeth_count,
        insert_family=bt.insert_family,
        insert_size=bt.insert_size,
        brand=bt.brand,
    )


def _merged_milling_insert_families():
    known = []
    seen = set()
    extra_vals = set()
    try:
        extra_vals.update(
            BodyToolSpec.objects.exclude(insert_family="")
            .values_list("insert_family", flat=True)
            .distinct()
        )
        extra_vals.update(
            InsertSpec.objects.exclude(milling_family="")
            .values_list("milling_family", flat=True)
            .distinct()
        )
    except Exception:
        extra_vals = set()
    catalog = {k for k, _ in MILLING_INSERT_FAMILIES if k}
    extras = sorted(v.strip().upper() for v in extra_vals if v and str(v).strip().upper() not in catalog)
    for key, label in MILLING_INSERT_FAMILIES:
        if key == INSERT_FAMILY_OTHER:
            for extra in extras:
                if extra not in seen:
                    known.append((extra, extra))
                    seen.add(extra)
        if key in seen:
            continue
        known.append((key, label))
        if key:
            seen.add(key)
    return known


def _insert_spec_fields_from_mapping(data: dict) -> dict:
    return {
        "insert_shape": (data.get("ins_shape") or data.get("insert_shape") or "C").strip()[:1] or "C",
        "relief_angle": (data.get("ins_relief") or data.get("relief_angle") or "N").strip()[:1] or "N",
        "tolerance_class": (data.get("ins_tolerance") or data.get("tolerance_class") or "M").strip()[:1] or "M",
        "mounting_chip": (data.get("ins_mounting") or data.get("mounting_chip") or "G").strip()[:1] or "G",
        "cutting_edge_length_code": (data.get("ins_edge_code") or data.get("cutting_edge_length_code") or "").strip()[:2],
        "thickness_code": (data.get("ins_thickness_code") or data.get("thickness_code") or "").strip()[:2],
        "nose_radius_code": (data.get("ins_nose_code") or data.get("nose_radius_code") or "").strip()[:2],
        "milling_family": _milling_family_from_request(data),
        "chipbreaker_grade": (data.get("ins_grade") or data.get("chipbreaker_grade") or "").strip()[:40],
        "machining_application": normalize_insert_machining_apps(
            data.get("ins_machining_app") or data.get("machining_application")
        ),
    }


def _find_insert_tool_match(tool_material, coating_type, work_material, main_diameter_mm, spec_fields: dict):
    return (
        ToolItem.objects.select_for_update()
        .filter(
            category="insert",
            tool_material=tool_material,
            coating_type=coating_type,
            work_material=work_material,
            main_diameter_mm=main_diameter_mm,
            insert_spec__insert_shape=spec_fields["insert_shape"],
            insert_spec__cutting_edge_length_code=spec_fields["cutting_edge_length_code"],
            insert_spec__thickness_code=spec_fields["thickness_code"],
            insert_spec__nose_radius_code=spec_fields["nose_radius_code"],
            insert_spec__milling_family=spec_fields["milling_family"],
            insert_spec__chipbreaker_grade=spec_fields["chipbreaker_grade"],
            insert_spec__machining_application=spec_fields["machining_application"],
        )
        .first()
    )


def _create_insert_tool(quantity, tool_material, coating_type, work_material, main_diameter_mm, spec_fields: dict) -> ToolItem:
    spec = InsertSpec(**spec_fields)
    spec.sync_derived_fields()
    tool = ToolItem.objects.create(
        category="insert",
        name=build_insert_display_name(spec.iso_designation, spec.milling_family, spec.chipbreaker_grade),
        tool_material=tool_material,
        coating_type=coating_type,
        work_material=work_material,
        main_diameter_mm=main_diameter_mm,
        quantity=quantity,
    )
    spec.tool = tool
    spec.save()
    return tool


def _collet_spec_fields_from_row(row: dict) -> dict:
    aa_raw = row.get("collet_high_precision_aa") or row.get("high_precision_aa")
    return {
        "collet_type": normalize_collet_type(row.get("collet_type")),
        "er_size": normalize_er_collet_size(row.get("collet_er_size") or row.get("er_size")),
        "clamp_range": normalize_er_clamp_range(row.get("collet_clamp_range") or row.get("clamp_range")),
        "high_precision_aa": str(aa_raw).lower() in ("1", "true", "on", "yes"),
        "square_size": "",
        "inner_diameter": normalize_collet_er_g_inner_diameter(
            row.get("collet_inner_diameter") or row.get("collet_square_size") or row.get("inner_diameter")
        ),
        "thread_standard": normalize_collet_thread_standard(
            row.get("collet_thread_standard") or row.get("thread_standard")
        ),
        "threading_use": normalize_collet_threading_use(
            row.get("collet_threading_use") or row.get("threading_use")
        ),
        "threading_series": normalize_collet_threading_series(
            row.get("collet_threading_series") or row.get("threading_series")
        ),
        "thread_size_label": (row.get("collet_thread_size") or row.get("thread_size_label") or "").strip()[:32],
        "diameter_mm": _to_decimal_or_none(row.get("collet_diameter_mm") or row.get("diameter_mm")),
        "size_label": (row.get("collet_size_label") or row.get("size_label") or "").strip()[:64],
    }


def _find_collet_tool_match(spec_fields: dict):
    return (
        ToolItem.objects.select_for_update()
        .filter(
            category="collet",
            tool_material="",
            coating_type="none",
            work_material="",
            collet_spec__collet_type=spec_fields["collet_type"],
            collet_spec__er_size=spec_fields["er_size"],
            collet_spec__clamp_range=spec_fields["clamp_range"],
            collet_spec__high_precision_aa=spec_fields["high_precision_aa"],
            collet_spec__inner_diameter=spec_fields["inner_diameter"],
            collet_spec__thread_standard=spec_fields["thread_standard"],
            collet_spec__threading_use=spec_fields["threading_use"],
            collet_spec__threading_series=spec_fields["threading_series"],
            collet_spec__thread_size_label=spec_fields["thread_size_label"],
            collet_spec__diameter_mm=spec_fields["diameter_mm"],
            collet_spec__size_label=spec_fields["size_label"],
        )
        .first()
    )


def _create_collet_tool(quantity, spec_fields: dict) -> ToolItem:
    name = build_collet_display_name(
        collet_type=spec_fields["collet_type"],
        er_size=spec_fields["er_size"],
        clamp_range=spec_fields["clamp_range"],
        high_precision_aa=spec_fields["high_precision_aa"],
        square_size=spec_fields["square_size"],
        inner_diameter=spec_fields["inner_diameter"],
        thread_standard=spec_fields["thread_standard"],
        threading_use=spec_fields["threading_use"],
        threading_series=spec_fields["threading_series"],
        thread_size_label=spec_fields["thread_size_label"],
        diameter_mm=spec_fields["diameter_mm"],
        size_label=spec_fields["size_label"],
    )
    tool = ToolItem.objects.create(
        category="collet",
        name=name,
        tool_material="",
        coating_type="none",
        work_material="",
        quantity=quantity,
    )
    ColletSpec.objects.create(tool=tool, **spec_fields)
    return tool


@biota_login_required
@inventory_route_nav_access_required
@write_permission_required
@require_http_methods(["GET", "POST"])
def inventory_view(request):
    action = request.POST.get("action") if request.method == "POST" else ""
    panel = (request.GET.get("panel") or "stock").strip()
    if panel not in {"stock", "history", "issue", "arrival", "issue_outcome", "purchases", "analysis", "defects", "payroll", "employees"}:
        panel = "stock"

    username = biota_user(request) or "Неизвестный пользователь"
    is_admin_user = _is_admin(username)
    can_manage_stock = is_admin_user or inventory_stock_manage_for_user(username)
    perms = nav_permissions_for_user(username)
    can_defects = perms.get("defects", True)
    can_payroll = perms.get("payroll", True)
    can_employees = perms.get("employees", True)
    if is_admin_user:
        can_defects = can_payroll = can_employees = True
    if panel == "defects" and not can_defects:
        messages.warning(request, "У вас нет доступа к разделу «Учёт брака».")
        return redirect(reverse("inventory"))
    if panel == "payroll" and not can_payroll:
        messages.warning(request, "У вас нет доступа к разделу «Расчёт ЗП».")
        return redirect(reverse("inventory"))
    if panel == "employees" and not can_employees:
        messages.warning(request, "У вас нет доступа к разделу «Сотрудники».")
        return redirect(reverse("inventory"))

    if panel == "employees" and not can_employees:
        messages.warning(request, "У вас нет доступа к разделу «Сотрудники».")
        return redirect(reverse("inventory"))

    if action == "save_watch_template":
        name = (request.POST.get("watch_name") or "").strip()[:120]
        category = (request.POST.get("watch_category") or "").strip()
        group_field = normalize_group_field(category, (request.POST.get("watch_group_field") or "").strip())
        group_value = (request.POST.get("watch_group_value") or "").strip()[:80]
        min_qty = max(1, min(9999, _to_int(request.POST.get("watch_min_qty"), 5)))
        notes = (request.POST.get("watch_notes") or "").strip()[:255]
        if not name or category not in _INVENTORY_CATEGORIES or not group_value:
            messages.error(request, "Укажите название, тип инструмента и значение для контроля.")
            return _analysis_panel_redirect(request)
        sort_order = (
            InventoryWatchTemplate.objects.filter(username=username, is_active=True).count() + 1
        )
        InventoryWatchTemplate.objects.create(
            username=username,
            name=name,
            category=category,
            group_field=group_field,
            group_value=group_value,
            min_qty=min_qty,
            sort_order=sort_order,
            notes=notes,
        )
        messages.success(request, f"Добавлено в контроль: {name}")
        return _analysis_panel_redirect(request, analysis_category=category)

    if action == "update_watch_template":
        tpl_id = _to_int(request.POST.get("watch_id"), 0)
        tpl = InventoryWatchTemplate.objects.filter(id=tpl_id, username=username, is_active=True).first()
        if not tpl:
            messages.error(request, "Строка контроля не найдена.")
            return _analysis_panel_redirect(request)
        tpl.min_qty = max(1, min(9999, _to_int(request.POST.get("watch_min_qty"), tpl.min_qty)))
        tpl.name = (request.POST.get("watch_name") or tpl.name).strip()[:120]
        tpl.notes = (request.POST.get("watch_notes") or tpl.notes).strip()[:255]
        tpl.save(update_fields=["min_qty", "name", "notes", "updated_at"])
        messages.success(request, "Контроль обновлён.")
        return _analysis_panel_redirect(request, analysis_category=tpl.category)

    if action == "delete_watch_template":
        tpl_id = _to_int(request.POST.get("watch_id"), 0)
        deleted, _ = InventoryWatchTemplate.objects.filter(id=tpl_id, username=username).delete()
        if deleted:
            messages.success(request, "Строка контроля удалена.")
        else:
            messages.error(request, "Строка контроля не найдена.")
        return _analysis_panel_redirect(request)

    if action == "rollback_stock_movement":
        if not is_admin_user:
            messages.error(request, "Откат движений доступен только администратору.")
            return _history_panel_redirect(request)
        mid = _to_int(request.POST.get("movement_id"), 0)
        if mid <= 0:
            messages.error(request, "Не указана запись для отката.")
            return _history_panel_redirect(request)
        ok_rb, err_rb = _rollback_stock_movement(mid, username)
        if ok_rb:
            messages.success(request, "Движение откатано, запись добавлена в историю.")
        else:
            messages.error(request, err_rb or "Не удалось выполнить откат.")
        return _history_panel_redirect(request)

    employee_options = []
    employee_department_map = {}
    employee_table_rows: list[dict] = []
    if panel == "defects" or action in {"create_defect_record", "update_defect_record"}:
        try:
            cfg = biota_db.db_config()
            employees_df = employees_df_for_nav(username, "defects", biota_db.load_employees(cfg))
            if not employees_df.empty:
                prepared: list[tuple[str, str, str, str]] = []
                base_counts: dict[str, int] = {}
                for _, row in employees_df.iterrows():
                    base_label = employee_label_row(row)
                    if not base_label or base_label == "Без имени":
                        continue
                    dept = str(row.get("department_name") or "").strip()
                    last = str(row.get("last_name") or "").strip()
                    first = str(row.get("first_name") or "").strip()
                    full_name = " ".join(p for p in (last, first) if p)
                    emp_code = str(row.get("emp_code") or "").strip()
                    prepared.append((base_label, full_name, emp_code, dept))
                    base_counts[base_label] = base_counts.get(base_label, 0) + 1

                for base_label, full_name, emp_code, dept in prepared:
                    label = base_label
                    if base_counts.get(base_label, 0) > 1:
                        if full_name and full_name != base_label:
                            label = f"{base_label} ({full_name})"
                        elif emp_code:
                            label = f"{base_label} [{emp_code}]"
                    # На случай редких коллизий (однофамильцы с одинаковым именем)
                    if label in employee_department_map and emp_code:
                        label = f"{label} [{emp_code}]"
                    if label not in employee_department_map:
                        employee_department_map[label] = dept
                employee_options = sorted(employee_department_map.keys())
        except Exception:
            employee_options = []
            employee_department_map = {}

    if panel == "employees":
        try:
            cfg = biota_db.db_config()
            emp_df = employees_df_for_nav(username, "employees", biota_db.load_employees(cfg))
            if not emp_df.empty:
                codes = [normalize_emp_code(str(x)) for x in emp_df["emp_code"].tolist() if normalize_emp_code(str(x))]
                profile_by_code = {
                    p.emp_code: p
                    for p in EmployeePayrollProfile.objects.filter(emp_code__in=codes)
                }
                rows: list[dict] = []
                for _, row in emp_df.iterrows():
                    emp_code = normalize_emp_code(str(row.get("emp_code") or ""))
                    if not emp_code:
                        continue
                    prof = profile_by_code.get(emp_code)
                    rows.append(
                        {
                            "emp_code": emp_code,
                            "label": (employee_label_row(row) or "").strip() or "—",
                            "last_name": str(row.get("last_name") or "").strip(),
                            "first_name": str(row.get("first_name") or "").strip(),
                            "department_name": str(row.get("department_name") or "").strip(),
                            "position_name": str(row.get("position_name") or "").strip(),
                            "area_name": str(row.get("area_name") or "").strip(),
                            "shift_hours": prof.shift_hours if prof else None,
                            "hourly_rate_day": prof.hourly_rate_day if prof and prof.hourly_rate_day is not None else None,
                            "hourly_rate_night": prof.hourly_rate_night if prof and prof.hourly_rate_night is not None else None,
                        }
                    )
                employee_table_rows = sorted(rows, key=lambda r: (r["label"].lower(), r["emp_code"]))
        except Exception:
            employee_table_rows = []

    if action == "add_end_mill":
        diameter_mm = _to_decimal(request.POST.get("diameter_mm"), Decimal("0"))
        overall_length_mm = _to_decimal(request.POST.get("overall_length_mm"), Decimal("0"))
        cutting_length_mm = _to_decimal(request.POST.get("cutting_length_mm"), Decimal("0"))
        flutes_count = _to_int(request.POST.get("flutes_count"), 0)
        quantity = _to_int(request.POST.get("quantity"), 0)
        tool_material = (request.POST.get("tool_material") or "").strip()
        coating_type = (request.POST.get("coating_type") or "none").strip()
        work_material = normalize_work_material_codes(request.POST.get("work_material"))
        main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        if diameter_mm <= 0 or overall_length_mm <= 0 or cutting_length_mm <= 0 or flutes_count <= 0 or quantity <= 0:
            messages.error(request, "Для фрезы заполните параметры корректно (числа больше нуля).")
            return redirect("inventory")
        with transaction.atomic():
            tool = ToolItem.objects.create(
                category="end_mill",
                name=_build_end_mill_name(diameter_mm, flutes_count, tool_material, work_material),
                tool_material=tool_material,
                coating_type=coating_type,
                work_material=work_material,
                main_diameter_mm=main_diameter_mm,
                quantity=quantity,
            )
            EndMillSpec.objects.create(
                tool=tool,
                diameter_mm=diameter_mm,
                overall_length_mm=overall_length_mm,
                cutting_length_mm=cutting_length_mm,
                flutes_count=flutes_count,
            )
        messages.success(request, "Фреза добавлена в склад.")
        return redirect("inventory")

    if action == "add_tap":
        thread_standard = (request.POST.get("thread_standard") or "metric").strip()
        thread_kind = normalize_thread_kind(request.POST.get("thread_kind"))
        size_label = (request.POST.get("size_label") or "").strip()
        pitch_mm = _to_decimal(request.POST.get("pitch_mm"), Decimal("0"))
        tpi = _to_int(request.POST.get("tpi"), 0) or None
        hole_type = (request.POST.get("hole_type") or "any").strip()
        tap_type = (request.POST.get("tap_type") or "cutting").strip()
        overall_length_mm = _to_decimal(request.POST.get("overall_length_mm"), Decimal("0"))
        cutting_length_mm = _to_decimal(request.POST.get("cutting_length_mm"), Decimal("0"))
        quantity = _to_int(request.POST.get("quantity"), 0)
        tool_material = (request.POST.get("tool_material") or "").strip()
        coating_type = (request.POST.get("coating_type") or "none").strip()
        work_material = normalize_work_material_codes(request.POST.get("work_material"))
        main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        if not size_label or overall_length_mm <= 0 or cutting_length_mm <= 0 or quantity <= 0:
            messages.error(request, "Для метчика заполните размер, длины и количество.")
            return redirect("inventory")
        with transaction.atomic():
            tool = ToolItem.objects.create(
                category="tap",
                name=_build_tap_name(size_label, thread_standard, tap_type, hole_type),
                tool_material=tool_material,
                coating_type=coating_type,
                work_material=work_material,
                main_diameter_mm=main_diameter_mm,
                quantity=quantity,
            )
            TapSpec.objects.create(
                tool=tool,
                thread_standard=thread_standard,
                thread_kind=thread_kind,
                size_label=size_label,
                pitch_mm=pitch_mm if pitch_mm > 0 else None,
                tpi=tpi,
                hole_type=hole_type,
                tap_type=tap_type,
                overall_length_mm=overall_length_mm,
                cutting_length_mm=cutting_length_mm,
            )
        messages.success(request, "Метчик добавлен в склад.")
        return redirect("inventory")

    if action == "move_stock":
        movement_type = (request.POST.get("movement_type") or "").strip()
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        qty = _to_int(request.POST.get("quantity"), 0)
        employee_name = (request.POST.get("employee_name") or "").strip()
        movement_date_raw = (request.POST.get("movement_date") or "").strip()
        comment = (request.POST.get("comment") or "").strip()
        try:
            movement_date = date.fromisoformat(movement_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату движения.")
            return redirect("inventory")
        if movement_type not in {"issue", "restock", "writeoff"} or tool_id <= 0 or qty <= 0:
            messages.error(request, "Проверьте тип операции, инструмент и количество.")
            return redirect("inventory")
        if movement_type == "writeoff" and not comment:
            messages.error(request, "Для списания обязательно укажите причину в комментарии.")
            return redirect("inventory")

        with transaction.atomic():
            tool = ToolItem.objects.select_for_update().get(id=tool_id)
            if movement_type in {"issue", "writeoff"}:
                if tool.quantity < qty:
                    messages.error(request, f"Недостаточно остатков: доступно {tool.quantity}.")
                    return redirect("inventory")
                tool.quantity -= qty
            else:
                tool.quantity += qty
            tool.save(update_fields=["quantity", "updated_at"])
            StockMovement.objects.create(
                movement_type=movement_type,
                tool=tool,
                quantity=qty,
                employee_name=employee_name,
                movement_date=movement_date,
                comment=comment,
                created_by_account=username,
            )
        messages.success(request, "Движение склада сохранено.")
        return redirect("inventory")

    if action == "delete_tool_item":
        if not can_manage_stock:
            messages.error(request, "Удалять позиции склада могут только администратор или пользователь с выданным правом.")
            return redirect(f"{request.path}?panel=stock")
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        if tool_id <= 0:
            messages.error(request, "Позиция склада не найдена.")
            return redirect(f"{request.path}?panel=stock")
        tool = ToolItem.objects.filter(id=tool_id).first()
        if not tool:
            messages.error(request, "Позиция склада не найдена.")
            return redirect(f"{request.path}?panel=stock")
        if tool.is_deleted:
            messages.info(request, "Позиция уже помечена как удаленная администратором.")
            return redirect(f"{request.path}?panel=stock")
        tool.is_deleted = True
        tool.deleted_at = timezone.now()
        tool.deleted_by = username
        tool.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])
        _log_inventory_stock_event(
            actor=username,
            event_type=InventoryStockEvent.EVENT_TOOL_DELETE,
            tool=tool,
            summary=f"Помечено удаление позиции: {tool.name} (id {tool.id})",
            details={"tool_id": tool.id},
        )
        messages.success(request, "Позиция помечена как удаленная администратором.")
        return redirect(f"{request.path}?panel=stock")

    if action == "update_tool_item":
        if not can_manage_stock:
            messages.error(request, "Изменять позиции склада могут только администратор или пользователь с выданным правом.")
            return redirect(f"{request.path}?panel=stock")
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        tool = (
            ToolItem.objects.select_related(
                "end_mill_spec",
                "body_tool_spec",
                "tap_spec",
                "center_drill_spec",
                "countersink_spec",
                "drill_spec",
                "insert_spec",
            )
            .filter(id=tool_id, is_deleted=False)
            .first()
        )
        if not tool:
            messages.error(request, "Позиция склада не найдена.")
            return redirect(f"{request.path}?panel=stock")

        tool.tool_material = (request.POST.get("tool_material") or "").strip()
        tool.coating_type = (request.POST.get("coating_type") or "none").strip()
        tool.work_material = normalize_work_material_codes(request.POST.get("work_material"))
        tool.main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        tool.quantity = max(0, _to_int(request.POST.get("quantity"), tool.quantity))

        if tool.category == "end_mill" and tool.end_mill_spec:
            tool.end_mill_spec.mill_type = (request.POST.get("mill_type") or "end").strip()
            tool.end_mill_spec.diameter_mm = _to_decimal_or_none(request.POST.get("em_diameter_mm"))
            tool.end_mill_spec.corner_radius_mm = _to_decimal_or_none(request.POST.get("em_corner_radius_mm"))
            tool.end_mill_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("em_overall_length_mm"))
            tool.end_mill_spec.cutting_length_mm = _to_decimal_or_none(request.POST.get("em_cutting_length_mm"))
            tool.end_mill_spec.flutes_count = _to_int_or_none(request.POST.get("em_flutes_count"))
            tool.end_mill_spec.save()
        elif tool.category == "body_tool" and tool.body_tool_spec:
            bt = tool.body_tool_spec
            bt.family = normalize_body_tool_family(request.POST.get("body_family"))
            bt.cutter_type = normalize_indexable_mill_cutter(request.POST.get("body_cutter"))
            bt.diameter_mm = _to_decimal_or_none(request.POST.get("bt_diameter_mm"))
            bt.overall_length_mm = _to_decimal_or_none(request.POST.get("bt_overall_length_mm"))
            bt.cutting_length_mm = _to_decimal_or_none(request.POST.get("bt_cutting_length_mm"))
            bt.teeth_count = _to_int_or_none(request.POST.get("bt_teeth_count"))
            bt.coupling = normalize_body_tool_coupling(request.POST.get("bt_coupling"))
            bt.insert_family = _body_insert_family_from_row(request.POST)
            bt.insert_size = _body_insert_size_from_row(request.POST)
            bt.mount_diameter_mm = _to_decimal_or_none(request.POST.get("bt_mount_diameter_mm"))
            bt.coolant_through = _to_bool(request.POST.get("bt_coolant"))
            bt.ap_max_mm = _to_decimal_or_none(request.POST.get("bt_ap_max_mm"))
            bt.brand = (request.POST.get("bt_brand") or "").strip()[:80]
            bt.shank_type = normalize_body_tool_shank(request.POST.get("bt_shank_type"))
            bt.hs_body_style = normalize_high_speed_body_style(request.POST.get("bt_hs_body_style"))
            bt.has_purpose = _to_bool(request.POST.get("bt_has_purpose"))
            bt.corner_radius_mm = _to_decimal_or_none(request.POST.get("bt_corner_radius_mm"))
            angle_raw = (request.POST.get("bt_angle_deg") or "").strip()
            ang_val, ang_var = parse_angle_or_variable(angle_raw)
            if ang_var:
                bt.variable_angle = True
                bt.approach_angle_deg = None
            else:
                bt.variable_angle = _to_bool(request.POST.get("bt_variable_angle"))
                bt.approach_angle_deg = _to_decimal_or_none(ang_val if ang_val is not None else angle_raw)
                if bt.variable_angle:
                    bt.approach_angle_deg = None
            derived = coupling_from_shank(bt.shank_type)
            if derived:
                bt.coupling = derived
            bt.size_label = ""
            if bt.cutter_type == "ball":
                bt.insert_compat = (request.POST.get("bt_insert_compat") or "").strip()[:80]
                bt.mount_thread = ""
                bt.insert_family = ""
                bt.insert_size = ""
                bt.approach_angle_deg = None
                bt.variable_angle = False
                bt.ap_max_mm = None
                bt.hs_body_style = ""
                bt.has_purpose = False
                bt.corner_radius_mm = None
            elif bt.cutter_type == "modular_head":
                bt.insert_compat = (request.POST.get("bt_insert_compat") or "").strip()[:80]
                bt.mount_thread = normalize_modular_head_thread(request.POST.get("bt_mount_thread"))
                bt.coupling = "modular"
                bt.shank_type = ""
                bt.insert_family = ""
                bt.insert_size = ""
                bt.overall_length_mm = None
                bt.cutting_length_mm = None
                bt.approach_angle_deg = None
                bt.variable_angle = False
                bt.ap_max_mm = None
                bt.hs_body_style = ""
                bt.has_purpose = False
                bt.corner_radius_mm = None
            else:
                bt.insert_compat = ""
                bt.mount_thread = ""
            bt.save()
            tool.name = _body_tool_name_from_spec(bt)
        elif tool.category == "tap" and tool.tap_spec:
            tool.tap_spec.thread_standard = (request.POST.get("thread_standard") or "metric").strip()
            tool.tap_spec.thread_kind = normalize_thread_kind(request.POST.get("thread_kind"))
            tool.tap_spec.size_label = (request.POST.get("size_label") or "").strip()
            tool.tap_spec.pitch_mm = _to_decimal_or_none(request.POST.get("tap_pitch_mm"))
            tool.tap_spec.tpi = _to_int_or_none(request.POST.get("tap_tpi"))
            tool.tap_spec.hole_type = (request.POST.get("hole_type") or "any").strip()
            tool.tap_spec.tap_type = (request.POST.get("tap_type") or "cutting").strip()
            tool.tap_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("tap_overall_length_mm"))
            tool.tap_spec.cutting_length_mm = _to_decimal_or_none(request.POST.get("tap_cutting_length_mm"))
            tool.tap_spec.save()
        elif tool.category == "center_drill" and tool.center_drill_spec:
            tool.center_drill_spec.diameter_mm = _to_decimal_or_none(request.POST.get("cd_diameter_mm"))
            tool.center_drill_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("cd_overall_length_mm"))
            tool.center_drill_spec.angle_deg = (request.POST.get("cd_angle_deg") or "60").strip()
            tool.center_drill_spec.save()
        elif tool.category == "countersink" and tool.countersink_spec:
            tool.countersink_spec.countersink_type = (request.POST.get("cs_type") or "machine").strip()
            tool.countersink_spec.diameter_mm = _to_decimal_or_none(request.POST.get("cs_diameter_mm"))
            tool.countersink_spec.angle_deg = (request.POST.get("cs_angle_deg") or "90").strip()
            tool.countersink_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("cs_overall_length_mm"))
            tool.countersink_spec.flutes_count = _to_int_or_none(request.POST.get("cs_flutes_count"))
            tool.countersink_spec.size_label = (request.POST.get("cs_size_label") or "").strip()
            tool.countersink_spec.save()
        elif tool.category == "drill" and tool.drill_spec:
            tool.drill_spec.diameter_mm = _to_decimal_or_none(request.POST.get("dr_diameter_mm"))
            tool.drill_spec.overall_length_mm = _to_decimal_or_none(request.POST.get("dr_overall_length_mm"))
            tool.drill_spec.cutting_length_mm = _to_decimal_or_none(request.POST.get("dr_cutting_length_mm"))
            tool.drill_spec.angle_deg = _to_decimal_or_none(request.POST.get("dr_angle_deg"))
            tool.drill_spec.save()
        elif tool.category == "insert" and tool.insert_spec:
            ins = tool.insert_spec
            ins.insert_shape = (request.POST.get("ins_shape") or ins.insert_shape or "C").strip()[:1]
            ins.relief_angle = (request.POST.get("ins_relief") or ins.relief_angle or "N").strip()[:1]
            ins.tolerance_class = (request.POST.get("ins_tolerance") or ins.tolerance_class or "M").strip()[:1]
            ins.mounting_chip = (request.POST.get("ins_mounting") or ins.mounting_chip or "G").strip()[:1]
            ins.cutting_edge_length_code = (request.POST.get("ins_edge_code") or ins.cutting_edge_length_code or "").strip()[:2]
            ins.thickness_code = (request.POST.get("ins_thickness_code") or ins.thickness_code or "").strip()[:2]
            ins.nose_radius_code = (request.POST.get("ins_nose_code") or ins.nose_radius_code or "").strip()[:2]
            ins.milling_family = _milling_family_from_request(request.POST) or normalize_milling_family(ins.milling_family)
            ins.chipbreaker_grade = (request.POST.get("ins_grade") or ins.chipbreaker_grade or "").strip()[:40]
            ins.save()
            tool.name = build_insert_display_name(ins.iso_designation, ins.milling_family, ins.chipbreaker_grade)

        tool.save()
        _log_inventory_stock_event(
            actor=username,
            event_type=InventoryStockEvent.EVENT_TOOL_EDIT,
            tool=tool,
            summary=f"Обновление карточки инструмента: {tool.name} (id {tool.id})",
            details={"tool_id": tool.id, "category": tool.category},
        )
        messages.success(request, "Данные инструмента обновлены.")
        return redirect(f"{request.path}?panel=stock&category={tool.category}")

    if action == "update_tool_cell":
        if not can_manage_stock:
            return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        field = (request.POST.get("field") or "").strip()
        value_raw = (request.POST.get("value") or "").strip()
        tool = (
            ToolItem.objects.select_related(
                "end_mill_spec",
                "body_tool_spec",
                "tap_spec",
                "center_drill_spec",
                "countersink_spec",
                "drill_spec",
                "insert_spec",
                "collet_spec",
            )
            .filter(id=tool_id, is_deleted=False)
            .first()
        )
        if not tool:
            return JsonResponse({"ok": False, "error": "Позиция не найдена."}, status=404)

        common_ok = False
        if field == "main_diameter_mm":
            tool.main_diameter_mm = _to_decimal_or_none(value_raw)
            tool.save(update_fields=["main_diameter_mm", "updated_at"])
            common_ok = True
        elif field == "tool_material":
            tool.tool_material = (value_raw or "")[:80]
            _register_tool_material_extra(tool.tool_material)
            tool.save(update_fields=["tool_material", "updated_at"])
            common_ok = True
        elif field == "coating_type":
            tool.coating_type = value_raw or "none"
            tool.save(update_fields=["coating_type", "updated_at"])
            common_ok = True
        elif field == "work_material":
            tool.work_material = normalize_work_material_codes(value_raw)
            tool.save(update_fields=["work_material", "updated_at"])
            common_ok = True
        elif field == "quantity":
            tool.quantity = max(0, _to_int(value_raw, tool.quantity))
            tool.save(update_fields=["quantity", "updated_at"])
            common_ok = True

        if not common_ok:
            cat = tool.category
            if cat == "end_mill" and tool.end_mill_spec:
                em = tool.end_mill_spec
                if field == "mill_type":
                    em.mill_type = value_raw or "end"
                    em.save(update_fields=["mill_type"])
                elif field == "em_diameter_mm":
                    em.diameter_mm = _to_decimal_or_none(value_raw)
                    em.save(update_fields=["diameter_mm"])
                elif field == "em_corner_radius_mm":
                    em.corner_radius_mm = _to_decimal_or_none(value_raw)
                    em.save(update_fields=["corner_radius_mm"])
                elif field == "em_overall_length_mm":
                    em.overall_length_mm = _to_decimal_or_none(value_raw)
                    em.save(update_fields=["overall_length_mm"])
                elif field == "em_cutting_length_mm":
                    em.cutting_length_mm = _to_decimal_or_none(value_raw)
                    em.save(update_fields=["cutting_length_mm"])
                elif field == "em_flutes_count":
                    em.flutes_count = _to_int_or_none(value_raw)
                    em.save(update_fields=["flutes_count"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
            elif cat == "body_tool" and tool.body_tool_spec:
                bt = tool.body_tool_spec
                if field == "body_family":
                    bt.family = normalize_body_tool_family(value_raw)
                    bt.save(update_fields=["family"])
                elif field == "body_cutter":
                    bt.cutter_type = normalize_indexable_mill_cutter(value_raw)
                    bt.save(update_fields=["cutter_type"])
                elif field == "bt_diameter_mm":
                    bt.diameter_mm = _to_decimal_or_none(value_raw)
                    bt.save(update_fields=["diameter_mm"])
                elif field == "bt_overall_length_mm":
                    bt.overall_length_mm = _to_decimal_or_none(value_raw)
                    bt.save(update_fields=["overall_length_mm"])
                elif field == "bt_cutting_length_mm":
                    bt.cutting_length_mm = _to_decimal_or_none(value_raw)
                    bt.save(update_fields=["cutting_length_mm"])
                elif field == "bt_teeth_count":
                    bt.teeth_count = _to_int_or_none(value_raw)
                    bt.save(update_fields=["teeth_count"])
                elif field == "bt_coupling":
                    bt.coupling = normalize_body_tool_coupling(value_raw)
                    bt.save(update_fields=["coupling"])
                elif field == "bt_insert_family":
                    bt.insert_family = normalize_milling_family(value_raw)
                    bt.save(update_fields=["insert_family"])
                elif field == "bt_insert_size":
                    bt.insert_size = normalize_insert_size(value_raw)
                    bt.save(update_fields=["insert_size"])
                elif field == "bt_mount_diameter_mm":
                    bt.mount_diameter_mm = _to_decimal_or_none(value_raw)
                    bt.save(update_fields=["mount_diameter_mm"])
                elif field == "bt_coolant":
                    bt.coolant_through = _to_bool(value_raw)
                    bt.save(update_fields=["coolant_through"])
                elif field == "bt_ap_max_mm":
                    bt.ap_max_mm = _to_decimal_or_none(value_raw)
                    bt.save(update_fields=["ap_max_mm"])
                elif field == "bt_angle_deg":
                    ang_val, ang_var = parse_angle_or_variable(value_raw)
                    if ang_var:
                        bt.variable_angle = True
                        bt.approach_angle_deg = None
                        bt.save(update_fields=["approach_angle_deg", "variable_angle"])
                    else:
                        bt.approach_angle_deg = _to_decimal_or_none(ang_val if ang_val is not None else value_raw)
                        if bt.cutter_type == "high_speed":
                            bt.variable_angle = False
                            bt.save(update_fields=["approach_angle_deg", "variable_angle"])
                        else:
                            bt.save(update_fields=["approach_angle_deg"])
                elif field == "bt_brand":
                    bt.brand = (value_raw or "").strip()[:80]
                    bt.save(update_fields=["brand"])
                elif field == "bt_shank_type":
                    bt.shank_type = normalize_body_tool_shank(value_raw)
                    derived = coupling_from_shank(bt.shank_type)
                    if derived:
                        bt.coupling = derived
                        bt.save(update_fields=["shank_type", "coupling"])
                    else:
                        bt.save(update_fields=["shank_type"])
                elif field == "bt_variable_angle":
                    bt.variable_angle = _to_bool(value_raw)
                    if bt.variable_angle:
                        bt.approach_angle_deg = None
                        bt.save(update_fields=["variable_angle", "approach_angle_deg"])
                    else:
                        bt.save(update_fields=["variable_angle"])
                elif field == "bt_hs_body_style":
                    bt.hs_body_style = normalize_high_speed_body_style(value_raw)
                    bt.save(update_fields=["hs_body_style"])
                elif field == "bt_has_purpose":
                    bt.has_purpose = _to_bool(value_raw)
                    bt.save(update_fields=["has_purpose"])
                elif field == "bt_corner_radius_mm":
                    bt.corner_radius_mm = _to_decimal_or_none(value_raw)
                    bt.save(update_fields=["corner_radius_mm"])
                elif field == "bt_insert_compat":
                    bt.insert_compat = (value_raw or "").strip()[:80]
                    bt.save(update_fields=["insert_compat"])
                elif field == "bt_mount_thread":
                    bt.mount_thread = normalize_modular_head_thread(value_raw)
                    bt.coupling = "modular"
                    bt.save(update_fields=["mount_thread", "coupling"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
                tool.name = _body_tool_name_from_spec(bt)
                tool.save(update_fields=["name", "updated_at"])
            elif cat == "tap" and tool.tap_spec:
                tp = tool.tap_spec
                if field == "size_label":
                    tp.size_label = (value_raw or "")[:40]
                    tp.save(update_fields=["size_label"])
                elif field == "thread_standard":
                    tp.thread_standard = value_raw or "metric"
                    tp.save(update_fields=["thread_standard"])
                elif field == "thread_kind":
                    tp.thread_kind = normalize_thread_kind(value_raw)
                    tp.save(update_fields=["thread_kind"])
                elif field == "tap_pitch_mm":
                    tp.pitch_mm = _to_decimal_or_none(value_raw)
                    tp.save(update_fields=["pitch_mm"])
                elif field == "tap_tpi":
                    tp.tpi = _to_int_or_none(value_raw)
                    tp.save(update_fields=["tpi"])
                elif field == "hole_type":
                    tp.hole_type = value_raw or "any"
                    tp.save(update_fields=["hole_type"])
                elif field == "tap_type":
                    tp.tap_type = value_raw or "cutting"
                    tp.save(update_fields=["tap_type"])
                elif field == "tap_overall_length_mm":
                    tp.overall_length_mm = _to_decimal_or_none(value_raw)
                    tp.save(update_fields=["overall_length_mm"])
                elif field == "tap_cutting_length_mm":
                    tp.cutting_length_mm = _to_decimal_or_none(value_raw)
                    tp.save(update_fields=["cutting_length_mm"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
            elif cat == "center_drill" and tool.center_drill_spec:
                cd = tool.center_drill_spec
                if field == "cd_diameter_mm":
                    cd.diameter_mm = _to_decimal_or_none(value_raw)
                    cd.save(update_fields=["diameter_mm"])
                elif field == "cd_overall_length_mm":
                    cd.overall_length_mm = _to_decimal_or_none(value_raw)
                    cd.save(update_fields=["overall_length_mm"])
                elif field == "cd_angle_deg":
                    cd.angle_deg = value_raw or "60"
                    cd.save(update_fields=["angle_deg"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
            elif cat == "countersink" and tool.countersink_spec:
                cs = tool.countersink_spec
                if field == "cs_type":
                    cs.countersink_type = value_raw or "machine"
                    cs.save(update_fields=["countersink_type"])
                elif field == "cs_diameter_mm":
                    cs.diameter_mm = _to_decimal_or_none(value_raw)
                    cs.save(update_fields=["diameter_mm"])
                elif field == "cs_angle_deg":
                    cs.angle_deg = value_raw or "90"
                    cs.save(update_fields=["angle_deg"])
                elif field == "cs_overall_length_mm":
                    cs.overall_length_mm = _to_decimal_or_none(value_raw)
                    cs.save(update_fields=["overall_length_mm"])
                elif field == "cs_flutes_count":
                    cs.flutes_count = _to_int_or_none(value_raw)
                    cs.save(update_fields=["flutes_count"])
                elif field == "cs_size_label":
                    cs.size_label = (value_raw or "")[:40]
                    cs.save(update_fields=["size_label"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
            elif cat == "drill" and tool.drill_spec:
                dr = tool.drill_spec
                if field == "dr_diameter_mm":
                    dr.diameter_mm = _to_decimal_or_none(value_raw)
                    dr.save(update_fields=["diameter_mm"])
                elif field == "dr_overall_length_mm":
                    dr.overall_length_mm = _to_decimal_or_none(value_raw)
                    dr.save(update_fields=["overall_length_mm"])
                elif field == "dr_cutting_length_mm":
                    dr.cutting_length_mm = _to_decimal_or_none(value_raw)
                    dr.save(update_fields=["cutting_length_mm"])
                elif field == "dr_angle_deg":
                    dr.angle_deg = _to_decimal_or_none(value_raw)
                    dr.save(update_fields=["angle_deg"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
            elif cat == "insert" and tool.insert_spec:
                ins = tool.insert_spec
                if field == "ins_family":
                    ins.milling_family = normalize_milling_family(value_raw) or ins.milling_family
                    ins.save(update_fields=["milling_family"])
                    tool.name = build_insert_display_name(ins.iso_designation, ins.milling_family, ins.chipbreaker_grade)
                    tool.save(update_fields=["name", "updated_at"])
                elif field == "ins_shape":
                    ins.insert_shape = (value_raw or ins.insert_shape or "C")[:1]
                    ins.save(update_fields=["insert_shape"])
                elif field == "ins_edge_code":
                    ins.cutting_edge_length_code = (value_raw or "")[:2]
                    ins.save(update_fields=["cutting_edge_length_code"])
                elif field == "ins_thickness_code":
                    ins.thickness_code = (value_raw or "")[:2]
                    ins.save(update_fields=["thickness_code"])
                elif field == "ins_nose_code":
                    ins.nose_radius_code = (value_raw or "")[:2]
                    ins.save(update_fields=["nose_radius_code"])
                elif field == "ins_grade":
                    ins.chipbreaker_grade = (value_raw or "")[:40]
                    ins.save(update_fields=["chipbreaker_grade"])
                    tool.name = build_insert_display_name(ins.iso_designation, ins.milling_family, ins.chipbreaker_grade)
                    tool.save(update_fields=["name", "updated_at"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
            elif cat == "collet" and tool.collet_spec:
                cl = tool.collet_spec
                if field == "collet_type":
                    cl.collet_type = value_raw or cl.collet_type
                    cl.save(update_fields=["collet_type"])
                elif field == "er_size":
                    cl.er_size = value_raw or ""
                    cl.save(update_fields=["er_size"])
                elif field == "clamp_range":
                    cl.clamp_range = value_raw or ""
                    cl.save(update_fields=["clamp_range"])
                elif field == "inner_diameter":
                    cl.inner_diameter = value_raw or ""
                    cl.save(update_fields=["inner_diameter"])
                elif field == "threading_use":
                    cl.threading_use = value_raw or ""
                    cl.save(update_fields=["threading_use"])
                elif field == "threading_series":
                    cl.threading_series = value_raw or ""
                    cl.save(update_fields=["threading_series"])
                elif field == "collet_thread_standard":
                    cl.thread_standard = value_raw or ""
                    cl.save(update_fields=["thread_standard"])
                elif field == "high_precision_aa":
                    cl.high_precision_aa = value_raw in {"1", "true", "True", "AA", "aa", "yes"}
                    cl.save(update_fields=["high_precision_aa"])
                else:
                    return JsonResponse({"ok": False, "error": "Поле не поддерживается."}, status=400)
            else:
                return JsonResponse({"ok": False, "error": "Поле не поддерживается для этой категории."}, status=400)

        _log_inventory_stock_event(
            actor=username,
            event_type=InventoryStockEvent.EVENT_TOOL_EDIT,
            tool=tool,
            summary=f"Быстрое редактирование ячейки «{field}»: {tool.name} (id {tool.id})",
            details={"tool_id": tool.id, "field": field, "value": value_raw[:200], "category": tool.category},
        )
        return JsonResponse({"ok": True})

    if action == "register_tool_material_extra":
        if not can_manage_stock:
            return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
        saved = _register_tool_material_extra(request.POST.get("value") or "")
        if not saved:
            return JsonResponse({"ok": False, "error": "Укажите непустой материал (не из стандартного списка)."}, status=400)
        return JsonResponse({"ok": True, "value": saved})

    if action == "register_purchase_store":
        saved = _register_purchase_store(request.POST.get("name") or "")
        if not saved:
            return JsonResponse({"ok": False, "error": "Укажите название магазина."}, status=400)
        return JsonResponse({"ok": True, "name": saved})

    if action == "process_issue_outcome":
        issue_id = _to_int(request.POST.get("issue_id"), 0)
        returned_qty = _to_int(request.POST.get("returned_qty"), 0)
        writeoff_qty = _to_int(request.POST.get("writeoff_qty"), 0)
        movement_date_raw = (request.POST.get("movement_date") or "").strip()
        comment = (request.POST.get("comment") or "").strip()
        employee_name = (request.POST.get("employee_name") or "").strip()
        if issue_id <= 0 or (returned_qty <= 0 and writeoff_qty <= 0):
            messages.error(request, "Выберите выдачу и укажите количество на возврат/списание.")
            return redirect("inventory")
        if not comment:
            messages.error(request, "Комментарий обязателен: укажите причину списания/возврата.")
            return redirect("inventory")
        try:
            movement_date = date.fromisoformat(movement_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату операции.")
            return redirect("inventory")

        with transaction.atomic():
            issue = StockMovement.objects.select_for_update().select_related("tool").filter(
                id=issue_id, movement_type="issue"
            ).first()
            if not issue:
                messages.error(request, "Исходная выдача не найдена.")
                return redirect("inventory")

            processed = (
                StockMovement.objects.filter(parent_issue=issue, movement_type__in=["restock", "writeoff"])
                .aggregate(total=Coalesce(Sum("quantity"), Value(0, output_field=IntegerField())))
                .get("total", 0)
            )
            remaining = max(0, issue.quantity - int(processed or 0))
            requested = returned_qty + writeoff_qty
            if requested > remaining:
                messages.error(request, f"По этой выдаче осталось обработать только {remaining} шт.")
                return redirect("inventory")

            if returned_qty > 0:
                issue.tool.quantity += returned_qty
                issue.tool.save(update_fields=["quantity", "updated_at"])
                StockMovement.objects.create(
                    movement_type="restock",
                    tool=issue.tool,
                    parent_issue=issue,
                    quantity=returned_qty,
                    employee_name=employee_name or issue.employee_name,
                    movement_date=movement_date,
                    comment=f"Возврат по выдаче #{issue.id}. {comment}",
                    created_by_account=username,
                )
            if writeoff_qty > 0:
                StockMovement.objects.create(
                    movement_type="writeoff",
                    tool=issue.tool,
                    parent_issue=issue,
                    quantity=writeoff_qty,
                    employee_name=employee_name or issue.employee_name,
                    movement_date=movement_date,
                    comment=f"Списание по выдаче #{issue.id}. {comment}",
                    created_by_account=username,
                )
        messages.success(request, "Операция по выданному инструменту сохранена.")
        return redirect("inventory")

    if action == "link_audit_surplus_return":
        tool_id = _to_int(request.POST.get("tool_id"), 0)
        issue_id = _to_int(request.POST.get("issue_id"), 0)
        returned_qty = _to_int(request.POST.get("returned_qty"), 0)
        comment = (request.POST.get("comment") or "").strip()
        if tool_id <= 0 or issue_id <= 0 or returned_qty <= 0:
            messages.error(request, "Выберите сотрудника и количество для возврата.")
            return redirect(f"{reverse('inventory')}?panel=history")
        with transaction.atomic():
            issue = (
                StockMovement.objects.select_for_update()
                .select_related("tool")
                .filter(id=issue_id, movement_type="issue", tool_id=tool_id)
                .first()
            )
            if not issue:
                messages.error(request, "Выдача не найдена для этой позиции.")
                return redirect(f"{reverse('inventory')}?panel=history")
            remaining = _issue_remaining_qty(issue)
            if remaining <= 0:
                messages.error(request, "По этой выдаче уже нечего возвращать.")
                return redirect(f"{reverse('inventory')}?panel=history")
            qty = min(returned_qty, remaining)

            pool = list(
                StockMovement.objects.select_for_update()
                .filter(
                    tool_id=tool_id,
                    movement_type="restock",
                    parent_issue_id__isnull=True,
                    is_reverted=False,
                )
                .filter(Q(comment__startswith="Инвентаризация"))
                .order_by("id")
            )
            pool_qty = sum(int(m.quantity or 0) for m in pool)
            if pool_qty <= 0:
                messages.error(
                    request,
                    "Нет нераспределённого излишка инвентаризации по этой позиции.",
                )
                return redirect(f"{reverse('inventory')}?panel=history")
            qty = min(qty, pool_qty)

            left = qty
            for mv in pool:
                if left <= 0:
                    break
                take = min(int(mv.quantity or 0), left)
                if take <= 0:
                    continue
                if take < int(mv.quantity or 0):
                    mv.quantity = int(mv.quantity) - take
                    mv.save(update_fields=["quantity"])
                else:
                    mv.delete()
                left -= take

            note = comment or "вернули в ящик при инвентаризации"
            linked = StockMovement.objects.create(
                movement_type="restock",
                tool=issue.tool,
                parent_issue=issue,
                quantity=qty,
                employee_name=(issue.employee_name or "")[:200],
                movement_date=timezone.localdate(),
                comment=f"Возврат по выдаче #{issue.id} (из инвентаризации). {note}"[:300],
                created_by_account=username,
            )
            # Склад уже увеличен инвентаризацией — quantity инструмента не трогаем.
            _log_inventory_stock_event(
                actor=username,
                event_type=InventoryStockEvent.EVENT_TOOL_EDIT,
                tool=issue.tool,
                stock_movement=linked,
                summary=(
                    f"Возврат из инвентаризации: {issue.employee_name or 'без ФИО'} · "
                    f"{issue.tool.name} · {qty} шт. (выдача #{issue.id})"
                ),
                details={
                    "movement_id": linked.id,
                    "issue_id": issue.id,
                    "quantity": qty,
                    "tool_id": tool_id,
                    "employee_name": issue.employee_name or "",
                },
            )
        messages.success(
            request,
            f"Возврат оформлен: {issue.employee_name or 'без ФИО'} · {qty} шт. "
            f"(выдача #{issue_id}). Остаток склада не менялся.",
        )
        return redirect(f"{reverse('inventory')}?panel=history")

    if action == "add_arrival_new":
        category = (request.POST.get("new_category") or "").strip()
        quantity = _to_int(request.POST.get("quantity"), 0)
        movement_date_raw = (request.POST.get("movement_date") or "").strip()
        comment = (request.POST.get("comment") or "").strip()
        tool_material = (request.POST.get("tool_material") or "").strip()
        _register_tool_material_extra(tool_material)
        coating_type = (request.POST.get("coating_type") or "none").strip()
        work_material = normalize_work_material_codes(request.POST.get("work_material"))
        main_diameter_mm = _to_decimal_or_none(request.POST.get("main_diameter_mm"))
        if category not in {"end_mill", "tap"} or quantity <= 0:
            messages.error(request, "Укажите тип инструмента и количество для прихода.")
            return redirect("inventory")
        try:
            movement_date = date.fromisoformat(movement_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату прихода.")
            return redirect("inventory")

        with transaction.atomic():
            if category == "end_mill":
                mill_type = (request.POST.get("mill_type") or "end").strip()
                diameter_mm = _to_decimal_or_none(request.POST.get("em_diameter_mm"))
                corner_radius_mm = _to_decimal_or_none(request.POST.get("em_corner_radius_mm"))
                overall_length_mm = _to_decimal_or_none(request.POST.get("em_overall_length_mm"))
                cutting_length_mm = _to_decimal_or_none(request.POST.get("em_cutting_length_mm"))
                flutes_count = _to_int_or_none(request.POST.get("em_flutes_count"))
                tool = (
                    ToolItem.objects.select_for_update()
                    .filter(
                        category="end_mill",
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        end_mill_spec__mill_type=mill_type,
                        end_mill_spec__diameter_mm=diameter_mm,
                        end_mill_spec__corner_radius_mm=corner_radius_mm,
                        end_mill_spec__overall_length_mm=overall_length_mm,
                        end_mill_spec__cutting_length_mm=cutting_length_mm,
                        end_mill_spec__flutes_count=flutes_count,
                    )
                    .first()
                )
                if tool:
                    tool.quantity += quantity
                    tool.save(update_fields=["quantity", "updated_at"])
                else:
                    tool = ToolItem.objects.create(
                        category="end_mill",
                        name=_build_end_mill_name(diameter_mm, flutes_count, tool_material, work_material),
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        quantity=quantity,
                    )
                    EndMillSpec.objects.create(
                        tool=tool,
                        mill_type=mill_type,
                        diameter_mm=diameter_mm,
                        corner_radius_mm=corner_radius_mm,
                        overall_length_mm=overall_length_mm,
                        cutting_length_mm=cutting_length_mm,
                        flutes_count=flutes_count,
                    )
            else:
                thread_standard = (request.POST.get("thread_standard") or "metric").strip()
                thread_kind = normalize_thread_kind(request.POST.get("thread_kind"))
                size_label = (request.POST.get("size_label") or "").strip() or "Размер неизвестен"
                pitch_mm = _to_decimal_or_none(request.POST.get("tap_pitch_mm"))
                tpi = _to_int_or_none(request.POST.get("tap_tpi"))
                hole_type = (request.POST.get("hole_type") or "any").strip()
                tap_type = (request.POST.get("tap_type") or "cutting").strip()
                overall_length_mm = _to_decimal_or_none(request.POST.get("tap_overall_length_mm"))
                cutting_length_mm = _to_decimal_or_none(request.POST.get("tap_cutting_length_mm"))
                tool = (
                    ToolItem.objects.select_for_update()
                    .filter(
                        category="tap",
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        tap_spec__thread_standard=thread_standard,
                        tap_spec__thread_kind=thread_kind,
                        tap_spec__size_label=size_label,
                        tap_spec__pitch_mm=pitch_mm,
                        tap_spec__tpi=tpi,
                        tap_spec__hole_type=hole_type,
                        tap_spec__tap_type=tap_type,
                        tap_spec__overall_length_mm=overall_length_mm,
                        tap_spec__cutting_length_mm=cutting_length_mm,
                    )
                    .first()
                )
                if tool:
                    tool.quantity += quantity
                    tool.save(update_fields=["quantity", "updated_at"])
                else:
                    tool = ToolItem.objects.create(
                        category="tap",
                        name=_build_tap_name(size_label, thread_standard, tap_type, hole_type),
                        tool_material=tool_material,
                        coating_type=coating_type,
                        work_material=work_material,
                        main_diameter_mm=main_diameter_mm,
                        quantity=quantity,
                    )
                    TapSpec.objects.create(
                        tool=tool,
                        thread_standard=thread_standard,
                        thread_kind=thread_kind,
                        size_label=size_label,
                        pitch_mm=pitch_mm,
                        tpi=tpi,
                        hole_type=hole_type,
                        tap_type=tap_type,
                        overall_length_mm=overall_length_mm,
                        cutting_length_mm=cutting_length_mm,
                    )
            StockMovement.objects.create(
                movement_type="restock",
                tool=tool,
                quantity=quantity,
                movement_date=movement_date,
                comment=comment or "Приход инструмента",
                created_by_account=username,
            )
        messages.success(request, "Приход сохранен: остаток обновлен (или создана новая позиция).")
        return redirect("inventory")

    if action == "add_arrival_bulk":
        rows_json = (request.POST.get("rows_json") or "").strip()
        if not rows_json:
            messages.error(request, "Добавьте хотя бы одну строку прихода.")
            return redirect(f"{request.path}?panel=arrival")
        try:
            rows = json.loads(rows_json)
        except Exception:
            messages.error(request, "Некорректные данные строк прихода.")
            return redirect(f"{request.path}?panel=arrival")
        if not isinstance(rows, list) or not rows:
            messages.error(request, "Добавьте хотя бы одну строку прихода.")
            return redirect(f"{request.path}?panel=arrival")

        validation_errors: list[str] = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            validation_errors.extend(_arrival_bulk_row_validation_errors(row, idx))
        if validation_errors:
            messages.error(request, "; ".join(validation_errors[:10]))
            return redirect(f"{request.path}?panel=arrival")

        created_count = 0
        with transaction.atomic():
            for row in rows:
                if not isinstance(row, dict):
                    continue
                category = (row.get("category") or "").strip()
                quantity = _to_int(row.get("quantity"), 0)
                movement_date_raw = (row.get("movement_date") or "").strip()
                comment = (row.get("comment") or "").strip()
                tool_material = (row.get("tool_material") or "").strip()
                _register_tool_material_extra(tool_material)
                coating_type = (row.get("coating_type") or "none").strip()
                work_material = normalize_work_material_codes(row.get("work_material"))
                main_diameter_mm = _to_decimal_or_none(row.get("main_diameter_mm"))
                if category not in _INVENTORY_CATEGORIES or quantity <= 0:
                    continue
                try:
                    movement_date = date.fromisoformat(movement_date_raw)
                except ValueError:
                    movement_date = date.today()

                if category == "end_mill":
                    mill_type = (row.get("mill_type") or "end").strip()
                    diameter_mm = _to_decimal_or_none(row.get("em_diameter_mm"))
                    corner_radius_mm = _to_decimal_or_none(row.get("em_corner_radius_mm"))
                    overall_length_mm = _to_decimal_or_none(row.get("em_overall_length_mm"))
                    cutting_length_mm = _to_decimal_or_none(row.get("em_cutting_length_mm"))
                    flutes_count = _to_int_or_none(row.get("em_flutes_count"))
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="end_mill",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            end_mill_spec__mill_type=mill_type,
                            end_mill_spec__diameter_mm=diameter_mm,
                            end_mill_spec__corner_radius_mm=corner_radius_mm,
                            end_mill_spec__overall_length_mm=overall_length_mm,
                            end_mill_spec__cutting_length_mm=cutting_length_mm,
                            end_mill_spec__flutes_count=flutes_count,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="end_mill",
                            name=_build_end_mill_name(diameter_mm, flutes_count, tool_material, work_material),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        EndMillSpec.objects.create(
                            tool=tool,
                            mill_type=mill_type,
                            diameter_mm=diameter_mm,
                            corner_radius_mm=corner_radius_mm,
                            overall_length_mm=overall_length_mm,
                            cutting_length_mm=cutting_length_mm,
                            flutes_count=flutes_count,
                        )
                elif category == "body_tool":
                    family = normalize_body_tool_family(row.get("body_family"))
                    cutter_type = normalize_indexable_mill_cutter(row.get("body_cutter"))
                    diameter_mm = _to_decimal_or_none(row.get("bt_diameter_mm"))
                    overall_length_mm = _to_decimal_or_none(row.get("bt_overall_length_mm"))
                    cutting_length_mm = _to_decimal_or_none(row.get("bt_cutting_length_mm"))
                    teeth_count = _to_int_or_none(row.get("bt_teeth_count"))
                    coupling = normalize_body_tool_coupling(row.get("bt_coupling"))
                    insert_family = _body_insert_family_from_row(row)
                    insert_size = _body_insert_size_from_row(row)
                    mount_diameter_mm = _to_decimal_or_none(row.get("bt_mount_diameter_mm"))
                    coolant_through = _to_bool(row.get("bt_coolant"))
                    ap_max_mm = _to_decimal_or_none(row.get("bt_ap_max_mm"))
                    brand = (row.get("bt_brand") or "").strip()[:80]
                    shank_type = normalize_body_tool_shank(row.get("bt_shank_type"))
                    hs_body_style = normalize_high_speed_body_style(row.get("bt_hs_body_style"))
                    has_purpose = _to_bool(row.get("bt_has_purpose"))
                    corner_radius_mm = _to_decimal_or_none(row.get("bt_corner_radius_mm"))
                    insert_compat = (row.get("bt_insert_compat") or "").strip()[:80]
                    mount_thread = normalize_modular_head_thread(row.get("bt_mount_thread"))
                    if cutter_type == "ball":
                        insert_family = ""
                        insert_size = ""
                        approach_angle_deg = None
                        variable_angle = False
                        ap_max_mm = None
                        hs_body_style = ""
                        has_purpose = False
                        corner_radius_mm = None
                        mount_thread = ""
                    elif cutter_type == "modular_head":
                        insert_family = ""
                        insert_size = ""
                        overall_length_mm = None
                        cutting_length_mm = None
                        approach_angle_deg = None
                        variable_angle = False
                        ap_max_mm = None
                        hs_body_style = ""
                        has_purpose = False
                        corner_radius_mm = None
                        shank_type = ""
                        coupling = "modular"
                    else:
                        insert_compat = ""
                        mount_thread = ""
                    ang_val, ang_var = parse_angle_or_variable(row.get("bt_angle_deg"))
                    if cutter_type not in ("ball", "modular_head"):
                        if ang_var:
                            variable_angle = True
                            approach_angle_deg = None
                        else:
                            variable_angle = _to_bool(row.get("bt_variable_angle"))
                            approach_angle_deg = _to_decimal_or_none(
                                ang_val if ang_val is not None else row.get("bt_angle_deg")
                            )
                            if variable_angle:
                                approach_angle_deg = None
                    derived = coupling_from_shank(shank_type)
                    if derived:
                        coupling = derived
                    elif cutter_type == "end" and not coupling:
                        coupling = "shank"
                    elif cutter_type == "modular_head":
                        coupling = "modular"
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="body_tool",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            body_tool_spec__family=family,
                            body_tool_spec__cutter_type=cutter_type,
                            body_tool_spec__diameter_mm=diameter_mm,
                            body_tool_spec__overall_length_mm=overall_length_mm,
                            body_tool_spec__teeth_count=teeth_count,
                            body_tool_spec__insert_family=insert_family,
                            body_tool_spec__insert_size=insert_size,
                            body_tool_spec__insert_compat=insert_compat,
                            body_tool_spec__mount_diameter_mm=mount_diameter_mm,
                            body_tool_spec__mount_thread=mount_thread,
                            body_tool_spec__coolant_through=coolant_through,
                            body_tool_spec__ap_max_mm=ap_max_mm,
                            body_tool_spec__approach_angle_deg=approach_angle_deg,
                            body_tool_spec__brand=brand,
                            body_tool_spec__shank_type=shank_type,
                            body_tool_spec__variable_angle=variable_angle,
                            body_tool_spec__hs_body_style=hs_body_style,
                            body_tool_spec__has_purpose=has_purpose,
                            body_tool_spec__corner_radius_mm=corner_radius_mm,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="body_tool",
                            name=build_body_tool_display_name(
                                family=family,
                                cutter_type=cutter_type,
                                diameter_mm=diameter_mm,
                                teeth_count=teeth_count,
                                insert_family=insert_family or insert_compat,
                                insert_size=insert_size,
                                brand=brand,
                            ),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=mount_diameter_mm,
                            quantity=quantity,
                        )
                        BodyToolSpec.objects.create(
                            tool=tool,
                            family=family,
                            cutter_type=cutter_type,
                            diameter_mm=diameter_mm,
                            overall_length_mm=overall_length_mm,
                            cutting_length_mm=cutting_length_mm,
                            teeth_count=teeth_count,
                            coupling=coupling,
                            insert_family=insert_family,
                            insert_size=insert_size,
                            insert_compat=insert_compat,
                            mount_diameter_mm=mount_diameter_mm,
                            mount_thread=mount_thread,
                            coolant_through=coolant_through,
                            ap_max_mm=ap_max_mm,
                            approach_angle_deg=approach_angle_deg,
                            brand=brand,
                            shank_type=shank_type,
                            variable_angle=variable_angle,
                            hs_body_style=hs_body_style,
                            has_purpose=has_purpose,
                            corner_radius_mm=corner_radius_mm,
                        )
                elif category == "tap":
                    thread_standard = (row.get("thread_standard") or "metric").strip()
                    thread_kind = normalize_thread_kind(row.get("thread_kind"))
                    size_label = (row.get("size_label") or "").strip() or "Размер неизвестен"
                    pitch_mm = _to_decimal_or_none(row.get("tap_pitch_mm"))
                    tpi = _to_int_or_none(row.get("tap_tpi"))
                    hole_type = (row.get("hole_type") or "any").strip()
                    tap_type = (row.get("tap_type") or "cutting").strip()
                    overall_length_mm = _to_decimal_or_none(row.get("tap_overall_length_mm"))
                    cutting_length_mm = _to_decimal_or_none(row.get("tap_cutting_length_mm"))
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="tap",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            tap_spec__thread_standard=thread_standard,
                            tap_spec__thread_kind=thread_kind,
                            tap_spec__size_label=size_label,
                            tap_spec__pitch_mm=pitch_mm,
                            tap_spec__tpi=tpi,
                            tap_spec__hole_type=hole_type,
                            tap_spec__tap_type=tap_type,
                            tap_spec__overall_length_mm=overall_length_mm,
                            tap_spec__cutting_length_mm=cutting_length_mm,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="tap",
                            name=_build_tap_name(size_label, thread_standard, tap_type, hole_type),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        TapSpec.objects.create(
                            tool=tool,
                            thread_standard=thread_standard,
                            thread_kind=thread_kind,
                            size_label=size_label,
                            pitch_mm=pitch_mm,
                            tpi=tpi,
                            hole_type=hole_type,
                            tap_type=tap_type,
                            overall_length_mm=overall_length_mm,
                            cutting_length_mm=cutting_length_mm,
                        )
                elif category == "center_drill":
                    diameter_mm = _to_decimal_or_none(row.get("cd_diameter_mm"))
                    overall_length_mm = _to_decimal_or_none(row.get("cd_overall_length_mm"))
                    angle_deg = (row.get("cd_angle_deg") or "60").strip()
                    if angle_deg not in {x[0] for x in CENTER_DRILL_ANGLES}:
                        angle_deg = "60"
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="center_drill",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            center_drill_spec__diameter_mm=diameter_mm,
                            center_drill_spec__overall_length_mm=overall_length_mm,
                            center_drill_spec__angle_deg=angle_deg,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="center_drill",
                            name=_build_center_drill_name(diameter_mm, angle_deg),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        CenterDrillSpec.objects.create(
                            tool=tool,
                            diameter_mm=diameter_mm,
                            overall_length_mm=overall_length_mm,
                            angle_deg=angle_deg,
                        )
                elif category == "countersink":
                    countersink_type = (row.get("cs_type") or "machine").strip()
                    if countersink_type not in {x[0] for x in COUNTERSINK_TYPES}:
                        countersink_type = "machine"
                    diameter_mm = _to_decimal_or_none(row.get("cs_diameter_mm"))
                    angle_deg = (row.get("cs_angle_deg") or "90").strip()
                    if angle_deg not in {x[0] for x in COUNTERSINK_ANGLES}:
                        angle_deg = "90"
                    overall_length_mm = _to_decimal_or_none(row.get("cs_overall_length_mm"))
                    flutes_count = _to_int_or_none(row.get("cs_flutes_count"))
                    size_label = (row.get("cs_size_label") or "").strip()
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="countersink",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            countersink_spec__countersink_type=countersink_type,
                            countersink_spec__diameter_mm=diameter_mm,
                            countersink_spec__angle_deg=angle_deg,
                            countersink_spec__overall_length_mm=overall_length_mm,
                            countersink_spec__flutes_count=flutes_count,
                            countersink_spec__size_label=size_label,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="countersink",
                            name=_build_countersink_name(countersink_type, diameter_mm, angle_deg, size_label),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        CountersinkSpec.objects.create(
                            tool=tool,
                            countersink_type=countersink_type,
                            diameter_mm=diameter_mm,
                            angle_deg=angle_deg,
                            overall_length_mm=overall_length_mm,
                            flutes_count=flutes_count,
                            size_label=size_label,
                        )
                elif category == "drill":
                    diameter_mm = _to_decimal_or_none(row.get("dr_diameter_mm"))
                    overall_length_mm = _to_decimal_or_none(row.get("dr_overall_length_mm"))
                    cutting_length_mm = _to_decimal_or_none(row.get("dr_cutting_length_mm"))
                    angle_deg = _to_decimal_or_none(row.get("dr_angle_deg"))
                    tool = (
                        ToolItem.objects.select_for_update()
                        .filter(
                            category="drill",
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            drill_spec__diameter_mm=diameter_mm,
                            drill_spec__overall_length_mm=overall_length_mm,
                            drill_spec__cutting_length_mm=cutting_length_mm,
                            drill_spec__angle_deg=angle_deg,
                        )
                        .first()
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = ToolItem.objects.create(
                            category="drill",
                            name=_build_drill_name(diameter_mm, overall_length_mm, cutting_length_mm, angle_deg),
                            tool_material=tool_material,
                            coating_type=coating_type,
                            work_material=work_material,
                            main_diameter_mm=main_diameter_mm,
                            quantity=quantity,
                        )
                        DrillSpec.objects.create(
                            tool=tool,
                            diameter_mm=diameter_mm,
                            overall_length_mm=overall_length_mm,
                            cutting_length_mm=cutting_length_mm,
                            angle_deg=angle_deg,
                        )
                elif category == "insert":
                    spec_fields = _insert_spec_fields_from_mapping(row)
                    tool = _find_insert_tool_match(
                        tool_material, coating_type, work_material, main_diameter_mm, spec_fields
                    )
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = _create_insert_tool(
                            quantity, tool_material, coating_type, work_material, main_diameter_mm, spec_fields
                        )
                elif category == "collet":
                    spec_fields = _collet_spec_fields_from_row(row)
                    if not spec_fields["collet_type"]:
                        continue
                    tool = _find_collet_tool_match(spec_fields)
                    if tool:
                        tool.quantity += quantity
                        tool.save(update_fields=["quantity", "updated_at"])
                    else:
                        tool = _create_collet_tool(quantity, spec_fields)
                else:
                    continue
                StockMovement.objects.create(
                    movement_type="restock",
                    tool=tool,
                    quantity=quantity,
                    movement_date=movement_date,
                    comment=comment or "Приход инструмента",
                    created_by_account=username,
                )
                created_count += 1

        if created_count <= 0:
            messages.error(request, "Не удалось сохранить строки прихода. Проверьте данные.")
        else:
            messages.success(request, f"Оприходовано строк: {created_count}.")
        return redirect(f"{request.path}?panel=arrival")

    if action == "create_purchase_request":
        requested_item = (request.POST.get("requested_item") or "").strip()
        store_name = _resolve_purchase_store_name(request.POST)
        store_link = (request.POST.get("store_link") or "").strip()
        article = (request.POST.get("article") or "").strip()
        quantity = _to_int(request.POST.get("quantity"), 0)
        unit_price = _to_decimal(request.POST.get("unit_price"), Decimal("0"))
        request_comment = (request.POST.get("request_comment") or "").strip()
        if not requested_item or quantity <= 0:
            messages.error(request, "Укажите что закупать и количество больше нуля.")
            return redirect(f"{request.path}?panel=purchases")
        if unit_price < 0:
            messages.error(request, "Цена за 1 шт не может быть отрицательной.")
            return redirect(f"{request.path}?panel=purchases")
        if not store_link and not article:
            messages.error(request, "Добавьте ссылку на магазин или артикул.")
            return redirect(f"{request.path}?panel=purchases")
        if store_link and len(store_link) > 2048:
            messages.error(request, "Ссылка на магазин слишком длинная (максимум 2048 символов).")
            return redirect(f"{request.path}?panel=purchases")
        if not store_name and store_link:
            store_name = _store_name_from_url(store_link)
        if store_name:
            _register_purchase_store(store_name)
        PurchaseRequest.objects.create(
            requested_item=requested_item,
            store_name=store_name,
            store_link=store_link,
            article=article,
            quantity=quantity,
            unit_price=unit_price,
            request_comment=request_comment,
            requested_by=username,
        )
        messages.success(request, "Заявка на закупку добавлена.")
        return redirect(f"{request.path}?panel=purchases")

    if action == "update_purchase_status":
        req_id = _to_int(request.POST.get("request_id"), 0)
        new_status = (request.POST.get("status") or "").strip()
        status_comment = (request.POST.get("status_comment") or "").strip()
        if req_id <= 0 or new_status not in {x[0] for x in PURCHASE_STATUSES}:
            messages.error(request, "Проверьте заявку и новый статус.")
            return redirect(f"{request.path}?panel=purchases")
        pr = PurchaseRequest.objects.filter(id=req_id).first()
        if not pr:
            messages.error(request, "Заявка не найдена.")
            return redirect(f"{request.path}?panel=purchases")
        pr.status = new_status
        pr.status_comment = status_comment
        pr.status_updated_by = username
        pr.save(update_fields=["status", "status_comment", "status_updated_by", "updated_at"])
        messages.success(request, "Статус заявки обновлён.")
        return redirect(f"{request.path}?panel=purchases")

    if action == "delete_purchase_request":
        if not is_admin_user:
            messages.error(request, "Удалять заявки может только администратор.")
            return redirect(f"{request.path}?panel=purchases")
        req_id = _to_int(request.POST.get("request_id"), 0)
        if req_id <= 0:
            messages.error(request, "Заявка не найдена.")
            return redirect(f"{request.path}?panel=purchases")
        deleted, _ = PurchaseRequest.objects.filter(id=req_id).delete()
        if deleted:
            messages.success(request, "Заявка удалена.")
        else:
            messages.error(request, "Заявка не найдена.")
        return redirect(f"{request.path}?panel=purchases")

    if action == "create_defect_record":
        if not can_defects:
            messages.warning(request, "У вас нет доступа к разделу «Учёт брака».")
            return redirect(reverse("inventory"))
        defect_date_raw = (request.POST.get("defect_date") or "").strip()
        employee_name = (request.POST.get("employee_name") or "").strip()
        responsible_selected = [str(x).strip() for x in request.POST.getlist("responsible_names") if str(x).strip()]
        responsible_selected = list(dict.fromkeys(responsible_selected))
        responsible_name = ", ".join(responsible_selected) if responsible_selected else employee_name
        department_name = employee_department_map.get(employee_name, "")
        record_type = (request.POST.get("record_type") or "scold").strip()
        if record_type not in ("scold", "praise"):
            record_type = "scold"
        product_name = (request.POST.get("product_name") or "").strip()
        defect_reason = (request.POST.get("defect_reason") or "").strip()
        try:
            defect_date = date.fromisoformat(defect_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату.")
            return redirect(f"{request.path}?panel=defects")
        if not employee_name or not defect_reason:
            messages.error(request, "Заполните сотрудника и причину.")
            return redirect(f"{request.path}?panel=defects")
        if employee_options and employee_name not in employee_options:
            messages.error(request, "Выберите сотрудника из списка (нет доступа к этому сотруднику).")
            return redirect(f"{request.path}?panel=defects")
        if employee_name not in employee_department_map:
            messages.error(request, "Не удалось определить отдел сотрудника — обновите страницу и выберите сотрудника заново.")
            return redirect(f"{request.path}?panel=defects")
        if responsible_selected:
            bad_resp = [nm for nm in responsible_selected if employee_options and nm not in employee_options]
            if bad_resp:
                messages.error(request, "Выберите ответственных только из списка сотрудников.")
                return redirect(f"{request.path}?panel=defects")
        EmployeeDefectRecord.objects.create(
            record_type=record_type,
            defect_date=defect_date,
            responsible_name=responsible_name,
            employee_name=employee_name,
            department_name=department_name,
            defect_quantity=0,
            good_quantity=0,
            bad_quantity=0,
            potential_defect_quantity=0,
            product_name=product_name,
            defect_reason=defect_reason,
        )
        messages.success(request, "Запись сохранена.")
        return redirect(f"{request.path}?panel=defects")

    if action == "update_defect_record":
        if not can_defects:
            messages.warning(request, "У вас нет доступа к разделу «Учёт брака».")
            return redirect(reverse("inventory"))
        rec_id = _to_int(request.POST.get("defect_id"), 0)
        if rec_id <= 0:
            messages.error(request, "Запись не найдена.")
            return redirect(f"{request.path}?panel=defects")
        rec = EmployeeDefectRecord.objects.filter(id=rec_id).first()
        if not rec:
            messages.error(request, "Запись не найдена.")
            return redirect(f"{request.path}?panel=defects")

        if not is_admin_user:
            allowed_departments = {d for d in employee_department_map.values() if d}
            has_access = (
                (rec.department_name and rec.department_name in allowed_departments)
                or (not rec.department_name and rec.employee_name in employee_options)
            )
            if not has_access:
                messages.error(request, "Нет прав на редактирование этой записи.")
                return redirect(f"{request.path}?panel=defects")

        defect_date_raw = (request.POST.get("defect_date") or "").strip()
        employee_name = (request.POST.get("employee_name") or "").strip()
        product_name = (request.POST.get("product_name") or "").strip()
        defect_reason = (request.POST.get("defect_reason") or "").strip()
        try:
            defect_date = date.fromisoformat(defect_date_raw)
        except ValueError:
            messages.error(request, "Введите корректную дату.")
            return redirect(f"{request.path}?panel=defects")
        if not employee_name or not defect_reason:
            messages.error(request, "Заполните сотрудника и причину брака.")
            return redirect(f"{request.path}?panel=defects")
        if employee_options and employee_name not in employee_options:
            messages.error(request, "Выберите сотрудника из списка (нет доступа к этому сотруднику).")
            return redirect(f"{request.path}?panel=defects")
        if employee_name not in employee_department_map:
            messages.error(request, "Не удалось определить отдел сотрудника — обновите страницу и выберите сотрудника заново.")
            return redirect(f"{request.path}?panel=defects")

        rec.defect_date = defect_date
        rec.employee_name = employee_name
        # В таблице редактируется только основной сотрудник; список ответственных не перезаписываем.
        rec.responsible_name = rec.responsible_name or employee_name
        rec.department_name = employee_department_map.get(employee_name, "")
        rec.product_name = product_name
        rec.defect_reason = defect_reason
        rec.save(
            update_fields=[
                "defect_date",
                "employee_name",
                "responsible_name",
                "department_name",
                "product_name",
                "defect_reason",
            ]
        )
        messages.success(request, "Запись учёта брака обновлена.")
        return redirect(f"{request.path}?panel=defects")

    if action == "delete_defect_record":
        if not is_admin_user:
            messages.error(request, "Удалять записи учёта брака может только администратор.")
            return redirect(f"{request.path}?panel=defects")
        rec_id = _to_int(request.POST.get("defect_id"), 0)
        if rec_id <= 0:
            messages.error(request, "Запись не найдена.")
            return redirect(f"{request.path}?panel=defects")
        deleted, _ = EmployeeDefectRecord.objects.filter(id=rec_id).delete()
        if deleted:
            messages.success(request, "Запись учёта брака удалена.")
        else:
            messages.error(request, "Запись не найдена.")
        return redirect(f"{request.path}?panel=defects")

    stock_req = _merge_inventory_stock_query(username, request.GET, use_saved=(panel == "stock"))

    def _sq(key: str, default: str = "") -> str:
        return (stock_req.get(key) or default).strip()

    show_all = (_sq("show_all") or "1") == "1"
    qs = ToolItem.objects.filter(is_deleted=False)
    if not show_all:
        qs = qs.filter(quantity__gt=0)
    if "category" in stock_req:
        cat_raw = _sq("category")
        if cat_raw in ("", "all"):
            filter_category = ""
        elif cat_raw in _INVENTORY_CATEGORIES:
            filter_category = cat_raw
        else:
            filter_category = "end_mill"
    else:
        filter_category = "end_mill"
    if filter_category:
        qs = qs.filter(category=filter_category)

    stock_req = _prune_stock_prefs_params(filter_category, stock_req)
    stock_req["category"] = filter_category
    stock_req["show_all"] = "1" if show_all else "0"

    diameter_mm_raw = _sq("diameter_mm")
    mill_overall_length_raw = _sq("mill_overall_length_mm")
    mill_cutting_length_raw = _sq("mill_cutting_length_mm")
    mill_flutes_count_raw = _sq("mill_flutes_count")
    mill_corner_radius_raw = _sq("mill_corner_radius_mm")
    mill_type_raw = _sq("mill_type")

    tap_size = _sq("tap_size")
    tap_pitch_raw = _sq("tap_pitch")
    tap_thread_standard = _sq("tap_thread_standard")
    tap_thread_kind = _sq("tap_thread_kind")
    tap_hole_type = _sq("tap_hole_type")
    tap_tool_type = _sq("tap_tool_type")
    tap_overall_length_raw = _sq("tap_overall_length_mm")
    tap_cutting_length_raw = _sq("tap_cutting_length_mm")
    center_diameter_raw = _sq("center_diameter_mm")
    center_overall_length_raw = _sq("center_overall_length_mm")
    center_angle_raw = _sq("center_angle_deg")
    countersink_type_raw = _sq("countersink_type")
    countersink_diameter_raw = _sq("countersink_diameter_mm")
    countersink_angle_raw = _sq("countersink_angle_deg")
    countersink_length_raw = _sq("countersink_overall_length_mm")
    countersink_flutes_raw = _sq("countersink_flutes_count")
    countersink_size_raw = _sq("countersink_size_label")
    drill_diameter_raw = _sq("drill_diameter_mm")
    drill_overall_length_raw = _sq("drill_overall_length_mm")
    drill_cutting_length_raw = _sq("drill_cutting_length_mm")
    drill_angle_raw = _sq("drill_angle_deg")
    ins_shape_raw = _sq("ins_shape")
    ins_relief_raw = _sq("ins_relief")
    ins_tolerance_raw = _sq("ins_tolerance")
    ins_edge_code_raw = _sq("ins_edge_code")
    ins_thickness_code_raw = _sq("ins_thickness_code")
    ins_nose_code_raw = _sq("ins_nose_code")
    ins_family_raw = _sq("ins_family")
    ins_grade_raw = _sq("ins_grade")
    ins_iso_raw = _sq("ins_iso")
    collet_type_raw = _sq("collet_type")
    collet_er_size_raw = _sq("collet_er_size")
    collet_clamp_range_raw = _sq("collet_clamp_range")
    collet_square_size_raw = _sq("collet_square_size")
    collet_inner_diameter_raw = _sq("collet_inner_diameter")
    collet_thread_standard_raw = _sq("collet_thread_standard")
    collet_threading_use_raw = _sq("collet_threading_use")
    collet_threading_series_raw = _sq("collet_threading_series")
    body_family_raw = _sq("body_family")
    body_cutter_raw = _sq("body_cutter")
    bt_diameter_raw = _sq("bt_diameter_mm")
    bt_overall_length_raw = _sq("bt_overall_length_mm")
    bt_cutting_length_raw = _sq("bt_cutting_length_mm")
    bt_teeth_count_raw = _sq("bt_teeth_count")
    bt_coupling_raw = _sq("bt_coupling")
    bt_insert_family_raw = _sq("bt_insert_family")
    bt_insert_size_raw = _sq("bt_insert_size")
    bt_mount_diameter_raw = _sq("bt_mount_diameter_mm")
    bt_coolant_raw = _sq("bt_coolant")
    bt_ap_max_raw = _sq("bt_ap_max_mm")
    bt_angle_raw = _sq("bt_angle_deg")
    bt_brand_raw = _sq("bt_brand")
    bt_shank_raw = _sq("bt_shank_type")
    bt_variable_raw = _sq("bt_variable_angle")
    bt_hs_style_raw = _sq("bt_hs_body_style")
    bt_purpose_raw = _sq("bt_has_purpose")
    bt_corner_radius_raw = _sq("bt_corner_radius_mm")
    bt_insert_compat_raw = _sq("bt_insert_compat")
    bt_mount_thread_raw = _sq("bt_mount_thread")

    tm_param = _sq("tool_material")
    tm_custom_param = (_sq("tool_material_custom") or "")[:80]
    if tm_param == TOOL_MATERIAL_FILTER_OTHER:
        tool_material = tm_custom_param.strip()[:80]
    else:
        tool_material = tm_param.strip()[:80]

    coating_type = _sq("coating_type")
    work_material = _sq("work_material")

    qs = _apply_stock_detail_filters(qs, category=filter_category, params=stock_req)

    stock_category_total = 0
    stock_filtered_count = 0
    if panel == "stock":
        stock_category_qs = ToolItem.objects.filter(is_deleted=False)
        if filter_category:
            stock_category_qs = stock_category_qs.filter(category=filter_category)
        if not show_all:
            stock_category_qs = stock_category_qs.filter(quantity__gt=0)
        stock_category_total = stock_category_qs.count()
        stock_filtered_count = qs.count()

    option_base = ToolItem.objects.filter(is_deleted=False)
    if not show_all:
        option_base = option_base.filter(quantity__gt=0)

    def _opt_qs(for_cat: str, *exclude_keys: str):
        oq = option_base.filter(category=for_cat)
        if filter_category and filter_category != for_cat:
            return oq
        return _apply_stock_detail_filters(
            oq,
            category=filter_category or "",
            params=stock_req,
            exclude=frozenset(exclude_keys),
        )

    option_source_qs = option_base
    if filter_category:
        option_source_qs = _opt_qs(filter_category)

    end_mill_diameters = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("end_mill", "diameter_mm"), "end_mill_spec__diameter_mm")
    )
    end_mill_overall_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("end_mill", "mill_overall_length_mm"), "end_mill_spec__overall_length_mm")
    )
    end_mill_cutting_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("end_mill", "mill_cutting_length_mm"), "end_mill_spec__cutting_length_mm")
    )
    end_mill_flutes = _sorted_unique_int_strings(
        _distinct_numeric_values(_opt_qs("end_mill", "mill_flutes_count"), "end_mill_spec__flutes_count")
    )
    end_mill_corner_radii = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("end_mill", "mill_corner_radius_mm"), "end_mill_spec__corner_radius_mm")
    )
    end_mill_types = _distinct_text_values(_opt_qs("end_mill", "mill_type"), "end_mill_spec__mill_type")

    body_tool_families_db = _distinct_text_values(
        _opt_qs("body_tool", "body_family"), "body_tool_spec__family"
    )
    body_tool_cutters_db = _distinct_text_values(
        _opt_qs("body_tool", "body_cutter"), "body_tool_spec__cutter_type"
    )
    body_tool_diameters = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_diameter_mm"), "body_tool_spec__diameter_mm")
    )
    body_tool_overall_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_overall_length_mm"), "body_tool_spec__overall_length_mm")
    )
    body_tool_cutting_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_cutting_length_mm"), "body_tool_spec__cutting_length_mm")
    )
    body_tool_teeth = _sorted_unique_int_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_teeth_count"), "body_tool_spec__teeth_count")
    )
    body_tool_couplings_db = _distinct_text_values(
        _opt_qs("body_tool", "bt_coupling"), "body_tool_spec__coupling"
    )
    body_tool_insert_families = _distinct_text_values(
        _opt_qs("body_tool", "bt_insert_family"), "body_tool_spec__insert_family"
    )
    body_tool_insert_sizes = _distinct_text_values(
        _opt_qs("body_tool", "bt_insert_size"), "body_tool_spec__insert_size"
    )
    body_tool_mount_diameters = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_mount_diameter_mm"), "body_tool_spec__mount_diameter_mm")
    )
    body_tool_ap_max = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_ap_max_mm"), "body_tool_spec__ap_max_mm")
    )
    body_tool_angles = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_angle_deg"), "body_tool_spec__approach_angle_deg")
    )
    body_tool_brands = _distinct_text_values(_opt_qs("body_tool", "bt_brand"), "body_tool_spec__brand")
    body_tool_shanks = _distinct_text_values(_opt_qs("body_tool", "bt_shank_type"), "body_tool_spec__shank_type")
    body_tool_radii = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("body_tool", "bt_corner_radius_mm"), "body_tool_spec__corner_radius_mm")
    )
    body_tool_insert_compats = _distinct_text_values(
        _opt_qs("body_tool", "bt_insert_compat"), "body_tool_spec__insert_compat"
    )
    body_tool_mount_threads = _distinct_text_values(
        _opt_qs("body_tool", "bt_mount_thread"), "body_tool_spec__mount_thread"
    )

    tap_sizes = _distinct_text_values(_opt_qs("tap", "tap_size"), "tap_spec__size_label")
    tap_pitches = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("tap", "tap_pitch"), "tap_spec__pitch_mm")
    )
    tap_overall_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("tap", "tap_overall_length_mm"), "tap_spec__overall_length_mm")
    )
    tap_cutting_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("tap", "tap_cutting_length_mm"), "tap_spec__cutting_length_mm")
    )
    tap_thread_standards = _distinct_text_values(_opt_qs("tap", "tap_thread_standard"), "tap_spec__thread_standard")
    tap_thread_kinds = _distinct_text_values(_opt_qs("tap", "tap_thread_kind"), "tap_spec__thread_kind")
    tap_hole_types = _distinct_text_values(_opt_qs("tap", "tap_hole_type"), "tap_spec__hole_type")
    tap_tool_types = _distinct_text_values(_opt_qs("tap", "tap_tool_type"), "tap_spec__tap_type")
    center_diameters = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("center_drill", "center_diameter_mm"), "center_drill_spec__diameter_mm")
    )
    center_overall_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(
            _opt_qs("center_drill", "center_overall_length_mm"), "center_drill_spec__overall_length_mm"
        )
    )
    center_angles = _distinct_text_values(
        _opt_qs("center_drill", "center_angle_deg"), "center_drill_spec__angle_deg"
    )
    countersink_types = _distinct_text_values(
        _opt_qs("countersink", "countersink_type"), "countersink_spec__countersink_type"
    )
    countersink_diameters = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("countersink", "countersink_diameter_mm"), "countersink_spec__diameter_mm")
    )
    countersink_angles = _distinct_text_values(
        _opt_qs("countersink", "countersink_angle_deg"), "countersink_spec__angle_deg"
    )
    countersink_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(
            _opt_qs("countersink", "countersink_overall_length_mm"), "countersink_spec__overall_length_mm"
        )
    )
    countersink_flutes = _sorted_unique_int_strings(
        _distinct_numeric_values(_opt_qs("countersink", "countersink_flutes_count"), "countersink_spec__flutes_count")
    )
    countersink_sizes = _distinct_text_values(
        _opt_qs("countersink", "countersink_size_label"), "countersink_spec__size_label"
    )
    drill_diameters = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("drill", "drill_diameter_mm"), "drill_spec__diameter_mm")
    )
    drill_overall_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("drill", "drill_overall_length_mm"), "drill_spec__overall_length_mm")
    )
    drill_cutting_lengths = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("drill", "drill_cutting_length_mm"), "drill_spec__cutting_length_mm")
    )
    drill_angles = _sorted_unique_decimal_strings(
        _distinct_numeric_values(_opt_qs("drill", "drill_angle_deg"), "drill_spec__angle_deg")
    )
    insert_shapes = _distinct_text_values(_opt_qs("insert", "ins_shape"), "insert_spec__insert_shape")
    insert_reliefs = _distinct_text_values(_opt_qs("insert", "ins_relief"), "insert_spec__relief_angle")
    insert_tolerances = _distinct_text_values(_opt_qs("insert", "ins_tolerance"), "insert_spec__tolerance_class")
    insert_edge_codes = _distinct_text_values(
        _opt_qs("insert", "ins_edge_code"), "insert_spec__cutting_edge_length_code"
    )
    insert_thickness_codes = _distinct_text_values(
        _opt_qs("insert", "ins_thickness_code"), "insert_spec__thickness_code"
    )
    insert_nose_codes = _distinct_text_values(_opt_qs("insert", "ins_nose_code"), "insert_spec__nose_radius_code")
    insert_families = _distinct_text_values(_opt_qs("insert", "ins_family"), "insert_spec__milling_family")
    insert_grades_db = _distinct_text_values(
        _opt_qs("insert", "ins_grade"), "insert_spec__chipbreaker_grade"
    )
    insert_grades = merge_insert_chipbreaker_grades(insert_grades_db)
    insert_isos = _distinct_text_values(_opt_qs("insert", "ins_iso"), "insert_spec__iso_designation")

    tool_material_extra_options = _tool_material_extra_options(
        tools_qs=_apply_stock_detail_filters(
            option_source_qs if filter_category else option_base,
            category=filter_category,
            params=stock_req,
            exclude=frozenset({"tool_material", "tool_material_custom"}),
        ),
        extra_candidate=tool_material,
    )
    extras_set = set(tool_material_extra_options)

    if tm_param == TOOL_MATERIAL_FILTER_OTHER:
        tm_custom_input = tm_custom_param
        tool_material_select = TOOL_MATERIAL_FILTER_OTHER
    elif not tool_material:
        tm_custom_input = ""
        tool_material_select = ""
    elif tool_material in _TOOL_MATERIAL_STD_KEYS:
        tm_custom_input = ""
        tool_material_select = tool_material
    elif tool_material in extras_set:
        tm_custom_input = ""
        tool_material_select = tool_material
    else:
        tm_custom_input = tool_material
        tool_material_select = TOOL_MATERIAL_FILTER_OTHER

    stock_tool_material_extra_json = json.dumps(tool_material_extra_options)

    issue_candidates = list(
        StockMovement.objects.filter(movement_type="issue")
        .select_related(
            "tool",
            "tool__end_mill_spec",
            "tool__body_tool_spec",
            "tool__tap_spec",
            "tool__center_drill_spec",
            "tool__countersink_spec",
            "tool__drill_spec",
            "tool__insert_spec",
            "tool__collet_spec",
        )
        .annotate(
            processed_qty=Coalesce(
                Sum("issue_outcomes__quantity"),
                Value(0, output_field=IntegerField()),
            )
        )
        .annotate(remaining_qty=F("quantity") - F("processed_qty"))
        .filter(remaining_qty__gt=0)
        .order_by("-movement_date", "-id")[:200]
    )
    purchase_status = (request.GET.get("purchase_status") or "").strip()
    purchase_store = (request.GET.get("purchase_store") or "").strip()
    purchase_date_from = (request.GET.get("purchase_date_from") or "").strip()
    purchase_date_to = (request.GET.get("purchase_date_to") or "").strip()
    purchase_employee = (request.GET.get("purchase_employee") or "").strip()
    purchase_qs = PurchaseRequest.objects.all()
    if purchase_status in {x[0] for x in PURCHASE_STATUSES}:
        purchase_qs = purchase_qs.filter(status=purchase_status)
    if purchase_store:
        purchase_qs = purchase_qs.filter(store_name__iexact=purchase_store)
    if purchase_date_from:
        purchase_qs = purchase_qs.filter(created_at__date__gte=purchase_date_from)
    if purchase_date_to:
        purchase_qs = purchase_qs.filter(created_at__date__lte=purchase_date_to)
    if purchase_employee:
        purchase_qs = purchase_qs.filter(requested_by__icontains=purchase_employee)

    defect_date_from = (request.GET.get("defect_date_from") or "").strip()
    defect_date_to = (request.GET.get("defect_date_to") or "").strip()
    defect_date_mode = (request.GET.get("defect_date_mode") or "day").strip()
    if defect_date_mode not in ("day", "range"):
        defect_date_mode = "day"
    defect_department = (request.GET.get("defect_department") or "").strip()
    defects_qs = EmployeeDefectRecord.objects.all()
    if not is_admin_user:
        allowed_departments = {d for d in employee_department_map.values() if d}
        if allowed_departments:
            defects_qs = defects_qs.filter(
                Q(department_name__in=allowed_departments)
                | Q(department_name="", employee_name__in=employee_options)
            )
        else:
            defects_qs = defects_qs.none()
    if defect_date_from:
        defects_qs = defects_qs.filter(defect_date__gte=defect_date_from)
    if defect_date_to:
        defects_qs = defects_qs.filter(defect_date__lte=defect_date_to)
    if defect_department:
        defects_qs = defects_qs.filter(department_name=defect_department)
    defect_department_options = sorted(
        {
            d
            for d in list(employee_department_map.values()) + list(
                EmployeeDefectRecord.objects.exclude(department_name="")
                .values_list("department_name", flat=True)
                .distinct()
            )
            if d
        }
    )

    payroll_rows: list[dict] = []
    payroll_year = date.today().year
    payroll_month = date.today().month
    payroll_month_name = MONTH_NAMES_RU[payroll_month]
    payroll_year_options: list[int] = []
    payroll_dept_options: list[str] = []
    payroll_depts_selected: list[str] = []
    if panel == "payroll":
        from .payroll_helpers import build_payroll_employee_rows, parse_payroll_year_month

        payroll_year, payroll_month = parse_payroll_year_month(request)
        payroll_month_name = MONTH_NAMES_RU[payroll_month]
        payroll_depts_selected = [d.strip() for d in request.GET.getlist("dep") if str(d).strip()]
        pay_df, skud_totals, payroll_year_options, payroll_dept_options = build_payroll_employee_rows(
            username,
            payroll_year,
            payroll_month,
            selected_departments=payroll_depts_selected or None,
        )
        # Оставляем в UI только реально существующие; полный набор = «все»
        if payroll_depts_selected and payroll_dept_options:
            allowed_deps = set(payroll_dept_options)
            payroll_depts_selected = [d for d in payroll_depts_selected if d in allowed_deps]
            if set(payroll_depts_selected) == allowed_deps:
                payroll_depts_selected = []
        if pay_df is not None and not getattr(pay_df, "empty", True):
            for _, r in pay_df.iterrows():
                ec = normalize_emp_code(str(r.get("emp_code") or ""))
                if not ec:
                    continue
                payroll_rows.append(
                    {
                        "emp_code": ec,
                        "label": employee_label_row(r),
                        "department_name": str(r.get("department_name") or "").strip(),
                        "skud_hours": round(float(skud_totals.get(ec, 0.0)), 2),
                    }
                )
            codes = [row["emp_code"] for row in payroll_rows]
            status_by_code = {
                s.emp_code: s
                for s in EmployeePayrollMonthStatus.objects.filter(
                    year=payroll_year, month=payroll_month, emp_code__in=codes
                )
            }
            for row in payroll_rows:
                st = status_by_code.get(row["emp_code"])
                row["payroll_advance_ok"] = bool(st and st.advance_closed)
                row["payroll_month_ok"] = bool(st and st.payroll_closed)
        if not payroll_year_options:
            ny = date.today().year
            payroll_year_options = [ny - 1, ny, ny + 1]

    if request.method == "GET" and panel == "stock":
        persist = dict(stock_req)
        persist["category"] = filter_category
        persist["show_all"] = "1" if show_all else "0"
        for _dk in _STOCK_DECIMAL_PARAM_KEYS:
            if _dk in persist:
                persist[_dk] = _norm_stock_decimal_str(persist.get(_dk) or "")
        for _ik in _STOCK_INT_PARAM_KEYS:
            if _ik in persist:
                persist[_ik] = _norm_stock_int_filter_str(persist.get(_ik) or "")
        _save_inventory_stock_filter_prefs(username, persist, category=filter_category)

    history_movement_type = (request.GET.get("history_movement_type") or "").strip()
    if history_movement_type not in _HISTORY_MOVEMENT_TYPES:
        history_movement_type = ""

    mv_qs = (
        StockMovement.objects.select_related(
            "tool",
            "tool__end_mill_spec",
            "tool__body_tool_spec",
            "tool__tap_spec",
            "tool__center_drill_spec",
            "tool__countersink_spec",
            "tool__drill_spec",
            "tool__insert_spec",
            "tool__collet_spec",
        )
        .prefetch_related("issue_outcomes")
        .order_by("-created_at")
    )
    if history_movement_type:
        mv_qs = mv_qs.filter(movement_type=history_movement_type)
    mv_hist = list(mv_qs[:120])
    ev_hist: list[InventoryStockEvent] = []
    if not history_movement_type:
        ev_hist = list(
            InventoryStockEvent.objects.select_related("tool", "stock_movement").order_by("-created_at")[:80]
        )
    timeline: list[dict] = []
    for m in mv_hist:
        timeline.append(
            {
                "kind": "movement",
                "ts": m.created_at,
                "tid": m.id,
                "movement": m,
                "show_rollback": is_admin_user and _can_rollback_stock_movement(m),
            }
        )
    for e in ev_hist:
        event_payload = e
        audit_details = None
        if e.event_type == InventoryStockEvent.EVENT_CONTAINER_AUDIT:
            audit_details = _enrich_container_audit_details(e.details if isinstance(e.details, dict) else {})
        timeline.append(
            {
                "kind": "event",
                "ts": e.created_at,
                "tid": 10**12 + e.id,
                "event": event_payload,
                "audit_details": audit_details,
                "show_rollback": False,
            }
        )
    timeline.sort(key=lambda x: (x["ts"], x["tid"]), reverse=True)
    inventory_history = timeline[:120]

    ctx = {
        "tool_items": qs.select_related(
            "end_mill_spec",
            "body_tool_spec",
            "tap_spec",
            "center_drill_spec",
            "countersink_spec",
            "drill_spec",
            "insert_spec",
            "collet_spec",
        ).order_by("category", "name"),
        "movements": mv_hist[:50],
        "inventory_history": inventory_history,
        "thread_standards": THREAD_STANDARDS,
        "thread_kinds": THREAD_KINDS,
        "tap_hole_types": TAP_HOLE_TYPES,
        "tap_tool_types": TAP_TOOL_TYPES,
        "filters": {
            "category": filter_category,
            "diameter_mm": _norm_stock_decimal_str(diameter_mm_raw),
            "mill_overall_length_mm": _norm_stock_decimal_str(mill_overall_length_raw),
            "mill_cutting_length_mm": _norm_stock_decimal_str(mill_cutting_length_raw),
            "mill_flutes_count": _norm_stock_int_filter_str(mill_flutes_count_raw),
            "mill_corner_radius_mm": _norm_stock_decimal_str(mill_corner_radius_raw),
            "mill_type": mill_type_raw,
            "tap_size": tap_size,
            "tap_pitch": _norm_stock_decimal_str(tap_pitch_raw),
            "tap_thread_standard": tap_thread_standard,
            "tap_thread_kind": tap_thread_kind,
            "tap_hole_type": tap_hole_type,
            "tap_tool_type": tap_tool_type,
            "tap_overall_length_mm": _norm_stock_decimal_str(tap_overall_length_raw),
            "tap_cutting_length_mm": _norm_stock_decimal_str(tap_cutting_length_raw),
            "center_diameter_mm": _norm_stock_decimal_str(center_diameter_raw),
            "center_overall_length_mm": _norm_stock_decimal_str(center_overall_length_raw),
            "center_angle_deg": center_angle_raw,
            "countersink_type": countersink_type_raw,
            "countersink_diameter_mm": _norm_stock_decimal_str(countersink_diameter_raw),
            "countersink_angle_deg": countersink_angle_raw,
            "countersink_overall_length_mm": _norm_stock_decimal_str(countersink_length_raw),
            "countersink_flutes_count": _norm_stock_int_filter_str(countersink_flutes_raw),
            "countersink_size_label": countersink_size_raw,
            "drill_diameter_mm": _norm_stock_decimal_str(drill_diameter_raw),
            "drill_overall_length_mm": _norm_stock_decimal_str(drill_overall_length_raw),
            "drill_cutting_length_mm": _norm_stock_decimal_str(drill_cutting_length_raw),
            "drill_angle_deg": _norm_stock_decimal_str(drill_angle_raw),
            "ins_shape": ins_shape_raw,
            "ins_relief": ins_relief_raw,
            "ins_tolerance": ins_tolerance_raw,
            "ins_edge_code": ins_edge_code_raw,
            "ins_thickness_code": ins_thickness_code_raw,
            "ins_nose_code": ins_nose_code_raw,
            "ins_family": ins_family_raw,
            "ins_grade": ins_grade_raw,
            "ins_iso": ins_iso_raw,
            "collet_type": collet_type_raw,
            "collet_er_size": collet_er_size_raw,
            "collet_clamp_range": collet_clamp_range_raw,
            "collet_square_size": collet_square_size_raw,
            "collet_inner_diameter": collet_inner_diameter_raw,
            "collet_thread_standard": collet_thread_standard_raw,
            "collet_threading_use": collet_threading_use_raw,
            "collet_threading_series": collet_threading_series_raw,
            "body_family": body_family_raw,
            "body_cutter": body_cutter_raw,
            "bt_diameter_mm": _norm_stock_decimal_str(bt_diameter_raw),
            "bt_overall_length_mm": _norm_stock_decimal_str(bt_overall_length_raw),
            "bt_cutting_length_mm": _norm_stock_decimal_str(bt_cutting_length_raw),
            "bt_teeth_count": _norm_stock_int_filter_str(bt_teeth_count_raw),
            "bt_coupling": bt_coupling_raw,
            "bt_insert_family": bt_insert_family_raw,
            "bt_insert_size": bt_insert_size_raw,
            "bt_mount_diameter_mm": _norm_stock_decimal_str(bt_mount_diameter_raw),
            "bt_coolant": bt_coolant_raw,
            "bt_ap_max_mm": _norm_stock_decimal_str(bt_ap_max_raw),
            "bt_angle_deg": bt_angle_raw if bt_angle_raw == "variable" else _norm_stock_decimal_str(bt_angle_raw),
            "bt_brand": bt_brand_raw,
            "bt_shank_type": bt_shank_raw,
            "bt_variable_angle": bt_variable_raw,
            "bt_hs_body_style": bt_hs_style_raw,
            "bt_has_purpose": bt_purpose_raw,
            "bt_corner_radius_mm": _norm_stock_decimal_str(bt_corner_radius_raw),
            "bt_insert_compat": bt_insert_compat_raw,
            "bt_mount_thread": bt_mount_thread_raw,
            "tool_material": tool_material,
            "tool_material_custom": tm_custom_input,
            "tool_material_select": tool_material_select,
            "coating_type": coating_type,
            "work_material": work_material,
            "show_all": show_all,
            "history_movement_type": history_movement_type,
        },
        "history_movement_types": [
            ("restock", "Пополнение"),
            ("writeoff", "Списание"),
            ("issue", "Выдача"),
        ],
        "end_mill_filter_options": {
            "diameters": end_mill_diameters,
            "overall_lengths": end_mill_overall_lengths,
            "cutting_lengths": end_mill_cutting_lengths,
            "flutes": end_mill_flutes,
            "corner_radii": end_mill_corner_radii,
            "types": end_mill_types,
        },
        "end_mill_types": END_MILL_TYPES,
        "body_tool_filter_options": {
            "families": body_tool_families_db,
            "cutters": body_tool_cutters_db,
            "diameters": body_tool_diameters,
            "overall_lengths": body_tool_overall_lengths,
            "cutting_lengths": body_tool_cutting_lengths,
            "teeth": body_tool_teeth,
            "couplings": body_tool_couplings_db,
            "insert_families": body_tool_insert_families,
            "insert_sizes": body_tool_insert_sizes,
            "mount_diameters": body_tool_mount_diameters,
            "ap_max": body_tool_ap_max,
            "angles": body_tool_angles,
            "brands": body_tool_brands,
            "shanks": body_tool_shanks,
            "radii": body_tool_radii,
            "insert_compats": body_tool_insert_compats,
            "mount_threads": body_tool_mount_threads,
        },
        "body_tool_families": BODY_TOOL_FAMILIES,
        "indexable_mill_cutter_types": INDEXABLE_MILL_CUTTER_TYPES,
        "body_tool_couplings": BODY_TOOL_COUPLINGS,
        "body_tool_shank_types": BODY_TOOL_SHANK_TYPES,
        "end_mill_shank_types": END_MILL_SHANK_TYPES,
        "chamfer_mill_shank_types": CHAMFER_MILL_SHANK_TYPES,
        "high_speed_shank_types": HIGH_SPEED_SHANK_TYPES,
        "round_insert_shank_types": ROUND_INSERT_SHANK_TYPES,
        "ball_mill_shank_types": BALL_MILL_SHANK_TYPES,
        "modular_head_threads": MODULAR_HEAD_THREADS,
        "high_speed_body_styles": HIGH_SPEED_BODY_STYLES,
        "high_speed_angle_options": HIGH_SPEED_ANGLE_OPTIONS,
        "face_mill_angles": FACE_MILL_ANGLES,
        "tap_filter_options": {
            "sizes": tap_sizes,
            "pitches": tap_pitches,
            "overall_lengths": tap_overall_lengths,
            "cutting_lengths": tap_cutting_lengths,
            "thread_standards": tap_thread_standards,
            "thread_kinds": tap_thread_kinds,
            "hole_types": tap_hole_types,
            "tool_types": tap_tool_types,
        },
        "center_drill_filter_options": {
            "diameters": center_diameters,
            "overall_lengths": center_overall_lengths,
            "angles": center_angles,
        },
        "center_drill_angles": CENTER_DRILL_ANGLES,
        "countersink_filter_options": {
            "types": countersink_types,
            "diameters": countersink_diameters,
            "angles": countersink_angles,
            "overall_lengths": countersink_lengths,
            "flutes": countersink_flutes,
            "sizes": countersink_sizes,
        },
        "countersink_types": COUNTERSINK_TYPES,
        "countersink_angles": COUNTERSINK_ANGLES,
        "drill_filter_options": {
            "diameters": drill_diameters,
            "overall_lengths": drill_overall_lengths,
            "cutting_lengths": drill_cutting_lengths,
            "angles": drill_angles,
        },
        "insert_filter_options": {
            "shapes": insert_shapes,
            "reliefs": insert_reliefs,
            "tolerances": insert_tolerances,
            "edge_codes": insert_edge_codes,
            "thickness_codes": insert_thickness_codes,
            "nose_codes": insert_nose_codes,
            "families": insert_families,
            "grades": insert_grades,
            "isos": insert_isos,
        },
        "insert_shapes": INSERT_SHAPES,
        "insert_relief_angles": INSERT_RELIEF_ANGLES,
        "insert_tolerance_classes": INSERT_TOLERANCE_CLASSES,
        "insert_edge_length_codes": INSERT_EDGE_LENGTH_CODES,
        "insert_thickness_codes": INSERT_THICKNESS_CODES,
        "insert_nose_radius_codes": INSERT_NOSE_RADIUS_CODES,
        "insert_machining_applications": INSERT_MACHINING_APPLICATIONS,
        "milling_insert_families": _merged_milling_insert_families(),
        "insert_family_other": INSERT_FAMILY_OTHER,
        "insert_size_other": INSERT_SIZE_OTHER,
        "insert_grade_other": INSERT_GRADE_OTHER,
        "insert_chipbreaker_grades": insert_grades,
        "insert_column_tooltips": INSERT_COLUMN_TOOLTIPS,
        "insert_column_tooltips_json": json.dumps(INSERT_COLUMN_TOOLTIPS, ensure_ascii=False),
        "collet_types": COLLET_TYPES,
        "collet_types_ui": [
            {"value": k, "label": lbl, "tip": COLLET_TYPE_TOOLTIPS.get(k, "")}
            for k, lbl in COLLET_TYPES
        ],
        "collet_type_tooltips": COLLET_TYPE_TOOLTIPS,
        "collet_type_tooltips_json": json.dumps(COLLET_TYPE_TOOLTIPS, ensure_ascii=False),
        "er_collet_sizes": ER_COLLET_SIZES,
        "er_clamp_ranges": ER_CLAMP_RANGES,
        "collet_er_g_inner_diameters": COLLET_ER_G_INNER_DIAMETERS,
        "collet_thread_standards": COLLET_THREAD_STANDARDS,
        "collet_threading_series": COLLET_THREADING_SERIES,
        "collet_threading_use": COLLET_THREADING_USE,
        "tool_material_types": TOOL_MATERIAL_TYPES,
        "tool_material_extra_options": tool_material_extra_options,
        "tool_material_filter_other": TOOL_MATERIAL_FILTER_OTHER,
        "stock_tool_material_extra_json": stock_tool_material_extra_json,
        "coating_types": COATING_TYPES,
        "work_material_types": WORK_MATERIAL_TYPES,
        "today": date.today().isoformat(),
        "movement_tool_options": ToolItem.objects.select_related(
            "end_mill_spec",
            "body_tool_spec",
            "tap_spec",
            "center_drill_spec",
            "countersink_spec",
            "drill_spec",
            "insert_spec",
            "collet_spec",
        ).filter(is_deleted=False).order_by("category", "name"),
        "issue_candidates": issue_candidates,
        "purchase_requests": purchase_qs[:300],
        "purchase_store_options": _purchase_store_options(),
        "purchase_store_filter_other": PURCHASE_STORE_FILTER_OTHER,
        "purchase_statuses": PURCHASE_STATUSES,
        "purchase_filters": {
            "status": purchase_status,
            "store": purchase_store,
            "date_from": purchase_date_from,
            "date_to": purchase_date_to,
            "employee": purchase_employee,
        },
        "is_admin_user": is_admin_user,
        "can_manage_stock": can_manage_stock,
        "can_rollback_stock": is_admin_user,
        "stock_filtered_count": stock_filtered_count,
        "stock_category_total": stock_category_total,
        "panel": panel,
        "employee_options": employee_options,
        "defect_records": defects_qs[:300],
        "defect_filters": {
            "date_from": defect_date_from,
            "date_to": defect_date_to,
            "date_mode": defect_date_mode,
            "department": defect_department,
        },
        "defect_department_options": defect_department_options,
        "employee_table_rows": employee_table_rows,
        "payroll_rows": payroll_rows,
        "payroll_year": payroll_year,
        "payroll_month": payroll_month,
        "payroll_month_name": payroll_month_name,
        "payroll_year_options": payroll_year_options,
        "payroll_dept_options": payroll_dept_options,
        "payroll_depts_selected": payroll_depts_selected,
        "month_choices_payroll": [(mm, MONTH_NAMES_RU[mm]) for mm in range(1, 13)],
    }
    if panel == "analysis":
        ctx.update(analysis_context(request, username))
    return render(request, "shifts/inventory.html", ctx)
