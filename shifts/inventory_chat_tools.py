"""Read-only инструменты склада для чата YandexGPT."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from django.db.models import Count, F, IntegerField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import SiteNotebookTask, StockMovement, ToolItem
from .size_label_normalize import size_label_match_variants

MAX_ROWS = 50
MAX_QUERY_LEN = 120
MAX_NAME_LEN = 120
SCAN_LIMIT = 400


def _parse_date(value: Any, *, default: date | None = None) -> date | None:
    if value is None or value == "":
        return default
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return default
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return default


def _clip(text: Any, n: int = 160) -> str:
    s = str(text or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _tool_label(tool: ToolItem) -> str:
    cat = tool.get_category_display()
    name = (tool.name or "").strip()
    if tool.category == "insert":
        ins = getattr(tool, "insert_spec", None)
        brand = (ins.brand if ins else "") or ""
        iname = (ins.item_name if ins else "") or name
        parts = [cat]
        if brand:
            parts.append(brand.strip())
        if iname:
            parts.append(iname.strip())
        return " · ".join(parts)
    if tool.category == "tap":
        tp = getattr(tool, "tap_spec", None)
        parts = [cat]
        if tp:
            size = (tp.size_label or "").strip()
            if size:
                parts.append(size)
            try:
                hole = tp.get_hole_type_display()
            except Exception:
                hole = ""
            if hole:
                parts.append(str(hole))
            try:
                ttype = tp.get_tap_type_display()
            except Exception:
                ttype = ""
            if ttype:
                parts.append(str(ttype))
        elif name:
            parts.append(name)
        return " · ".join(parts)
    if tool.category == "drill":
        dr = getattr(tool, "drill_spec", None)
        d = None
        try:
            d = dr.diameter_mm if dr else None
        except Exception:
            d = None
        if d is not None:
            s = format(d, "f").rstrip("0").rstrip(".")
            return f"{cat} · ⌀{s}" + (f" · {name}" if name else "")
        return f"{cat} · {name}" if name else cat
    return f"{cat} · {name}" if name else cat


_HOLE_ALIASES = {
    "сквозн": "through",
    "сквозной": "through",
    "сквозное": "through",
    "through": "through",
    "глух": "blind",
    "глухой": "blind",
    "глухое": "blind",
    "blind": "blind",
    "универс": "any",
    "any": "any",
}


def _normalize_hole_token(tok: str) -> str | None:
    t = (tok or "").strip().lower().replace("ё", "е")
    if not t:
        return None
    for key, val in _HOLE_ALIASES.items():
        if t == key or t.startswith(key):
            return val
    return None


def _parse_diameter_token(tok: str) -> Decimal | None:
    t = (tok or "").strip().replace(",", ".")
    t = re.sub(r"^(?:[dDø⌀ØфФ]\s*)", "", t)
    t = re.sub(r"\s*(?:мм|mm)$", "", t, flags=re.IGNORECASE).strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", t):
        return None
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


def _query_wants_category(q_low: str) -> str:
    """Явный тип в вопросе: drill / tap / mill / insert / ''."""
    if re.search(r"сверл|drill", q_low):
        return "drill"
    if re.search(r"метчик|раскатник|резьбофрез|\btap\b", q_low):
        return "tap"
    if re.search(r"фрез", q_low):
        return "mill"
    if re.search(r"пластин|insert|apkt|rpmt", q_low):
        return "insert"
    return ""


_TYPE_WORD_RE = re.compile(r"сверл|метчик|раскат|фрез|пластин|drill|tap|insert", re.IGNORECASE)
_STOP_TOKENS = frozenset(
    {
        "а",
        "и",
        "или",
        "но",
        "же",
        "ли",
        "про",
        "для",
        "как",
        "какой",
        "какая",
        "какие",
        "что",
        "это",
        "этот",
        "эта",
        "то",
        "тот",
        "также",
        "ещё",
        "еще",
        "да",
        "нет",
        "ну",
        "вот",
        "там",
        "тут",
        "бы",
        "у",
        "в",
        "на",
        "с",
        "со",
        "к",
        "по",
        "о",
        "об",
        "от",
        "до",
        "из",
        "за",
        "под",
        "над",
        "при",
        "скажи",
        "подскажи",
        "покажи",
        "найди",
        "последний",
        "последние",
        "последнее",
        "брал",
        "брали",
        "взял",
        "взяли",
        "кто",
    }
)


def _is_stop_token(tok: str) -> bool:
    t = (tok or "").strip().lower().replace("ё", "е")
    if not t:
        return True
    if _parse_diameter_token(tok) is not None:
        return False
    if _is_metric_size_token(tok, "tap"):
        return False
    if t in _STOP_TOKENS:
        return True
    return len(t) == 1 and not t.isdigit()


def _diameter_token_q(diam: Decimal, *, name_field: str, comment_field: str | None, drill_field: str, mill_field: str) -> Q:
    """⌀3.5 / D3.5 / 3,5 — не цеплять 2.3 и 13.5."""
    s = format(diam, "f").rstrip("0").rstrip(".")
    esc = re.escape(s).replace(r"\.", r"[.,]")
    boundary = rf"(^|[^0-9]){esc}($|[^0-9])"
    q = Q(**{drill_field: diam}) | Q(**{mill_field: diam})
    q |= Q(**{f"{name_field}__iregex": boundary})
    if comment_field:
        q |= Q(**{f"{comment_field}__iregex": boundary})
    return q


def _is_metric_size_token(tok: str, want_cat: str = "") -> bool:
    t = (tok or "").strip()
    if re.match(r"^[mм]\s*\d", t, re.IGNORECASE):
        return True
    if want_cat == "tap" and re.fullmatch(r"\d+(?:[.,]\d+)?", t.replace(",", ".")):
        return True
    return False


def _metric_size_q(
    tok: str,
    *,
    size_field: str,
    name_field: str,
    comment_field: str | None = None,
) -> Q:
    """M3 / М3 / m3 — один размер; не путать с M30."""
    q = Q()
    if comment_field:
        q |= Q(**{f"{comment_field}__icontains": tok})
    variants = size_label_match_variants(tok)
    if not variants:
        q |= Q(**{f"{name_field}__icontains": tok})
        q |= Q(**{f"{size_field}__icontains": tok})
        return q
    for v in variants:
        q |= Q(**{f"{size_field}__iexact": v})
        if v and re.match(r"^[MmМм]\d", v):
            esc = re.escape(v)
            q |= Q(**{f"{name_field}__iregex": rf"(^|[^0-9]){esc}($|[^0-9])"})
    return q


def _norm_hay(s: str) -> str:
    t = (s or "").lower().replace("ё", "е").replace("й", "и")
    t = t.replace("м", "m").replace(",", ".")
    for ch in ("ø", "⌀", "Ø"):
        t = t.replace(ch, "d")
    t = re.sub(r"[·|/]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tool_haystack(tool: ToolItem | None) -> str:
    if tool is None:
        return ""
    parts: list[str] = [_tool_label(tool), tool.name or "", tool.get_category_display()]
    tp = getattr(tool, "tap_spec", None)
    if tp is not None:
        size = (getattr(tp, "size_label", None) or "").strip()
        if size:
            parts.extend(size_label_match_variants(size))
            parts.append(size)
        try:
            parts.append(str(tp.get_hole_type_display() or ""))
        except Exception:
            pass
        try:
            parts.append(str(tp.get_tap_type_display() or ""))
        except Exception:
            pass
    dr = getattr(tool, "drill_spec", None)
    if dr is not None and getattr(dr, "diameter_mm", None) is not None:
        d = format(dr.diameter_mm, "f").rstrip("0").rstrip(".")
        parts.extend([d, f"d{d}", f"ø{d}"])
    mill = getattr(tool, "end_mill_spec", None)
    if mill is not None and getattr(mill, "diameter_mm", None) is not None:
        d = format(mill.diameter_mm, "f").rstrip("0").rstrip(".")
        parts.extend([d, f"d{d}"])
    ins = getattr(tool, "insert_spec", None)
    if ins is not None:
        parts.append(getattr(ins, "item_name", None) or "")
        parts.append(getattr(ins, "brand", None) or "")
    return _norm_hay(" ".join(p for p in parts if p))


def _movement_haystack(m: StockMovement) -> str:
    extra = f"{m.employee_name or ''} {m.comment or ''}"
    return (_tool_haystack(m.tool) + " " + _norm_hay(extra)).strip()


def _token_matches_hay(hay: str, tok: str, want_cat: str) -> bool:
    low = tok.lower().replace("ё", "е")
    if _TYPE_WORD_RE.search(low) or _is_stop_token(tok):
        return True
    diam = _parse_diameter_token(tok)
    if diam is not None and want_cat != "tap":
        s = format(diam, "f").rstrip("0").rstrip(".")
        return bool(re.search(rf"(^|[^0-9]){re.escape(s)}($|[^0-9])", hay))
    if _is_metric_size_token(tok, want_cat):
        for v in size_label_match_variants(tok):
            nv = _norm_hay(v)
            if not nv:
                continue
            if re.fullmatch(r"m?\d+(?:\.\d+)?", nv):
                if re.search(rf"(^|[^0-9a-z]){re.escape(nv)}($|[^0-9])", hay):
                    return True
            elif nv in hay:
                return True
        return False
    nt = _norm_hay(tok)
    return bool(nt) and nt in hay


def _hay_matches(hay: str, tokens: list[str], want_cat: str) -> bool:
    return all(_token_matches_hay(hay, tok, want_cat) for tok in tokens)


def search_issues(
    query: str = "",
    date_from: Any = None,
    date_to: Any = None,
    limit: int = 20,
    movement_type: str = "issue",
) -> dict[str, Any]:
    """Поиск выдач/движений по названию инструмента (метчик M3, сверло D2.5…)."""
    q = _clip(query, MAX_QUERY_LEN)
    if len(q) < 1:
        return {"error": "Укажите что искать (например: метчик M3 сквозной).", "rows": []}

    today = timezone.localdate()
    d_to = _parse_date(date_to, default=today) or today
    d_from = _parse_date(date_from, default=d_to - timedelta(days=180)) or (d_to - timedelta(days=180))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    lim = max(1, min(int(limit or 20), MAX_ROWS))
    mtype = (movement_type or "issue").strip().lower()
    if mtype == "all":
        mtype = ""
    allowed = {"", "issue", "restock", "writeoff"}
    if mtype not in allowed:
        mtype = "issue"

    q_low = q.lower().replace("ё", "е")
    want_cat = _query_wants_category(q_low)

    tokens = [t for t in re.split(r"[\s,/|]+", q) if t]
    hole_codes: list[str] = []
    search_tokens: list[str] = []
    for tok in tokens:
        hole = _normalize_hole_token(tok)
        if hole:
            hole_codes.append(hole)
        else:
            search_tokens.append(tok)

    qs = (
        StockMovement.objects.filter(
            is_reverted=False,
            movement_date__gte=d_from,
            movement_date__lte=d_to,
        )
        .select_related(
            "tool",
            "tool__insert_spec",
            "tool__tap_spec",
            "tool__drill_spec",
            "tool__end_mill_spec",
        )
        .order_by("-movement_date", "-id")
    )
    if mtype:
        qs = qs.filter(movement_type=mtype)
    if want_cat == "drill":
        qs = qs.filter(tool__category="drill")
    elif want_cat == "tap":
        qs = qs.filter(tool__category="tap")
    elif want_cat == "mill":
        qs = qs.filter(tool__category__in=["end_mill", "body_tool"])
    elif want_cat == "insert":
        qs = qs.filter(tool__category="insert")
    if hole_codes and want_cat != "drill":
        qs = qs.filter(tool__tap_spec__hole_type__in=list(set(hole_codes)))

    rows = []
    for m in qs[:SCAN_LIMIT]:
        if not _hay_matches(_movement_haystack(m), search_tokens, want_cat):
            continue
        rows.append(
            {
                "date": m.movement_date.strftime("%d.%m.%Y"),
                "type": m.get_movement_type_display(),
                "employee": _clip(m.employee_name, 80),
                "tool": _clip(_tool_label(m.tool), 180),
                "qty": m.quantity,
                "comment": _clip(m.comment, 60),
            }
        )
        if len(rows) >= lim:
            break
    empty_hint = ""
    if not rows and want_cat == "drill":
        empty_hint = "Выдач сверла по этому запросу не найдено (метрический метчик сюда не входит)."
    elif not rows and want_cat == "tap":
        empty_hint = f"Выдач метчика по запросу «{q}» с {d_from.strftime('%d.%m.%Y')} по {d_to.strftime('%d.%m.%Y')} не найдено."
    return {
        "query": q,
        "from": d_from.strftime("%d.%m.%Y"),
        "to": d_to.strftime("%d.%m.%Y"),
        "type": mtype or "все",
        "count": len(rows),
        "rows": rows,
        "hint": "Первая строка — самая свежая выдача по запросу." if rows else empty_hint,
    }


def issues_by_employee(
    name: str = "",
    date_from: Any = None,
    date_to: Any = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Выдачи сотруднику за период."""
    emp = _clip(name, MAX_NAME_LEN)
    if len(emp) < 2:
        return {"error": "Укажите ФИО сотрудника (минимум 2 символа).", "rows": []}
    today = timezone.localdate()
    d_to = _parse_date(date_to, default=today) or today
    d_from = _parse_date(date_from, default=d_to - timedelta(days=90)) or (d_to - timedelta(days=90))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    lim = max(1, min(int(limit or 30), MAX_ROWS))

    qs = (
        StockMovement.objects.filter(
            movement_type="issue",
            is_reverted=False,
            movement_date__gte=d_from,
            movement_date__lte=d_to,
            employee_name__icontains=emp,
        )
        .select_related("tool", "tool__insert_spec")
        .order_by("-movement_date", "-id")[:lim]
    )
    rows = []
    for m in qs:
        rows.append(
            {
                "date": m.movement_date.strftime("%d.%m.%Y"),
                "employee": _clip(m.employee_name, 80),
                "tool": _clip(_tool_label(m.tool), 160),
                "qty": m.quantity,
                "comment": _clip(m.comment, 80),
            }
        )
    return {
        "employee_query": emp,
        "from": d_from.strftime("%d.%m.%Y"),
        "to": d_to.strftime("%d.%m.%Y"),
        "count": len(rows),
        "rows": rows,
    }


def top_issued_tools(
    date_from: Any = None,
    date_to: Any = None,
    limit: int = 15,
    category: str = "",
) -> dict[str, Any]:
    """Самые частые выдачи (по сумме количества)."""
    today = timezone.localdate()
    d_to = _parse_date(date_to, default=today) or today
    d_from = _parse_date(date_from, default=d_to - timedelta(days=90)) or (d_to - timedelta(days=90))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    lim = max(1, min(int(limit or 15), MAX_ROWS))
    cat = (category or "").strip()

    qs = StockMovement.objects.filter(
        movement_type="issue",
        is_reverted=False,
        movement_date__gte=d_from,
        movement_date__lte=d_to,
    )
    if cat:
        qs = qs.filter(tool__category=cat)
    agg = (
        qs.values("tool_id", "tool__name", "tool__category")
        .annotate(total_qty=Sum("quantity"), issues=Count("id"))
        .order_by("-total_qty", "-issues")[:lim]
    )
    tool_ids = [r["tool_id"] for r in agg]
    tools = {
        t.id: t
        for t in ToolItem.objects.filter(id__in=tool_ids).select_related("insert_spec")
    }
    rows = []
    for r in agg:
        tool = tools.get(r["tool_id"])
        label = _tool_label(tool) if tool else (r["tool__name"] or "—")
        rows.append(
            {
                "tool": _clip(label, 160),
                "category": tool.get_category_display() if tool else (r["tool__category"] or ""),
                "total_qty": int(r["total_qty"] or 0),
                "issues": int(r["issues"] or 0),
            }
        )
    return {
        "from": d_from.strftime("%d.%m.%Y"),
        "to": d_to.strftime("%d.%m.%Y"),
        "category": cat or "все",
        "rows": rows,
    }


def tool_stock_search(query: str = "", category: str = "", limit: int = 30) -> dict[str, Any]:
    """Поиск позиций на складе по наименованию/бренду."""
    q = _clip(query, MAX_QUERY_LEN)
    if len(q) < 1:
        return {"error": "Укажите строку поиска.", "rows": []}
    lim = max(1, min(int(limit or 30), MAX_ROWS))
    cat = (category or "").strip()

    filt = (
        Q(name__icontains=q)
        | Q(insert_spec__item_name__icontains=q)
        | Q(insert_spec__brand__icontains=q)
        | Q(warehouse_address__icontains=q)
    )
    qs = ToolItem.objects.filter(is_deleted=False).filter(filt).select_related("insert_spec")
    if cat:
        qs = qs.filter(category=cat)
    qs = qs.order_by("-quantity", "name")[:lim]

    rows = []
    for t in qs:
        rows.append(
            {
                "tool": _clip(_tool_label(t), 160),
                "category": t.get_category_display(),
                "qty": t.quantity,
                "address": _clip(getattr(t, "warehouse_address", "") or "", 40),
            }
        )
    return {"query": q, "category": cat or "все", "count": len(rows), "rows": rows}


def top_stock_tools(category: str = "", limit: int = 15, only_positive: Any = True) -> dict[str, Any]:
    """Топ позиций по текущему остатку на складе (не по выдачам)."""
    lim = max(1, min(int(limit or 15), MAX_ROWS))
    cat = (category or "").strip()
    qs = ToolItem.objects.filter(is_deleted=False).select_related("insert_spec")
    if cat:
        qs = qs.filter(category=cat)
    if isinstance(only_positive, bool):
        want_positive = only_positive
    else:
        want_positive = str(only_positive).strip().lower() not in ("0", "false", "no")
    if want_positive:
        qs = qs.filter(quantity__gt=0)
    qs = qs.order_by("-quantity", "name")[:lim]
    rows = []
    for t in qs:
        rows.append(
            {
                "tool": _clip(_tool_label(t), 160),
                "category": t.get_category_display(),
                "qty": t.quantity,
                "address": _clip(getattr(t, "warehouse_address", "") or "", 40),
            }
        )
    return {
        "metric": "текущий остаток на складе",
        "category": cat or "все",
        "count": len(rows),
        "rows": rows,
    }


def recent_movements(
    date_from: Any = None,
    date_to: Any = None,
    movement_type: str = "",
    limit: int = 30,
) -> dict[str, Any]:
    """Последние движения склада."""
    today = timezone.localdate()
    d_to = _parse_date(date_to, default=today) or today
    d_from = _parse_date(date_from, default=d_to - timedelta(days=30)) or (d_to - timedelta(days=30))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    lim = max(1, min(int(limit or 30), MAX_ROWS))
    mtype = (movement_type or "").strip().lower()
    allowed = {"issue", "restock", "writeoff"}
    if mtype and mtype not in allowed:
        return {"error": f"Тип операции: {', '.join(sorted(allowed))} или пусто.", "rows": []}

    qs = StockMovement.objects.filter(
        is_reverted=False,
        movement_date__gte=d_from,
        movement_date__lte=d_to,
    ).select_related("tool", "tool__insert_spec")
    if mtype:
        qs = qs.filter(movement_type=mtype)
    qs = qs.order_by("-movement_date", "-id")[:lim]

    rows = []
    for m in qs:
        rows.append(
            {
                "date": m.movement_date.strftime("%d.%m.%Y"),
                "type": m.get_movement_type_display(),
                "employee": _clip(m.employee_name, 80),
                "tool": _clip(_tool_label(m.tool), 160),
                "qty": m.quantity,
                "comment": _clip(m.comment, 60),
            }
        )
    return {
        "from": d_from.strftime("%d.%m.%Y"),
        "to": d_to.strftime("%d.%m.%Y"),
        "type": mtype or "все",
        "count": len(rows),
        "rows": rows,
    }


def _open_issue_qs():
    """Выдачи с remaining_qty > 0 (не возвращены и не списаны полностью)."""
    return (
        StockMovement.objects.filter(movement_type="issue", is_reverted=False)
        .select_related(
            "tool",
            "tool__insert_spec",
            "tool__tap_spec",
            "tool__drill_spec",
            "tool__end_mill_spec",
        )
        .annotate(
            processed_qty=Coalesce(
                Sum("issue_outcomes__quantity"),
                Value(0, output_field=IntegerField()),
            )
        )
        .annotate(remaining_qty=F("quantity") - F("processed_qty"))
        .filter(remaining_qty__gt=0)
    )


def _limit_n(limit: Any, default: int = 20) -> int:
    try:
        n = int(limit if limit is not None and limit != "" else default)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_ROWS))


def overdue_open_issues(min_days: Any = 14, limit: int = 20) -> dict[str, Any]:
    """Открытые выдачи старше min_days дней (как на вкладке «Анализ»)."""
    try:
        days = int(min_days if min_days is not None and min_days != "" else 14)
    except (TypeError, ValueError):
        days = 14
    days = max(1, min(days, 365))
    lim = _limit_n(limit, 20)
    today = timezone.localdate()
    cutoff = today - timedelta(days=days)
    qs = _open_issue_qs().filter(movement_date__lte=cutoff).order_by("movement_date", "id")[:lim]
    rows = []
    for iss in qs:
        emp = (iss.employee_name or "").strip() or "—"
        rows.append(
            {
                "date": iss.movement_date.strftime("%d.%m.%Y"),
                "days": (today - iss.movement_date).days,
                "employee": _clip(emp, 80),
                "tool": _clip(_tool_label(iss.tool), 180),
                "remaining": int(iss.remaining_qty or 0),
            }
        )
    return {
        "title": f"Просроченные открытые выдачи (≥{days} дн.)",
        "min_days": days,
        "count": len(rows),
        "rows": rows,
        "hint": (
            "Это невозвращённый остаток по выдаче, не «кто последний брал»."
            if rows
            else f"Открытых выдач старше {days} дн. нет."
        ),
    }


def open_issues(employee: str = "", query: str = "", limit: int = 20) -> dict[str, Any]:
    """Кто сейчас держит инструмент (открытые выдачи)."""
    emp = _clip(employee, MAX_NAME_LEN)
    q = _clip(query, MAX_QUERY_LEN)
    lim = _limit_n(limit, 20)
    qs = _open_issue_qs().order_by("-movement_date", "-id")
    if emp:
        qs = qs.filter(employee_name__icontains=emp)
    want_cat = _query_wants_category(q.lower().replace("ё", "е")) if q else ""
    if want_cat == "drill":
        qs = qs.filter(tool__category="drill")
    elif want_cat == "tap":
        qs = qs.filter(tool__category="tap")
    elif want_cat == "mill":
        qs = qs.filter(tool__category__in=["end_mill", "body_tool"])
    elif want_cat == "insert":
        qs = qs.filter(tool__category="insert")
    if q:
        tokens = [t for t in re.split(r"[\s,/|]+", q) if t]
        rows = []
        for iss in qs[:SCAN_LIMIT]:
            if not _hay_matches(_movement_haystack(iss), tokens, want_cat):
                continue
            emp_name = (iss.employee_name or "").strip() or "—"
            rows.append(
                {
                    "date": iss.movement_date.strftime("%d.%m.%Y"),
                    "employee": _clip(emp_name, 80),
                    "tool": _clip(_tool_label(iss.tool), 180),
                    "remaining": int(iss.remaining_qty or 0),
                    "issued": int(iss.quantity or 0),
                }
            )
            if len(rows) >= lim:
                break
    else:
        rows = []
        for iss in qs[:lim]:
            emp_name = (iss.employee_name or "").strip() or "—"
            rows.append(
                {
                    "date": iss.movement_date.strftime("%d.%m.%Y"),
                    "employee": _clip(emp_name, 80),
                    "tool": _clip(_tool_label(iss.tool), 180),
                    "remaining": int(iss.remaining_qty or 0),
                    "issued": int(iss.quantity or 0),
                }
            )
    hint = "На руках — остаток по выдаче (выдано минус возврат/списание)."
    if not rows:
        hint = "Открытых выдач по запросу нет (всё вернули или списали)."
    return {
        "title": "Открытые выдачи (на руках)",
        "employee_query": emp or "все",
        "query": q or "",
        "count": len(rows),
        "rows": rows,
        "hint": hint,
    }


def locate_tool(query: str = "", limit: int = 20) -> dict[str, Any]:
    """Где лежит инструмент: адрес ячейки + остаток."""
    q = _clip(query, MAX_QUERY_LEN)
    if len(q) < 1:
        return {"error": "Укажите что искать (сверло 2.5, адрес A-01-02, APKT…).", "rows": []}
    lim = _limit_n(limit, 20)
    q_low = q.lower().replace("ё", "е")
    want_cat = _query_wants_category(q_low)
    looks_addr = bool(re.search(r"[A-Za-zА-Яа-яЁё0-9]{1,8}-\d", q.replace(" ", "")))

    qs = ToolItem.objects.filter(is_deleted=False).select_related(
        "insert_spec",
        "tap_spec",
        "drill_spec",
        "end_mill_spec",
    )
    if want_cat == "drill":
        qs = qs.filter(category="drill")
    elif want_cat == "tap":
        qs = qs.filter(category="tap")
    elif want_cat == "mill":
        qs = qs.filter(category__in=["end_mill", "body_tool"])
    elif want_cat == "insert":
        qs = qs.filter(category="insert")

    if looks_addr:
        addr = q.replace(" ", "")
        qs = qs.filter(warehouse_address__icontains=addr)
        picked = list(qs.order_by("-quantity", "warehouse_address", "name")[:lim])
    else:
        tokens = [t for t in re.split(r"[\s,/|]+", q) if t]
        picked = []
        for t in qs.order_by("-quantity", "warehouse_address", "name")[:SCAN_LIMIT]:
            hay = _tool_haystack(t) + " " + _norm_hay(t.warehouse_address or "")
            if not _hay_matches(hay, tokens, want_cat):
                continue
            picked.append(t)
            if len(picked) >= lim:
                break
    rows = []
    for t in picked:
        addr = (t.warehouse_address or "").strip()
        rows.append(
            {
                "tool": _clip(_tool_label(t), 180),
                "category": t.get_category_display(),
                "qty": int(t.quantity or 0),
                "address": addr or "— без адреса —",
            }
        )
    empty_hint = "На складе не найдено."
    if want_cat == "drill":
        empty_hint = "Сверла по запросу не найдены (метрический метчик сюда не входит)."
    return {
        "title": "Где лежит (ячейка склада)",
        "query": q,
        "count": len(rows),
        "rows": rows,
        "hint": "Адрес — warehouse_address / визуальный склад." if rows else empty_hint,
    }


def tools_without_address(limit: int = 20, only_positive: Any = True) -> dict[str, Any]:
    """Позиции с остатком без адреса ячейки."""
    lim = _limit_n(limit, 20)
    if isinstance(only_positive, bool):
        want_positive = only_positive
    else:
        want_positive = str(only_positive).strip().lower() not in ("0", "false", "no")
    qs = ToolItem.objects.filter(is_deleted=False).filter(
        Q(warehouse_address="") | Q(warehouse_address__isnull=True)
    )
    if want_positive:
        qs = qs.filter(quantity__gt=0)
    qs = qs.select_related("insert_spec", "tap_spec", "drill_spec").order_by("-quantity", "name")[:lim]
    rows = []
    for t in qs:
        rows.append(
            {
                "tool": _clip(_tool_label(t), 180),
                "category": t.get_category_display(),
                "qty": int(t.quantity or 0),
                "address": "",
            }
        )
    return {
        "title": "Без адреса ячейки",
        "count": len(rows),
        "rows": rows,
        "hint": "У этих позиций не заполнен адрес склада." if rows else "Все показанные позиции с адресом.",
    }


def dead_stock(idle_days: Any = 90, limit: int = 15) -> dict[str, Any]:
    """Остаток есть, движений давно не было."""
    try:
        idle = int(idle_days if idle_days is not None and idle_days != "" else 90)
    except (TypeError, ValueError):
        idle = 90
    idle = max(14, min(idle, 730))
    lim = _limit_n(limit, 15)
    today = timezone.localdate()
    cutoff = today - timedelta(days=idle)
    qs = (
        ToolItem.objects.filter(is_deleted=False, quantity__gt=0)
        .select_related("insert_spec", "tap_spec", "drill_spec")
        .annotate(
            last_move=Max(
                "movements__movement_date",
                filter=Q(movements__is_reverted=False),
            )
        )
        .filter(Q(last_move__isnull=True) | Q(last_move__lt=cutoff))
        .order_by(F("last_move").asc(nulls_first=True), "-quantity", "name")[:lim]
    )
    rows = []
    for t in qs:
        last = t.last_move
        idle_n = (today - last).days if last else None
        rows.append(
            {
                "tool": _clip(_tool_label(t), 180),
                "category": t.get_category_display(),
                "qty": int(t.quantity or 0),
                "address": _clip(getattr(t, "warehouse_address", "") or "", 40),
                "last_move": last.strftime("%d.%m.%Y") if last else "нет",
                "idle_days": idle_n if idle_n is not None else idle,
            }
        )
    return {
        "title": f"Залежь (нет движений ≥{idle} дн., остаток > 0)",
        "idle_days": idle,
        "count": len(rows),
        "rows": rows,
        "hint": "Это не просроченные выдачи, а позиции, которые давно не трогали." if rows else "Залежалых позиций нет.",
    }


def watch_alerts(username: str = "", only_problems: Any = True) -> dict[str, Any]:
    """Шаблоны контроля остатков текущего пользователя (вкладка «Анализ»)."""
    from .inventory_analysis import evaluate_watch_templates, list_watch_templates

    user = _clip(username, 120)
    if not user:
        return {
            "error": "Нет имени пользователя для шаблонов контроля.",
            "rows": [],
            "hint": "Контроль остатков личный — смотрите вкладку «Анализ».",
        }
    if isinstance(only_problems, bool):
        problems_only = only_problems
    else:
        problems_only = str(only_problems).strip().lower() not in ("0", "false", "no")
    templates = list_watch_templates(user)
    evaluated = evaluate_watch_templates(templates)
    rows = []
    ok_n = 0
    for item in evaluated:
        tpl = item["template"]
        status = item["status"]
        if status == "ok":
            ok_n += 1
            if problems_only:
                continue
        rows.append(
            {
                "name": _clip(tpl.name, 80),
                "category": _clip(item.get("category_label") or tpl.category, 40),
                "group": f"{item.get('group_label') or tpl.group_field}: {tpl.group_value}",
                "qty": int(item.get("total_qty") or 0),
                "min_qty": int(tpl.min_qty or 0),
                "status": status,
                "notes": _clip(tpl.notes, 80),
            }
        )
    if not templates:
        hint = "У вас нет активных шаблонов контроля (вкладка «Анализ» склада)."
    elif problems_only and not rows:
        hint = f"Все шаблоны в норме ({ok_n} шт.)."
    else:
        hint = "critical — 0 шт.; warn — ниже минимума; ok — норма."
    return {
        "title": "Контроль остатков (ваши шаблоны)",
        "count": len(rows),
        "ok_count": ok_n,
        "templates_total": len(templates),
        "rows": rows,
        "hint": hint,
    }


def build_control_digest(*, username: str = "") -> str:
    """Короткая строка для снимка: сколько просрочек и алертов контроля."""
    today = timezone.localdate()
    cutoff = today - timedelta(days=14)
    overdue_n = _open_issue_qs().filter(movement_date__lte=cutoff).count()
    open_n = _open_issue_qs().count()
    no_addr_n = (
        ToolItem.objects.filter(is_deleted=False, quantity__gt=0)
        .filter(Q(warehouse_address="") | Q(warehouse_address__isnull=True))
        .count()
    )
    lines = [
        "=== КОНТРОЛЬ (цифры склада, не выдумывай другие) ===",
        f"Открытых выдач (на руках): {open_n}. Просрочено ≥14 дн.: {overdue_n}. Tool: open_issues / overdue_open_issues",
        f"Позиций с остатком без адреса: {no_addr_n}. Tool: tools_without_address / locate_tool",
    ]
    user = (username or "").strip()
    if user:
        try:
            from .inventory_analysis import evaluate_watch_templates, list_watch_templates

            ev = evaluate_watch_templates(list_watch_templates(user))
            bad = sum(1 for x in ev if x.get("status") in {"warn", "critical"})
            lines.append(
                f"Ваши шаблоны контроля: {len(ev)}, ниже минимума: {bad}. Tool: watch_alerts"
            )
        except Exception:
            pass
    return "\n".join(lines)


def build_warehouse_context(
    *,
    max_chars: int | None = None,
    recent_issues: int | None = None,
    username: str = "",
) -> str:
    """
    Компактный снимок склада для промпта: контроль + остатки + свежие выдачи.
    """
    from django.conf import settings

    if max_chars is None:
        max_chars = int(getattr(settings, "YANDEX_GPT_CONTEXT_CHARS", 7000) or 7000)
    if recent_issues is None:
        recent_issues = int(getattr(settings, "YANDEX_GPT_RECENT_ISSUES", 20) or 20)
    max_chars = max(2000, min(int(max_chars), 14000))
    recent_issues = max(5, min(int(recent_issues), 80))
    parts: list[str] = []
    used = 0
    try:
        digest = build_control_digest(username=username)
        parts.append(digest)
        parts.append("")
        used += len(digest) + 1
    except Exception:
        pass

    lim = recent_issues
    issues = (
        StockMovement.objects.filter(movement_type="issue", is_reverted=False)
        .select_related(
            "tool",
            "tool__insert_spec",
            "tool__tap_spec",
            "tool__drill_spec",
        )
        .order_by("-movement_date", "-id")[:lim]
    )
    parts.append(f"=== ПОСЛЕДНИЕ ВЫДАЧИ (до {lim}, свежие сверху; как вкладка История) ===")
    parts.append("Формат: дата | сотрудник | инструмент | qty")
    iss_n = 0
    for m in issues:
        line = (
            f"{m.movement_date.strftime('%d.%m.%Y')} | "
            f"{_clip(m.employee_name, 40) or '—'} | "
            f"{_clip(_tool_label(m.tool), 120)} | "
            f"{m.quantity}"
        )
        parts.append(line)
        used += len(line) + 1
        iss_n += 1
    if iss_n == 0:
        parts.append("(выдач нет)")
    parts.append("Точный поиск выдач — tool search_issues, не выдумывай из этого списка.")
    parts.append("")

    qs = (
        ToolItem.objects.filter(is_deleted=False, quantity__gt=0)
        .select_related("insert_spec", "tap_spec", "drill_spec")
        .order_by("category", "-quantity", "name")
    )
    cat_counts: dict[str, int] = {}
    stock_lines: list[str] = []
    total_qty = 0
    for t in qs:
        cat = t.get_category_display()
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        total_qty += int(t.quantity or 0)
        addr = (getattr(t, "warehouse_address", "") or "").strip()
        line = f"{int(t.quantity)}\t{_tool_label(t)}"
        if addr:
            line += f"\t[{addr}]"
        stock_lines.append(line)

    parts.append("=== ОСТАТКИ НА СКЛАДЕ (кол-во > 0) ===")
    parts.append(
        "Сводка по типам: "
        + (", ".join(f"{k}: {v} поз." for k, v in sorted(cat_counts.items())) or "пусто")
    )
    parts.append(f"Всего позиций: {len(stock_lines)}, суммарно штук: {total_qty}")
    parts.append("Формат: остаток <TAB> позиция [<адрес>]")

    shown = 0
    for line in stock_lines:
        add = len(line) + 1
        if used + add > max_chars - 80:
            parts.append(
                f"… ещё {len(stock_lines) - shown} позиций не влезло (tool_stock_search / top_stock_tools)."
            )
            break
        parts.append(line)
        used += add
        shown += 1

    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…[обрезано]"
    return text


def add_site_note(
    *,
    title: str = "",
    body: str = "",
    username: str = "",
    source_question: str = "",
    page: str = "",
    panel: str = "",
) -> dict[str, Any]:
    text = (body or title or source_question or "").strip()
    if not text:
        return {"ok": False, "error": "Пустая заявка — укажите, что добавить или изменить."}
    head = (title or text).strip().replace("\n", " ")
    if len(head) > 200:
        head = head[:199] + "…"
    note_body = (body or text).strip()
    if len(note_body) > 4000:
        note_body = note_body[:3999] + "…"
    row = SiteNotebookTask.objects.create(
        author_username=(username or "").strip()[:120] or "unknown",
        title=head,
        body=note_body,
        source_question=(source_question or "").strip()[:2000],
        page=(page or "").strip()[:40],
        panel=(panel or "").strip()[:40],
        status=SiteNotebookTask.STATUS_OPEN,
    )
    return {
        "ok": True,
        "id": row.id,
        "title": row.title,
        "reply": (
            f"Записал в блокнот для администратора (№{row.id}): {row.title}. "
            "Админ увидит задачу и отметит, когда сделает."
        ),
    }


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "search_issues": {
        "description": (
            "Поиск ВЫДАЧ по названию/типу инструмента: «кто брал метчик M3», «сквозной/глухой», "
            "«сверло 2.5», APKT и т.п. Возвращает последние подходящие операции (свежие сверху). "
            "Используй для вопросов «кто последний брал …»."
        ),
        "args": {
            "query": "фраза поиска, напр. метчик M3 сквозной (обязательно)",
            "date_from": "начало периода (по умолчанию −180 дней)",
            "date_to": "конец периода (сегодня)",
            "limit": "до 50",
            "movement_type": "issue (по умолчанию) | restock | writeoff | all",
        },
        "fn": search_issues,
    },
    "top_stock_tools": {
        "description": (
            "Топ позиций по ТЕКУЩЕМУ ОСТАТКУ на складе (поле quantity). "
            "Используй для вопросов «какой позиции больше всего», «где самый большой остаток», "
            "«топ по количеству на складе». Это НЕ про выдачи."
        ),
        "args": {
            "category": "ключ категории: insert, end_mill, drill, … или пусто",
            "limit": "сколько позиций (до 50), по умолчанию 15",
            "only_positive": "true — только с остатком > 0 (по умолчанию)",
        },
        "fn": top_stock_tools,
    },
    "issues_by_employee": {
        "description": "Выдачи инструмента сотруднику по ФИО за период (date_from/date_to).",
        "args": {
            "name": "ФИО или фрагмент (обязательно)",
            "date_from": "дата начала YYYY-MM-DD или ДД.ММ.ГГГГ (по умолчанию −90 дней)",
            "date_to": "дата конца (по умолчанию сегодня)",
            "limit": "макс. строк, до 50",
        },
        "fn": issues_by_employee,
    },
    "top_issued_tools": {
        "description": (
            "Топ по ВЫДАЧАМ / использованию за период (что чаще выдавали, популярные позиции). "
            "Для «какие позиции чаще используют», «топ выдач», «расход». "
            "НЕ для вопроса про текущий остаток на складе."
        ),
        "args": {
            "date_from": "начало периода",
            "date_to": "конец периода",
            "limit": "сколько позиций (до 50)",
            "category": "ключ категории: insert, end_mill, drill, … или пусто",
        },
        "fn": top_issued_tools,
    },
    "tool_stock_search": {
        "description": "Поиск остатков на складе по наименованию/бренду.",
        "args": {
            "query": "строка поиска (обязательно)",
            "category": "категория или пусто",
            "limit": "до 50",
        },
        "fn": tool_stock_search,
    },
    "recent_movements": {
        "description": "Последние операции склада: выдача/пополнение/списание.",
        "args": {
            "date_from": "начало",
            "date_to": "конец",
            "movement_type": "issue | restock | writeoff | пусто",
            "limit": "до 50",
        },
        "fn": recent_movements,
    },
    "overdue_open_issues": {
        "description": (
            "Просроченные ОТКРЫТЫЕ выдачи: инструмент не вернули N дней. "
            "Не для «кто последний брал» (это search_issues)."
        ),
        "args": {
            "min_days": "порог дней, по умолчанию 14",
            "limit": "до 50",
        },
        "fn": overdue_open_issues,
    },
    "open_issues": {
        "description": (
            "Что сейчас НА РУКАХ: невозвращённый остаток по выдаче. "
            "employee — ФИО, query — сверло 2.5 и т.п."
        ),
        "args": {
            "employee": "фрагмент ФИО или пусто",
            "query": "фильтр инструмента или пусто",
            "limit": "до 50",
        },
        "fn": open_issues,
    },
    "locate_tool": {
        "description": (
            "ГДЕ ЛЕЖИТ: адрес ячейки + остаток. Сверло ≠ метчик. "
            "Можно искать по адресу вида A-01-02."
        ),
        "args": {
            "query": "что искать (обязательно)",
            "limit": "до 50",
        },
        "fn": locate_tool,
    },
    "tools_without_address": {
        "description": "Позиции с остатком БЕЗ адреса ячейки.",
        "args": {
            "limit": "до 50",
            "only_positive": "true — только qty>0",
        },
        "fn": tools_without_address,
    },
    "dead_stock": {
        "description": "Залежь: остаток > 0 и давно не было движений. Не путать с просроченными выдачами.",
        "args": {
            "idle_days": "порог дней, по умолчанию 90",
            "limit": "до 50",
        },
        "fn": dead_stock,
    },
    "watch_alerts": {
        "description": (
            "Личные шаблоны КОНТРОЛЯ остатков (вкладка Анализ): ниже минимума / ноль. "
            "Не топ остатков."
        ),
        "args": {
            "only_problems": "true — только warn/critical",
        },
        "fn": watch_alerts,
    },
    "add_site_note": {
        "description": (
            "Записать в блокнот админа заявку на ДОРАБОТКУ САЙТА "
            "(добавить функцию, исправить UX, изменить фильтр и т.п.). "
            "НЕ для складских вопросов. Пользователь просит что-то сделать на сайте — "
            "сразу вызывай этот tool."
        ),
        "args": {
            "title": "краткий заголовок (до 120 символов)",
            "body": "что именно нужно добавить или изменить",
        },
        "fn": add_site_note,
    },
}


def tools_schema_for_prompt() -> str:
    return (
        "Tools: "
        "overdue_open_issues{min_days?,limit?} — просроченные невозвраты; "
        "open_issues{employee?,query?,limit?} — сейчас на руках; "
        "locate_tool{query,limit?} — адрес ячейки; "
        "tools_without_address{limit?}; "
        "watch_alerts{only_problems?} — ваши шаблоны контроля; "
        "dead_stock{idle_days?,limit?} — залежь; "
        "search_issues{query} — кто брал (история); "
        "top_issued_tools — чаще выдавали; "
        "top_stock_tools — топ остатков; "
        "tool_stock_search{query}; "
        "issues_by_employee{name}; "
        "recent_movements{movement_type?}; "
        "add_site_note{title,body} — заявка на доработку сайта в блокнот админа. "
        'Формат: {"tool":"имя","args":{...}}'
    )


def run_tool(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if not spec:
        return {"error": f"Неизвестный инструмент: {name}"}
    fn: Callable[..., dict[str, Any]] = spec["fn"]
    raw = args if isinstance(args, dict) else {}
    allowed = set(spec["args"].keys())
    clean = {k: v for k, v in raw.items() if k in allowed}
    ctx = context if isinstance(context, dict) else {}
    if name == "watch_alerts":
        clean["username"] = str(ctx.get("username") or "")[:120]
    if name == "add_site_note":
        clean["username"] = str(ctx.get("username") or "")[:120]
        clean["source_question"] = str(ctx.get("source_question") or "")[:2000]
        pc = ctx.get("page_context") if isinstance(ctx.get("page_context"), dict) else {}
        if not clean.get("page"):
            clean["page"] = str(pc.get("page") or "")[:40]
        if not clean.get("panel"):
            clean["panel"] = str(pc.get("panel") or "")[:40]
    try:
        return fn(**clean)
    except Exception as exc:  # noqa: BLE001 — отдаём модели текст ошибки
        return {"error": f"Ошибка выполнения {name}: {exc}"}
