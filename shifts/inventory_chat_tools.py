"""Read-only инструменты склада для чата YandexGPT."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Callable

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import StockMovement, ToolItem

MAX_ROWS = 50
MAX_QUERY_LEN = 120
MAX_NAME_LEN = 120


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
        .select_related("tool", "tool__insert_spec", "tool__tap_spec", "tool__drill_spec")
        .order_by("-movement_date", "-id")
    )
    if mtype:
        qs = qs.filter(movement_type=mtype)
    if hole_codes:
        qs = qs.filter(tool__tap_spec__hole_type__in=list(set(hole_codes)))

    for tok in search_tokens:
        tok_q = (
            Q(tool__name__icontains=tok)
            | Q(tool__tap_spec__size_label__icontains=tok)
            | Q(tool__insert_spec__item_name__icontains=tok)
            | Q(tool__insert_spec__brand__icontains=tok)
            | Q(tool__collet_spec__size_label__icontains=tok)
            | Q(comment__icontains=tok)
            | Q(employee_name__icontains=tok)
        )
        low = tok.lower().replace("ё", "е")
        if "метчик" in low or "tap" in low:
            tok_q |= Q(tool__category="tap")
        if "сверл" in low or "drill" in low:
            tok_q |= Q(tool__category="drill")
        if "пластин" in low or "insert" in low:
            tok_q |= Q(tool__category="insert")
        if "фрез" in low:
            tok_q |= Q(tool__category="end_mill") | Q(tool__category="body_tool")
        qs = qs.filter(tok_q)

    rows = []
    for m in qs[:lim]:
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
    return {
        "query": q,
        "from": d_from.strftime("%d.%m.%Y"),
        "to": d_to.strftime("%d.%m.%Y"),
        "type": mtype or "все",
        "count": len(rows),
        "rows": rows,
        "hint": "Первая строка — самая свежая выдача по запросу." if rows else "",
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
    )
    qs = ToolItem.objects.filter(filt).select_related("insert_spec")
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
    qs = ToolItem.objects.all().select_related("insert_spec")
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


def build_warehouse_context(*, max_chars: int | None = None, recent_issues: int | None = None) -> str:
    """
    Компактный снимок склада для промпта: остатки + свежие выдачи.
    Модель видит данные сразу, без отдельного tool-вызова.
    """
    from django.conf import settings

    if max_chars is None:
        max_chars = int(getattr(settings, "YANDEX_GPT_CONTEXT_CHARS", 7000) or 7000)
    if recent_issues is None:
        recent_issues = int(getattr(settings, "YANDEX_GPT_RECENT_ISSUES", 20) or 20)
    max_chars = max(2000, min(int(max_chars), 14000))
    recent_issues = max(5, min(int(recent_issues), MAX_ROWS))
    parts: list[str] = []
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

    budget = max_chars - 800
    used = 0
    shown = 0
    for line in stock_lines:
        add = len(line) + 1
        if used + add > budget:
            parts.append(f"… ещё {len(stock_lines) - shown} позиций не влезло в снимок (зови tool_stock_search / top_stock_tools).")
            break
        parts.append(line)
        used += add
        shown += 1

    lim = max(1, min(int(recent_issues or 40), MAX_ROWS))
    issues = (
        StockMovement.objects.filter(movement_type="issue", is_reverted=False)
        .select_related("tool", "tool__insert_spec", "tool__tap_spec")
        .order_by("-movement_date", "-id")[:lim]
    )
    parts.append("")
    parts.append(f"=== ПОСЛЕДНИЕ ВЫДАЧИ (до {lim}, свежие сверху) ===")
    parts.append("Формат: дата | сотрудник | инструмент | qty")
    iss_n = 0
    for m in issues:
        line = (
            f"{m.movement_date.strftime('%d.%m.%Y')} | "
            f"{_clip(m.employee_name, 40) or '—'} | "
            f"{_clip(_tool_label(m.tool), 120)} | "
            f"{m.quantity}"
        )
        if used + len(line) + 1 > max_chars:
            parts.append("… список выдач обрезан по размеру контекста.")
            break
        parts.append(line)
        used += len(line) + 1
        iss_n += 1
    if iss_n == 0:
        parts.append("(выдач нет)")

    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…[обрезано]"
    return text


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
            "Топ по ВЫДАЧАМ за период (сколько раз/штук выдавали). "
            "Только если явно спрашивают про выдачи/расход/«что чаще выдавали». "
            "НЕ используй для вопроса про остаток на складе."
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
}


def tools_schema_for_prompt() -> str:
    # Короткий список — экономия входных токенов
    return (
        "Tools (JSON only if snapshot недостаточно): "
        "search_issues{query,date_from?,date_to?,limit?}; "
        "top_stock_tools{category?,limit?}; "
        "top_issued_tools{date_from?,date_to?,limit?,category?}; "
        "issues_by_employee{name,date_from?,date_to?,limit?}; "
        "tool_stock_search{query,category?,limit?}; "
        "recent_movements{date_from?,date_to?,movement_type?,limit?}. "
        'Формат: {"tool":"имя","args":{...}}'
    )


def run_tool(name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if not spec:
        return {"error": f"Неизвестный инструмент: {name}"}
    fn: Callable[..., dict[str, Any]] = spec["fn"]
    raw = args if isinstance(args, dict) else {}
    # только известные ключи
    allowed = set(spec["args"].keys())
    clean = {k: v for k, v in raw.items() if k in allowed}
    try:
        return fn(**clean)
    except Exception as exc:  # noqa: BLE001 — отдаём модели текст ошибки
        return {"error": f"Ошибка выполнения {name}: {exc}"}
