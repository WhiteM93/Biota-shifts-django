"""Read-only инструменты склада для чата YandexGPT."""
from __future__ import annotations

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
    return f"{cat} · {name}" if name else cat


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


TOOL_SPECS: dict[str, dict[str, Any]] = {
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
    lines = ["Доступные инструменты (вызови один, верни JSON):"]
    for name, spec in TOOL_SPECS.items():
        args = ", ".join(f"{k}: {v}" for k, v in spec["args"].items())
        lines.append(f"- {name}: {spec['description']} Аргументы: {args}")
    lines.append(
        'Формат вызова: {"tool":"имя","args":{...}} — только JSON, без пояснений. '
        "Если данных достаточно для ответа пользователю — ответь обычным текстом на русском."
    )
    return "\n".join(lines)


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
