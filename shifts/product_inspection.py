"""Контроль размеров в карточке наладки: карта контроля и акты замеров."""
from __future__ import annotations

import json
import re
from typing import Any

from django.db import transaction
from django.db.models import Max

import biota_shifts.db as biota_db
from biota_shifts.auth import employees_df_for_nav
from biota_shifts.schedule import employee_label_row

from .models import (
    Product,
    ProductInspectionDimension,
    ProductInspectionSession,
    ProductInspectionValue,
    ProductSetup,
)

_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _parse_num(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", ".")
    if not s:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except (TypeError, ValueError):
        return None


def evaluate_measurement(
    nominal: str,
    tolerance_plus: str,
    tolerance_minus: str,
    tolerance_display: str,
    actual: str,
) -> bool | None:
    """True/False если удалось вычислить, None — ручная оценка."""
    n = _parse_num(nominal)
    a = _parse_num(actual)
    if n is None or a is None:
        return None

    td = (tolerance_display or "").strip()
    plus = _parse_num(tolerance_plus)
    minus = _parse_num(tolerance_minus)

    if td.startswith("±"):
        t = _parse_num(td[1:])
        if t is not None:
            plus = minus = t
    elif "/" in td and not plus and not minus:
        parts = td.replace(" ", "").split("/")
        if len(parts) == 2:
            if parts[0].startswith("+"):
                plus = _parse_num(parts[0][1:])
            if parts[1].startswith("-"):
                minus = _parse_num(parts[1][1:])

    if plus is None and minus is None:
        return None
    if plus is None:
        plus = minus
    if minus is None:
        minus = plus

    lo = n - minus
    hi = n + plus
    return lo <= a <= hi


def employee_options_for_products(username: str | None) -> list[dict[str, str]]:
    """Список сотрудников для combobox (label + emp_code)."""
    try:
        cfg = biota_db.db_config()
        employees_df = employees_df_for_nav(username, "products", biota_db.load_employees(cfg))
    except Exception:
        return []
    if employees_df.empty:
        return []

    prepared: list[tuple[str, str, str]] = []
    base_counts: dict[str, int] = {}
    for _, row in employees_df.iterrows():
        base_label = employee_label_row(row)
        if not base_label or base_label == "Без имени":
            continue
        emp_code = str(row.get("emp_code") or "").strip()
        last = str(row.get("last_name") or "").strip()
        first = str(row.get("first_name") or "").strip()
        full_name = " ".join(p for p in (last, first) if p)
        prepared.append((base_label, full_name, emp_code))
        base_counts[base_label] = base_counts.get(base_label, 0) + 1

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for base_label, full_name, emp_code in prepared:
        label = base_label
        if base_counts.get(base_label, 0) > 1:
            if full_name and full_name != base_label:
                label = f"{base_label} ({full_name})"
            elif emp_code:
                label = f"{base_label} [{emp_code}]"
        if label in seen and emp_code:
            label = f"{label} [{emp_code}]"
        if label in seen:
            continue
        seen.add(label)
        out.append({"label": label, "emp_code": emp_code})
    out.sort(key=lambda x: x["label"].lower())
    return out


def _dimension_qs(product: Product, setup: ProductSetup | None):
    qs = ProductInspectionDimension.objects.filter(product=product, is_active=True)
    if setup is None:
        return qs.filter(setup__isnull=True)
    return qs.filter(setup=setup)


def dimension_applies_for_session(
    dim: ProductInspectionDimension,
    *,
    session_index: int,
    first_piece: bool,
) -> bool:
    if dim.frequency == ProductInspectionDimension.FREQUENCY_FIRST:
        return first_piece
    if dim.frequency == ProductInspectionDimension.FREQUENCY_EVERY_N:
        n = max(1, int(dim.frequency_n or 1))
        return first_piece or ((session_index + 1) % n == 1)
    return True


def applicable_dimensions(
    product: Product,
    setup: ProductSetup | None,
    *,
    first_piece: bool,
) -> list[ProductInspectionDimension]:
    session_count = ProductInspectionSession.objects.filter(
        product=product,
        setup=setup,
    ).count()
    dims = list(_dimension_qs(product, setup))
    return [
        d
        for d in dims
        if dimension_applies_for_session(d, session_index=session_count, first_piece=first_piece)
    ]


def dimension_to_dict(dim: ProductInspectionDimension) -> dict[str, Any]:
    return {
        "id": dim.pk,
        "label": dim.label,
        "nominal": dim.nominal or "",
        "tolerance_plus": dim.tolerance_plus or "",
        "tolerance_minus": dim.tolerance_minus or "",
        "tolerance_display": dim.tolerance_text,
        "criticality": dim.criticality,
        "frequency": dim.frequency,
        "frequency_n": dim.frequency_n,
        "pdf_page": dim.pdf_page,
        "mark_x": dim.mark_x,
        "mark_y": dim.mark_y,
        "sort_order": dim.sort_order,
    }


def session_to_dict(session: ProductInspectionSession) -> dict[str, Any]:
    values = [
        {
            "id": v.pk,
            "dimension_id": v.dimension_id,
            "dimension_label": v.dimension_label,
            "nominal": v.nominal or "",
            "tolerance_display": v.tolerance_display or "",
            "criticality": v.criticality or "",
            "actual_value": v.actual_value or "",
            "is_ok": v.is_ok,
            "pdf_page": v.pdf_page,
            "mark_x": v.mark_x,
            "mark_y": v.mark_y,
        }
        for v in session.values.all()
    ]
    return {
        "id": session.pk,
        "session_no": session.session_no,
        "inspector_emp_code": session.inspector_emp_code or "",
        "inspector_label": session.inspector_label or "",
        "part_label": session.part_label or "",
        "author_username": session.author_username or "",
        "result": session.result,
        "notes": session.notes or "",
        "created_at": session.created_at.strftime("%d.%m.%Y %H:%M"),
        "values": values,
    }


def inspection_context_payload(product: Product, setup: ProductSetup | None, username: str | None) -> dict[str, Any]:
    dims = list(_dimension_qs(product, setup))
    sessions = (
        ProductInspectionSession.objects.filter(product=product, setup=setup)
        .prefetch_related("values")
        .order_by("-created_at", "-id")[:80]
    )
    drawing_url = ""
    drawing_files: list[dict[str, Any]] = []
    files = list(getattr(product, "drawing_file_list", None) or [])
    if not files and product.drawing_pdf:
        drawing_url = product.drawing_pdf.url
        drawing_files = [{"id": 0, "url": drawing_url, "name": "Чертёж PDF"}]
    elif files:
        for f in files:
            drawing_files.append(
                {"id": f.pk, "url": f.file.url, "name": (f.display_name or f.original_filename or "Чертёж")}
            )
        drawing_url = drawing_files[0]["url"]

    return {
        "dimensions": [dimension_to_dict(d) for d in dims],
        "sessions": [session_to_dict(s) for s in sessions],
        "employee_options": employee_options_for_products(username),
        "drawing_url": drawing_url,
        "drawing_files": drawing_files,
        "session_count": ProductInspectionSession.objects.filter(product=product, setup=setup).count(),
        "setup_id": setup.pk if setup else None,
        "setup_name": (setup.name or "").strip() if setup else "",
    }


def save_inspection_plan(
    product: Product,
    setup: ProductSetup | None,
    rows: list[dict],
) -> str | None:
    if not isinstance(rows, list):
        return "Некорректный формат карты контроля."
    kept_ids: list[int] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        label = (row.get("label") or "").strip()
        if not label:
            continue
        dim_id = row.get("id")
        obj: ProductInspectionDimension | None = None
        if dim_id is not None and str(dim_id).isdigit():
            obj = ProductInspectionDimension.objects.filter(
                pk=int(dim_id), product=product, setup=setup
            ).first()
        if obj is None:
            obj = ProductInspectionDimension(product=product, setup=setup)

        crit = (row.get("criticality") or ProductInspectionDimension.CRITICALITY_STANDARD).strip()
        if crit not in dict(ProductInspectionDimension.CRITICALITY_CHOICES):
            crit = ProductInspectionDimension.CRITICALITY_STANDARD
        freq = (row.get("frequency") or ProductInspectionDimension.FREQUENCY_ALWAYS).strip()
        if freq not in dict(ProductInspectionDimension.FREQUENCY_CHOICES):
            freq = ProductInspectionDimension.FREQUENCY_ALWAYS

        obj.label = label[:120]
        obj.nominal = (row.get("nominal") or "").strip()[:80]
        obj.tolerance_plus = (row.get("tolerance_plus") or "").strip()[:40]
        obj.tolerance_minus = (row.get("tolerance_minus") or "").strip()[:40]
        obj.tolerance_display = (row.get("tolerance_display") or "").strip()[:80]
        obj.criticality = crit
        obj.frequency = freq
        fn = row.get("frequency_n")
        obj.frequency_n = max(1, min(999, int(fn))) if str(fn or "").isdigit() else 5
        pp = row.get("pdf_page")
        obj.pdf_page = int(pp) if str(pp or "").isdigit() else None
        mx, my = row.get("mark_x"), row.get("mark_y")
        obj.mark_x = float(mx) if mx not in (None, "") else None
        obj.mark_y = float(my) if my not in (None, "") else None
        obj.sort_order = idx
        obj.is_active = True
        obj.save()
        kept_ids.append(obj.pk)

    stale = ProductInspectionDimension.objects.filter(product=product, setup=setup)
    if kept_ids:
        stale = stale.exclude(pk__in=kept_ids)
    stale.update(is_active=False)
    return None


def create_inspection_session(
    product: Product,
    setup: ProductSetup | None,
    *,
    author_username: str,
    inspector_emp_code: str,
    inspector_label: str,
    part_label: str,
    first_piece: bool,
    notes: str,
    measurements: list[dict],
) -> tuple[ProductInspectionSession | None, str | None]:
    inspector_label = (inspector_label or "").strip()
    if not inspector_label:
        return None, "Выберите контролёра из списка сотрудников."

    dim_map = {d.pk: d for d in _dimension_qs(product, setup)}
    applicable_ids = {d.pk for d in applicable_dimensions(product, setup, first_piece=first_piece)}

    class _Row:
        __slots__ = (
            "dim",
            "label",
            "nominal",
            "tolerance_display",
            "criticality",
            "actual",
            "is_ok",
            "mark_x",
            "mark_y",
            "pdf_page",
        )

        def __init__(self, **kwargs):
            for k in self.__slots__:
                setattr(self, k, kwargs.get(k))

    parsed_rows: list[_Row] = []
    for row in measurements:
        if not isinstance(row, dict):
            continue
        actual = (row.get("actual_value") or "").strip()[:80]
        if not actual:
            continue

        dim_id_raw = row.get("dimension_id")
        dim: ProductInspectionDimension | None = None
        if str(dim_id_raw or "").isdigit():
            dim_id = int(dim_id_raw)
            if dim_id in dim_map and (dim_id in applicable_ids or row.get("from_drawing")):
                dim = dim_map[dim_id]

        if dim is not None:
            label = dim.label
            nominal = dim.nominal or ""
            tol = dim.tolerance_display or dim.tolerance_text
            criticality = dim.criticality
            mark_x = dim.mark_x if row.get("mark_x") in (None, "") else row.get("mark_x")
            mark_y = dim.mark_y if row.get("mark_y") in (None, "") else row.get("mark_y")
            pdf_page = dim.pdf_page if row.get("pdf_page") in (None, "") else row.get("pdf_page")
        else:
            label = (row.get("label") or row.get("dimension_label") or "").strip()
            if not label:
                continue
            nominal = (row.get("nominal") or "").strip()[:80]
            tol = (row.get("tolerance_display") or "").strip()[:80]
            criticality = (row.get("criticality") or "").strip()[:20]
            mark_x = row.get("mark_x")
            mark_y = row.get("mark_y")
            pdf_page = row.get("pdf_page")

        manual_ok = row.get("is_ok")
        if manual_ok is True or manual_ok is False or manual_ok == "true" or manual_ok == "false":
            is_ok = manual_ok is True or manual_ok == "true"
        else:
            is_ok = evaluate_measurement(nominal, "", "", tol, actual)
            if is_ok is None and tol and nominal:
                return None, f"Не удалось определить допуск для «{label}» — отметьте годность вручную."

        def _float_or_none(v):
            if v in (None, ""):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _page_or_none(v):
            if v in (None, ""):
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        parsed_rows.append(
            _Row(
                dim=dim,
                label=label[:120],
                nominal=nominal,
                tolerance_display=tol,
                criticality=criticality,
                actual=actual,
                is_ok=is_ok,
                mark_x=_float_or_none(mark_x),
                mark_y=_float_or_none(mark_y),
                pdf_page=_page_or_none(pdf_page),
            )
        )

    if not parsed_rows:
        return None, "Нет замеров для сохранения. Кликните по чертежу или добавьте строки."

    with transaction.atomic():
        max_no = (
            ProductInspectionSession.objects.filter(product=product, setup=setup)
            .aggregate(m=Max("session_no"))
            .get("m")
        )
        session_no = (max_no or 0) + 1
        ok_count = sum(1 for r in parsed_rows if r.is_ok)
        nok_count = sum(1 for r in parsed_rows if r.is_ok is False)
        if nok_count == 0:
            result = ProductInspectionSession.RESULT_OK
        elif ok_count == 0:
            result = ProductInspectionSession.RESULT_NOK
        else:
            result = ProductInspectionSession.RESULT_PARTIAL

        session = ProductInspectionSession.objects.create(
            product=product,
            setup=setup,
            session_no=session_no,
            inspector_emp_code=(inspector_emp_code or "").strip()[:32],
            inspector_label=inspector_label[:240],
            part_label=(part_label or "").strip()[:120],
            author_username=(author_username or "?")[:150],
            result=result,
            notes=(notes or "").strip()[:2000],
        )
        for idx, pr in enumerate(parsed_rows):
            ProductInspectionValue.objects.create(
                session=session,
                dimension=pr.dim,
                dimension_label=pr.label,
                nominal=pr.nominal,
                tolerance_display=pr.tolerance_display,
                criticality=pr.criticality,
                actual_value=pr.actual,
                is_ok=pr.is_ok,
                pdf_page=pr.pdf_page,
                mark_x=pr.mark_x,
                mark_y=pr.mark_y,
                sort_order=idx,
            )
    return session, None


def parse_json_list(raw: str) -> list | None:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    return data
