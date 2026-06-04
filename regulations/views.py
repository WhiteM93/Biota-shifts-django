"""Регламенты: интерактивная шкала времени + API сохранения (БД Django)."""
import json
from datetime import datetime, time
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from biota_shifts import db as biota_db
from biota_shifts import export as biota_export
from biota_shifts import schedule as biota_schedule
from biota_shifts.auth import employees_df_for_nav

from shifts.auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from shifts.department_order import apply_department_order, load_department_order
from shifts.graph_views import (
    DEPT_COLOR_CLASSES,
    _dept_rank_map,
    _extract_selected_deps,
    _parse_sort_mode,
    _pos_rank_map,
    _schedule_with_department,
    _sort_graph_rows,
)
from shifts.position_order import apply_position_order, load_position_order
from shifts.section_action_log import (
    EVT_SERVER_REG_META,
    EVT_SERVER_REG_SAVE,
    SECTION_REGULATIONS,
    record_from_request,
)

from .models import RegulationPlan

_DEFAULT_BREAKFAST = (time(9, 0), time(9, 30))
_DEFAULT_LUNCH = (time(12, 0), time(13, 0))


def _default_breaks_for_plan(o: RegulationPlan) -> list[dict]:
    items = [
        {
            "label": "Завтрак",
            "start": o.breakfast_start.strftime("%H:%M"),
            "end": o.breakfast_end.strftime("%H:%M"),
            "color_kind": "bf",
        },
        {
            "label": "Обед",
            "start": o.lunch_start.strftime("%H:%M"),
            "end": o.lunch_end.strftime("%H:%M"),
            "color_kind": "ln",
        },
    ]
    if o.extra_start and o.extra_end:
        items.append(
            {
                "label": (o.extra_label or "").strip() or "Доп. ползунок",
                "start": o.extra_start.strftime("%H:%M"),
                "end": o.extra_end.strftime("%H:%M"),
                "color_kind": "br",
            }
        )
    return items


def _normalized_breaks(o: RegulationPlan, raw_items) -> list[dict]:
    items = raw_items if isinstance(raw_items, list) else []
    out: list[dict] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        label = str(it.get("label") or "").strip()[:100] or f"Ползунок {idx + 1}"
        try:
            st = _parse_hm(str(it.get("start", "")))
            en = _parse_hm(str(it.get("end", "")))
        except ValueError:
            continue
        if (st.hour * 60 + st.minute) >= (en.hour * 60 + en.minute):
            continue
        kind = str(it.get("color_kind") or "").strip().lower()
        if kind == "ex":
            kind = "br"
        if kind not in ("bf", "ln", "br"):
            kind = "br"
        out.append(
            {
                "label": label,
                "start": st.strftime("%H:%M"),
                "end": en.strftime("%H:%M"),
                "color_kind": kind,
            }
        )
    if out:
        return out
    return _default_breaks_for_plan(o)


def _break_intervals_minutes_day(breaks: list[dict]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for b in breaks:
        try:
            st = _parse_hm(str(b.get("start", "")))
            en = _parse_hm(str(b.get("end", "")))
        except ValueError:
            continue
        a0 = st.hour * 60 + st.minute
        a1 = en.hour * 60 + en.minute
        if a0 < a1:
            out.append((a0, a1))
    return out


def _intervals_overlap_pairwise(intervals: list[tuple[int, int]]) -> bool:
    for i in range(len(intervals)):
        a0, a1 = intervals[i]
        for j in range(i + 1, len(intervals)):
            b0, b1 = intervals[j]
            if a0 < b1 and b0 < a1:
                return True
    return False


def _primary_windows_from_breaks(plan: RegulationPlan, breaks: list[dict]) -> tuple:
    bf = next((b for b in breaks if b.get("color_kind") == "bf"), None)
    ln = next((b for b in breaks if b.get("color_kind") == "ln"), None)
    br = next((b for b in breaks if b.get("color_kind") == "br"), None)
    bf_s = _parse_hm(str((bf or {}).get("start") or plan.breakfast_start.strftime("%H:%M")))
    bf_e = _parse_hm(str((bf or {}).get("end") or plan.breakfast_end.strftime("%H:%M")))
    ln_s = _parse_hm(str((ln or {}).get("start") or plan.lunch_start.strftime("%H:%M")))
    ln_e = _parse_hm(str((ln or {}).get("end") or plan.lunch_end.strftime("%H:%M")))
    if br:
        br_s = _parse_hm(str(br.get("start") or ""))
        br_e = _parse_hm(str(br.get("end") or ""))
        br_l = str(br.get("label") or "").strip()[:100] or "Перерыв 1"
        return bf_s, bf_e, ln_s, ln_e, br_l, br_s, br_e
    return bf_s, bf_e, ln_s, ln_e, "", None, None


def _parse_shift(raw: str | None) -> str:
    s = (raw or "д").strip().lower()
    return "н" if s in ("н", "n") else "д"


def _shift_title(shift: str) -> str:
    return "Ночная смена" if shift == "н" else "Дневная смена"


def _employees_for_user(request):
    cfg = biota_db.db_config()
    employees_df = biota_db.load_employees(cfg)
    return employees_df_for_nav(biota_user(request), "regulations", employees_df)


def _fill_from_catalog(employees_df) -> tuple[int, int]:
    created = 0
    skipped = 0
    for _, row in employees_df.iterrows():
        code = str(row.get("emp_code") or "").strip()
        if not code:
            continue
        ln = str(row.get("last_name") or "").strip()
        fn = str(row.get("first_name") or "").strip()
        name = f"{ln} {fn}".strip() or code
        dept = str(row.get("department_name") or "").strip()
        pos = str(row.get("position_name") or "").strip()
        for shift_key in ("д", "н"):
            _, was_created = RegulationPlan.objects.get_or_create(
                employee_code=code,
                shift=shift_key,
                defaults={
                    "employee_name": name,
                    "department": dept,
                    "position": pos,
                    "breakfast_start": _DEFAULT_BREAKFAST[0],
                    "breakfast_end": _DEFAULT_BREAKFAST[1],
                    "lunch_start": _DEFAULT_LUNCH[0],
                    "lunch_end": _DEFAULT_LUNCH[1],
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1
    return created, skipped


def _sync_regulation_catalog_fields(employees_df) -> int:
    """Подставить актуальные ФИО, отдел и должность из Biota в строки регламента."""
    if employees_df is None or getattr(employees_df, "empty", True):
        return 0
    by_code: dict[str, tuple[str, str, str]] = {}
    for _, row in employees_df.iterrows():
        code = str(row.get("emp_code") or "").strip()
        if not code:
            continue
        ln = str(row.get("last_name") or "").strip()
        fn = str(row.get("first_name") or "").strip()
        name = f"{ln} {fn}".strip() or code
        dept = str(row.get("department_name") or "").strip()
        pos = str(row.get("position_name") or "").strip()
        by_code[code] = (name, dept, pos)
    updated = 0
    for obj in RegulationPlan.objects.all():
        info = by_code.get(str(obj.employee_code).strip())
        if not info:
            continue
        name, dept, pos = info
        if (
            (obj.employee_name or "") == name
            and (obj.department or "") == dept
            and (obj.position or "") == pos
        ):
            continue
        RegulationPlan.objects.filter(pk=obj.pk).update(
            employee_name=name,
            department=dept,
            position=pos,
        )
        updated += 1
    return updated


def _scale_slots_30min() -> list[dict]:
    slots: list[dict] = []
    for i in range(25):
        total_min = 8 * 60 + i * 30
        h, m = divmod(total_min, 60)
        lbl = f"{h:02d}:{m:02d}"
        slots.append({"label": lbl, "strong": m == 0})
    return slots


def _row_json(o: RegulationPlan) -> dict:
    breaks = _normalized_breaks(o, o.breaks)
    return {
        "id": o.pk,
        "employee_code": o.employee_code,
        "employee_name": o.employee_name,
        "breakfast_start": o.breakfast_start.strftime("%H:%M"),
        "breakfast_end": o.breakfast_end.strftime("%H:%M"),
        "lunch_start": o.lunch_start.strftime("%H:%M"),
        "lunch_end": o.lunch_end.strftime("%H:%M"),
        "locked": o.locked,
        "breaks": breaks,
    }


def _dept_color_map_from_list(all_deps: list[str]) -> dict[str, str]:
    return {
        dep: DEPT_COLOR_CLASSES[i % len(DEPT_COLOR_CLASSES)]
        for i, dep in enumerate(all_deps)
    }


def _fallback_dep_color_map(plans: list[RegulationPlan]) -> dict[str, str]:
    names = sorted({((o.department or "").strip() or "Без отдела") for o in plans})
    all_deps = apply_department_order(names, load_department_order())
    return _dept_color_map_from_list(all_deps)


def _regulation_plans_and_colors(
    request, shift: str = "д"
) -> tuple[list[RegulationPlan], dict[str, str]]:
    """Порядок строк как на «Графике» + цвета отделов; только выбранная смена (д/н)."""
    if shift not in ("д", "н"):
        shift = "д"
    base_all = list(RegulationPlan.objects.all())
    employees_df = None
    try:
        employees_df = _employees_for_user(request)
    except Exception:
        employees_df = None
    if employees_df is not None and not getattr(employees_df, "empty", True):
        active_codes = set(employees_df["emp_code"].astype(str).str.strip())
        base_all = [o for o in base_all if str(o.employee_code).strip() in active_codes]
    base = [o for o in base_all if o.shift == shift]
    if not base:
        return [], {}
    if employees_df is None:
        base.sort(key=lambda o: (o.employee_name.lower(), o.employee_code))
        return base, _fallback_dep_color_map(base)
    if employees_df.empty:
        return [], {}
    try:
        from datetime import date
        today = date.today()
        schedule_df = biota_schedule.load_schedule_table(employees_df, today.year, today.month)
        schedule_df = _schedule_with_department(schedule_df, employees_df)
        all_deps = apply_department_order(
            sorted(schedule_df["Отдел"].unique().tolist()),
            load_department_order(),
        )
        dep_color_map = _dept_color_map_from_list(all_deps)
        selected_deps, dep_mode = _extract_selected_deps(request, all_deps, from_post=False)
        dep_rank = _dept_rank_map(all_deps)
        all_positions = apply_position_order(
            sorted(schedule_df["Должность"].unique().tolist()),
            load_position_order(),
        )
        pos_rank = _pos_rank_map(all_positions)
        sort_mode = _parse_sort_mode(request, from_post=False)
        if not selected_deps:
            return [], dep_color_map
        schedule_df = schedule_df[schedule_df["Отдел"].isin(selected_deps)].copy()
        schedule_df = _sort_graph_rows(
            schedule_df, dep_rank, pos_rank, sort_mode=sort_mode
        ).reset_index(drop=True)
        code_order = [str(c).strip() for c in schedule_df["Код"].tolist()]
    except Exception:
        base.sort(key=lambda o: (o.employee_name.lower(), o.employee_code))
        return base, _fallback_dep_color_map(base)

    by_key = {(str(o.employee_code).strip(), o.shift): o for o in base_all}
    ordered: list[RegulationPlan] = []
    seen: set[str] = set()
    for code in code_order:
        o = by_key.get((code, shift))
        if o is not None:
            ordered.append(o)
            seen.add(code)
    if dep_mode == "all":
        rest = [o for o in base if str(o.employee_code).strip() not in seen]
        rest.sort(key=lambda o: (o.employee_name.lower(), o.employee_code))
        ordered.extend(rest)
    return ordered, dep_color_map


def _department_filter_context(request) -> dict:
    ctx = {
        "reg_filter_deps": [],
        "reg_sel_deps": [],
        "reg_dep_mode_pick": False,
        "reg_dep_qs": "",
        "post_dep_mode": request.GET.get("dep_mode") or "",
        "post_dep_list": list(request.GET.getlist("dep")),
    }
    try:
        from datetime import date
        today = date.today()
        employees_df = _employees_for_user(request)
        schedule_df = biota_schedule.load_schedule_table(
            employees_df, today.year, today.month
        )
        schedule_df = _schedule_with_department(schedule_df, employees_df)
        all_deps = apply_department_order(
            sorted(schedule_df["Отдел"].unique().tolist()),
            load_department_order(),
        )
        sel, depm = _extract_selected_deps(request, all_deps, from_post=False)
        ctx["reg_filter_deps"] = all_deps
        ctx["reg_sel_deps"] = sel
        ctx["reg_dep_mode_pick"] = depm != "all"
        q = []
        if request.GET.get("dep_mode"):
            q.append(("dep_mode", request.GET.get("dep_mode")))
        for d in request.GET.getlist("dep"):
            q.append(("dep", d))
        ctx["reg_dep_qs"] = ("&" + urlencode(q)) if q else ""
    except Exception:
        pass
    return ctx


def _parse_hm(s: str) -> time:
    s = (s or "").strip()
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError("time")
    return time(int(parts[0]), int(parts[1]))


def _regulation_timeline_export_rows(
    plans: list[RegulationPlan], dep_color_map: dict[str, str]
) -> list[dict]:
    out: list[dict] = []
    for o in plans:
        dept = (o.department or "").strip() or "Без отдела"
        breaks = _normalized_breaks(o, o.breaks)
        breakfasts = [b for b in breaks if b.get("color_kind") == "bf"]
        lunches = [b for b in breaks if b.get("color_kind") == "ln"]
        pauses = [b for b in breaks if b.get("color_kind") == "br"]

        breakfast_text_lines = [f"{b.get('start','')}–{b.get('end','')}" for b in breakfasts]
        lunch_text_lines = [f"{b.get('start','')}–{b.get('end','')}" for b in lunches]
        pause_lines = [f"{b.get('start','')}–{b.get('end','')}" for b in pauses]

        first_bf = breakfasts[0] if breakfasts else None
        first_ln = lunches[0] if lunches else None
        out.append(
            {
                "employee_name": o.employee_name,
                "department_class": dep_color_map.get(dept, "dept-c1"),
                "breakfast_start": (first_bf or {}).get("start") or o.breakfast_start.strftime("%H:%M"),
                "breakfast_end": (first_bf or {}).get("end") or o.breakfast_end.strftime("%H:%M"),
                "lunch_start": (first_ln or {}).get("start") or o.lunch_start.strftime("%H:%M"),
                "lunch_end": (first_ln or {}).get("end") or o.lunch_end.strftime("%H:%M"),
                "breaks": breaks,
                "breakfast_text": "\n".join(breakfast_text_lines) if breakfast_text_lines else "—",
                "lunch_text": "\n".join(lunch_text_lines) if lunch_text_lines else "—",
                "pause_text": "\n".join(pause_lines) if pause_lines else "—",
            }
        )
    return out


@biota_login_required
@nav_permission_required("regulations")
@require_http_methods(["GET"])
def regulations_excel(request):
    shift = _parse_shift(request.GET.get("shift"))
    plans, dep_color_map = _regulation_plans_and_colors(request, shift=shift)
    if not plans:
        return HttpResponse("Нет данных для выбранной смены", status=400, content_type="text/plain; charset=utf-8")
    rows = _regulation_timeline_export_rows(plans, dep_color_map)
    data = biota_export.build_regulations_timeline_excel(rows, None, shift)
    tag = "n" if shift == "н" else "d"
    fn = f"reglament_{tag}.xlsx"
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


@biota_login_required
@nav_permission_required("regulations")
@require_http_methods(["GET"])
def regulations_pdf(request):
    shift = _parse_shift(request.GET.get("shift"))
    plans, dep_color_map = _regulation_plans_and_colors(request, shift=shift)
    if not plans:
        return HttpResponse("Нет данных для выбранной смены", status=400, content_type="text/plain; charset=utf-8")
    rows = _regulation_timeline_export_rows(plans, dep_color_map)
    try:
        data = biota_export.build_regulations_list_pdf(rows, None, shift)
    except Exception as exc:
        return HttpResponse(f"PDF недоступен: {exc}", status=500, content_type="text/plain; charset=utf-8")
    tag = "n" if shift == "н" else "d"
    fn = f"reglament_{tag}.pdf"
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    return resp


@ensure_csrf_cookie
@biota_login_required
@nav_permission_required("regulations")
@write_permission_required
@require_http_methods(["GET", "POST"])
def regulation_page(request):
    reg_shift = _parse_shift(request.GET.get("shift") or request.POST.get("shift"))

    if request.method == "POST" and request.POST.get("action") == "from_catalog":
        try:
            employees_df = _employees_for_user(request)
        except Exception as exc:
            return render(
                request,
                "shifts/error.html",
                {"title": "Ошибка БД", "message": str(exc)},
            )
        if employees_df.empty:
            messages.warning(
                request,
                "Справочник сотрудников пуст или нет прав — нечего подставлять.",
            )
        else:
            n_new, n_skip = _fill_from_catalog(employees_df)
            msg = f"Добавлено новых строк: {n_new}. Уже были в регламенте: {n_skip}."
            messages.success(request, msg)
        post_shift = _parse_shift(request.POST.get("shift"))
        redir_q = [("shift", post_shift)]
        dm = (request.POST.get("dep_mode") or "").strip()
        if dm:
            redir_q.append(("dep_mode", dm))
        for d in request.POST.getlist("dep"):
            if d:
                redir_q.append(("dep", d))
        return redirect(f"{reverse('regulations_page')}?{urlencode(redir_q)}")

    if request.method == "GET":
        try:
            employees_sync = _employees_for_user(request)
            n_sync = _sync_regulation_catalog_fields(employees_sync)
            if n_sync:
                messages.info(
                    request,
                    f"Обновлено из справочника Biota: {n_sync} строк (ФИО, отдел, должность).",
                )
        except Exception:
            pass

    plans, dep_color_map = _regulation_plans_and_colors(request, shift=reg_shift)
    rows: list[dict] = []
    for o in plans:
        row = _row_json(o)
        dept = (o.department or "").strip() or "Без отдела"
        row["department"] = dept
        row["department_class"] = dep_color_map.get(dept, "dept-c1")
        rows.append(row)

    biota_ok = True
    emp_count = None
    try:
        df = _employees_for_user(request)
        emp_count = len(df) if df is not None else 0
    except Exception:
        biota_ok = False

    dep_ctx = _department_filter_context(request)

    return render(
        request,
        "regulations/timeline.html",
        {
            "reg_shift": reg_shift,
            "reg_shift_title": _shift_title(reg_shift),
            "rows": rows,
            "biota_ok": biota_ok,
            "emp_count": emp_count,
            "scale_slots_30": _scale_slots_30min(),
            **dep_ctx,
        },
    )


@csrf_protect
@biota_login_required
@nav_permission_required("regulations")
@write_permission_required
@require_POST
def regulations_api_save(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("invalid json")
    items = payload.get("items")
    if not isinstance(items, list):
        return HttpResponseBadRequest("items required")

    updated = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            pk = int(it.get("id"))
        except (TypeError, ValueError):
            continue
        row = RegulationPlan.objects.filter(pk=pk).first()
        if not row:
            continue
        breaks = _normalized_breaks(row, it.get("breaks"))
        ivs = _break_intervals_minutes_day(breaks)
        if _intervals_overlap_pairwise(ivs):
            return HttpResponseBadRequest(
                "Интервалы (завтрак, обед и доп. промежутки) не должны пересекаться.",
                content_type="text/plain; charset=utf-8",
            )
        try:
            bf_s, bf_e, ln_s, ln_e, ex_l, ex_s, ex_e = _primary_windows_from_breaks(row, breaks)
        except (ValueError, KeyError, TypeError):
            return HttpResponseBadRequest("bad breaks")
        n = RegulationPlan.objects.filter(pk=pk).update(
            breakfast_start=bf_s,
            breakfast_end=bf_e,
            lunch_start=ln_s,
            lunch_end=ln_e,
            extra_label=ex_l,
            extra_start=ex_s,
            extra_end=ex_e,
            breaks=breaks,
        )
        updated += n

    record_from_request(
        request,
        SECTION_REGULATIONS,
        EVT_SERVER_REG_SAVE,
        f"API save: обновлено строк {updated}, в запросе {len(items)}",
        {"updated": updated, "items_in_request": len(items)},
    )
    return JsonResponse({"ok": True, "updated": updated, "saved_at": datetime.now().isoformat(timespec="seconds")})


@csrf_protect
@biota_login_required
@nav_permission_required("regulations")
@write_permission_required
@require_POST
def regulations_api_meta(request):
    """Переключение замка строки."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("invalid json")
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return HttpResponseBadRequest("updates required")

    changed = 0
    updated_rows: list[dict] = []
    for u in updates:
        if not isinstance(u, dict):
            continue
        try:
            pk = int(u.get("id"))
        except (TypeError, ValueError):
            continue
        fields: dict = {}
        if "locked" in u:
            fields["locked"] = bool(u.get("locked"))
        if not fields:
            continue
        n = RegulationPlan.objects.filter(pk=pk).update(**fields)
        changed += n
        if n:
            obj = RegulationPlan.objects.filter(pk=pk).first()
            if obj:
                updated_rows.append(_row_json(obj))

    record_from_request(
        request,
        SECTION_REGULATIONS,
        EVT_SERVER_REG_META,
        f"API meta: изменено {changed}",
        {"changed": changed, "updates": len(updates)},
    )
    return JsonResponse({"ok": True, "changed": changed, "rows": updated_rows})
