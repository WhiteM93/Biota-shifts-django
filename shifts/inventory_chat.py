"""Оркестратор чата склада: YandexGPT + снимок склада + tools."""
from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings

from .inventory_chat_tools import build_warehouse_context, run_tool, tools_schema_for_prompt
from .yandex_gpt import YandexGptError, complete, yandex_gpt_configured

SYSTEM_PROMPT = """Склад Biota. Отвечай кратко по-русски.
Факты только из tools (search_issues и др.) — это те же выдачи, что вкладка История.
Не выдумывай цифры и не подменяй ø2.3 вместо ø3.5. Даты ДД.ММ.ГГГГ. Только чтение склада.

Типы не путать: сверло ⌀2.5 ≠ метчик M2.5 / M5.

Если пользователь просит ДОБАВИТЬ / ИЗМЕНИТЬ / ИСПРАВИТЬ что-то на САЙТЕ
(кнопка, вкладка, фильтр, форма, удобство) — вызывай add_site_note{title,body}.
Это пишется в блокнот админа. Не путай с вопросами про складской остаток.

Вызывай tool JSON сам (не проси пользователя):
- «кто брал …» / «а сверла 3.5» → search_issues;
- «на руках / не вернул / кто держит» → open_issues;
- «просрочено / давно не вернули» → overdue_open_issues;
- «где лежит / ячейка / адрес» → locate_tool;
- «без адреса» → tools_without_address;
- «контроль / кончается / ниже минимума» → watch_alerts;
- «залежь / давно не двигался» → dead_stock;
- «чаще используют / топ выдач» → top_issued_tools (НЕ остатки);
- «больше всего на складе» → top_stock_tools;
- «добавь на сайт / нужно сделать / исправь интерфейс / запиши в блокнот» → add_site_note.
На «проводи / точнее» — снова тот же класс tool.
Формат только: {"tool":"имя","args":{...}} если нужен tool."""

_TOOL_JSON_RE = re.compile(
    r"\{[^{}]*\"tool\"\s*:\s*\"[a-z_]+\"[^{}]*\}",
    re.DOTALL,
)

_USAGE_RE = re.compile(
    r"част(о|ее)|использу|популярн|топ\s*выдач|выдавал|расход|что\s*берут|чаще\s*всего",
    re.IGNORECASE,
)
_STOCK_TOP_RE = re.compile(
    r"топ\s*остат|остатк\w*\s*больш|больше\s*всего\s*(на\s*)?склад|како[йя]\s+позици\w*.*больш",
    re.IGNORECASE,
)
_FOLLOW_RE = re.compile(
    r"^(проведи|проводи|сделай|давай|точнее|анализ|посчитай|выполни|ну\s*давай)\b",
    re.IGNORECASE,
)
_TOOLISH_RE = re.compile(
    r"сверл|метчик|раскат|резьб|фрез|пластин|зенкер|цанг|разверт|apkt|rpmt|"
    r"[mм]\s*\d|[dø⌀]\s*\d|\d+[.,]\d+|\b\d{1,2}\b",
    re.IGNORECASE,
)
_SHORT_FOLLOW_RE = re.compile(r"^(?:а|и|ещё|еще|ну)\s+", re.IGNORECASE)
_WHO_RE = re.compile(
    r"кто\s+(?:последн\w*\s+)?брал|кто\s+выдавал|последн\w*\s+брал",
    re.IGNORECASE,
)
_OVERDUE_RE = re.compile(
    r"просроч|давно\s+не\s+верн|задерж\w*\s+выдач|не\s+вернул\w*\s+больше|"
    r"старше\s+\d+\s*дн|более\s+\d+\s*дн",
    re.IGNORECASE,
)
_WATCH_RE = re.compile(
    r"контрол\w*\s+остат|шаблон\w*\s+контрол|что\s+конча|"
    r"мало\s+(?:на\s+складе|инструмент)|ниже\s+минимум|критичн\w*\s+остат|"
    r"watch|покажи\s+контроль|^контроль$",
    re.IGNORECASE,
)
_LOCATE_RE = re.compile(
    r"где\s+леж|в\s+какой\s+ячейк|адрес\s+(?:ячейк|склад)|куда\s+полож|"
    r"найди\s+адрес|в\s+какой\s+клетк",
    re.IGNORECASE,
)
_HOLD_RE = re.compile(
    r"на\s+руках|не\s+возвращ|открыт\w*\s+выдач|кто\s+держит|кто\s+не\s+верн|"
    r"у\s+кого\s+(?:сейчас\s+)?(?:на\s+руках|инструмент)|что\s+не\s+вернул",
    re.IGNORECASE,
)
_DEAD_RE = re.compile(
    r"мертв\w*\s+запас|мёртв\w*\s+запас|залеж|давно\s+не\s+двиг|"
    r"не\s+ходов|не\s+трогал",
    re.IGNORECASE,
)
_NO_ADDR_RE = re.compile(
    r"без\s+адреса|нет\s+адреса|не\s+привязан\w*\s+(?:к\s+)?ячейк|пуст\w*\s+адрес",
    re.IGNORECASE,
)
_RECENT_RE = re.compile(
    r"последн\w*\s+(?:движен|операц)|свеж\w*\s+(?:приход|списан|выдач)",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(
    r"^(?:сводка|что\s+тут|что\s+важно|что\s+критичн|покажи\s+контроль)\b",
    re.IGNORECASE,
)
_NOTEBOOK_RE = re.compile(
    r"запиши\s+(?:в\s+)?блокнот|в\s+блокнот|"
    r"добав\w*\s+(?:на\s+сайт|в\s+сайт|кнопк|вкладк|фильтр|поле|функци)|"
    r"нужно\s+(?:добавить|сделать|доработать|исправить|улучшить)|"
    r"хочу\s+(?:чтобы|чтоб)\s+(?:на\s+сайте\s+)?(?:добав|сделал|доработ|исправ)|"
    r"доработк\w*\s+сайт|улучш\w*\s+сайт|исправ\w*\s+(?:на\s+сайте|в\s+интерфейс|ux)|"
    r"можно\s+ли\s+добавить|добавьте\s+(?:кнопк|вкладк|фильтр|поле)|"
    r"задача\s+для\s+админ|предложени\w*\s+(?:по\s+)?(?:сайт|доработ|улучшен)|"
    r"feature\s*request|сделай\s+(?:чтобы|чтоб)\s+(?:на\s+сайте|в\s+кабинет|в\s+складе)",
    re.IGNORECASE,
)
_REFUSAL_RE = re.compile(
    r"не\s+могу\s+выполнить|вам\s+нужно|используйте\s+инструмент|запросить\s+этот\s+инструмент|"
    r"в\s+рамках\s+текущего\s+доступа",
    re.IGNORECASE,
)
_EMPTYISH_RE = re.compile(
    r"не\s+найден|ничего\s+не\s+найден|нет\s+выдач|выдач\w*\s+не\s+найден",
    re.IGNORECASE,
)


def _extract_tool_call(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    candidates = [raw]
    m = _TOOL_JSON_RE.search(raw)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("tool"), str):
            args = data.get("args")
            if args is None:
                args = {k: v for k, v in data.items() if k != "tool"}
            if not isinstance(args, dict):
                args = {}
            return {"tool": data["tool"].strip(), "args": args}
    return None


def _history_blob(history: list[dict[str, str]] | None, *, max_turns: int = 4) -> str:
    parts: list[str] = []
    if not history:
        return ""
    for item in history[-max_turns:]:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or item.get("content") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


_ALLOWED_PAGES = frozenset(
    {
        "inventory",
        "visual_warehouse",
        "products",
        "machines",
        "home",
        "hours",
        "skud",
        "graph",
        "cabinet",
        "calculator",
        "contracts",
        "forms",
        "other",
    }
)
_ALLOWED_PANELS = frozenset(
    {
        "",
        "stock",
        "history",
        "issue",
        "issue_outcome",
        "arrival",
        "purchases",
        "analysis",
        "defects",
        "payroll",
        "employees",
    }
)
_PANEL_LABELS = {
    "stock": "остатки",
    "history": "история",
    "issue": "выдача",
    "issue_outcome": "возврат/списание",
    "arrival": "приход",
    "purchases": "закупки",
    "analysis": "анализ склада",
    "defects": "брак",
    "payroll": "зарплата",
    "employees": "сотрудники",
}
_FACT_REPLY_TOOLS = frozenset(
    {
        "search_issues",
        "open_issues",
        "locate_tool",
        "issues_by_employee",
        "overdue_open_issues",
    }
)
_FORCED_KEEP = frozenset(
    {
        "search_issues",
        "overdue_open_issues",
        "open_issues",
        "locate_tool",
        "watch_alerts",
        "dead_stock",
        "tools_without_address",
        "top_issued_tools",
        "top_stock_tools",
        "recent_movements",
        "add_site_note",
    }
)


def normalize_page_context(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {"page": "other", "panel": ""}
    page = str(raw.get("page") or "other").strip()[:40]
    panel = str(raw.get("panel") or "").strip()[:40]
    if page not in _ALLOWED_PAGES:
        page = "other"
    if panel not in _ALLOWED_PANELS:
        panel = ""
    return {"page": page, "panel": panel}


def _page_prompt_line(page_context: dict[str, str] | None) -> str:
    ctx = normalize_page_context(page_context or {})
    page = ctx["page"]
    panel = ctx["panel"]
    if page == "inventory":
        label = _PANEL_LABELS.get(panel, panel or "склад")
        return f"Пользователь на складе, вкладка: {label}."
    if page == "visual_warehouse":
        return "Пользователь на визуальном складе (ячейки/адреса)."
    if page == "products":
        return "Пользователь в наладках; складские вопросы всё равно через tools склада."
    return ""


def _strip_prefix(src: str, patterns: list[str]) -> str:
    text = (src or "").strip()
    for pat in patterns:
        text = re.sub(pat, "", text, count=1, flags=re.IGNORECASE).strip()
    return text


def _extract_hold_employee(q: str) -> str:
    m = re.search(
        r"у\s+([А-ЯЁA-Z][\w.\-]{1,40}(?:\s+[А-ЯЁA-Z][\w.\-]{1,40}){0,2})\s+"
        r"(?:на\s+руках|не\s+верн|держит)",
        q or "",
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()[:80]
    m = re.search(r"сотрудник[ауе]?\s+(.{2,40})$", q or "", re.IGNORECASE)
    if m:
        return m.group(1).strip()[:80]
    return ""


def _panel_summary_tool(page_context: dict[str, str] | None) -> dict[str, Any] | None:
    ctx = normalize_page_context(page_context or {})
    page, panel = ctx["page"], ctx["panel"]
    if page == "inventory" and panel in {"analysis", "issue_outcome"}:
        return {"tool": "overdue_open_issues", "args": {"min_days": 14, "limit": 20}}
    if page == "inventory" and panel == "issue":
        return {"tool": "open_issues", "args": {"limit": 20}}
    if page == "inventory" and panel == "purchases":
        return {"tool": "watch_alerts", "args": {"only_problems": True}}
    if page == "inventory" and panel in {"stock", "arrival"}:
        return {"tool": "tools_without_address", "args": {"limit": 15}}
    if page == "visual_warehouse":
        return {"tool": "tools_without_address", "args": {"limit": 15}}
    if page == "inventory" and panel == "history":
        return {"tool": "recent_movements", "args": {"limit": 20}}
    return None


def forced_tool_call(
    question: str,
    history: list[dict[str, str]] | None = None,
    page_context: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Маршрутизатор для Lite: факты считает Python, не снимок."""
    q = (question or "").strip()
    if not q:
        return None
    hist = _history_blob(history)
    blob = f"{q}\n{hist}"
    usage = bool(_USAGE_RE.search(q) or (_FOLLOW_RE.search(q) and _USAGE_RE.search(blob)))
    stock_top = bool(_STOCK_TOP_RE.search(q) or (_FOLLOW_RE.search(q) and _STOCK_TOP_RE.search(blob)))
    who = bool(_WHO_RE.search(q) or (_FOLLOW_RE.search(q) and _WHO_RE.search(blob)))
    overdue = bool(_OVERDUE_RE.search(q) or (_FOLLOW_RE.search(q) and _OVERDUE_RE.search(blob)))
    watch = bool(_WATCH_RE.search(q) or (_FOLLOW_RE.search(q) and _WATCH_RE.search(blob)))
    locate = bool(_LOCATE_RE.search(q) or (_FOLLOW_RE.search(q) and _LOCATE_RE.search(blob)))
    hold = bool(_HOLD_RE.search(q) or (_FOLLOW_RE.search(q) and _HOLD_RE.search(blob)))
    dead = bool(_DEAD_RE.search(q) or (_FOLLOW_RE.search(q) and _DEAD_RE.search(blob)))
    no_addr = bool(_NO_ADDR_RE.search(q) or (_FOLLOW_RE.search(q) and _NO_ADDR_RE.search(blob)))
    recent = bool(_RECENT_RE.search(q) or (_FOLLOW_RE.search(q) and _RECENT_RE.search(blob)))
    notebook = bool(_NOTEBOOK_RE.search(q))

    if notebook:
        return {"tool": "add_site_note", "args": {"title": q[:120], "body": q[:2000]}}
    if who and not hold:
        src = q if _WHO_RE.search(q) else blob
        tool_q = _strip_prefix(
            src,
            [
                r"^(?:скажи|подскажи)?\s*кто\s+(?:последн\w*\s+)?брал\s+",
                r"^кто\s+выдавал\s+",
            ],
        )
        if not tool_q or len(tool_q) < 2:
            tool_q = q
        return {"tool": "search_issues", "args": {"query": tool_q[:120], "limit": 20}}
    if overdue:
        return {"tool": "overdue_open_issues", "args": {"min_days": 14, "limit": 20}}
    if watch:
        return {"tool": "watch_alerts", "args": {"only_problems": True}}
    if locate:
        src = q if _LOCATE_RE.search(q) else blob
        tool_q = _strip_prefix(
            src,
            [
                r"^.*?(?:где\s+лежит|в\s+какой\s+ячейке|найди\s+адрес|куда\s+положили)\s+",
            ],
        )
        if not tool_q or len(tool_q) < 2:
            tool_q = q
        return {"tool": "locate_tool", "args": {"query": tool_q[:120], "limit": 20}}
    if hold:
        src = q if _HOLD_RE.search(q) else blob
        emp = _extract_hold_employee(src)
        tool_q = _strip_prefix(
            src,
            [
                r"^.*?(?:на\s+руках|кто\s+держит|открытые\s+выдачи)\s+",
                r"^у\s+[^\s]+(?:\s+[^\s]+){0,2}\s+",
            ],
        )
        args: dict[str, Any] = {"limit": 20}
        if emp:
            args["employee"] = emp
        leftover = tool_q
        for noise in ("на руках", "не возвращено", "открытые выдачи", "кто держит"):
            leftover = re.sub(re.escape(noise), "", leftover, flags=re.IGNORECASE).strip()
        leftover = leftover.strip(" ?.,:—-")
        if leftover and leftover.lower() not in {(emp or "").lower(), "инструмент", "что"}:
            if emp and leftover.lower() == emp.lower():
                leftover = ""
            elif re.search(
                r"\d|сверл|метчик|фрез|пластин|apkt|rpmt|разверт|зенкер|цанг",
                leftover,
                re.IGNORECASE,
            ):
                args["query"] = leftover[:120]
        return {"tool": "open_issues", "args": args}
    if dead:
        return {"tool": "dead_stock", "args": {"idle_days": 90, "limit": 15}}
    if no_addr:
        return {"tool": "tools_without_address", "args": {"limit": 20}}
    if recent and not who:
        return {"tool": "recent_movements", "args": {"limit": 20}}
    if _SUMMARY_RE.search(q):
        summary = _panel_summary_tool(page_context)
        if summary:
            return summary
    if usage and not (stock_top and not _USAGE_RE.search(q)):
        return {"tool": "top_issued_tools", "args": {"limit": 15}}
    if stock_top:
        return {"tool": "top_stock_tools", "args": {"limit": 15}}
    if _TOOLISH_RE.search(q):
        tool_q = _strip_prefix(
            q,
            [
                r"^(?:а|и|ещё|еще|ну)\s+",
                r"^(?:скажи|подскажи)?\s*кто\s+(?:последн\w*\s+)?брал\s+",
                r"^кто\s+выдавал\s+",
            ],
        )
        if not tool_q or len(tool_q) < 2:
            tool_q = q
        return {"tool": "search_issues", "args": {"query": tool_q[:120], "limit": 20}}
    return None


def _history_messages(history: list[dict[str, str]] | None, *, max_turns: int = 4) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not history:
        return out
    for item in history[-max_turns:]:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip()
        text = (item.get("text") or item.get("content") or "").strip()
        if role in {"user", "assistant"} and text:
            out.append({"role": role, "text": text[:800]})
    return out


def _pick_tool_call(
    first: str,
    question: str,
    history: list[dict[str, str]] | None,
    page_context: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    forced = forced_tool_call(question, history, page_context)
    call = _extract_tool_call(first)
    if forced:
        if forced.get("tool") in _FORCED_KEEP:
            return forced
        if not call or call.get("tool") in {"top_stock_tools", "top_issued_tools"}:
            return forced
        return call
    if call:
        return call
    if _REFUSAL_RE.search(first or ""):
        return forced_tool_call(question, history, page_context) or {
            "tool": "overdue_open_issues",
            "args": {"min_days": 14, "limit": 15},
        }
    return None


def ask_inventory_chat(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    page_context: dict[str, str] | None = None,
    username: str = "",
) -> dict[str, Any]:
    q = (question or "").strip()
    if not q:
        return {"ok": False, "error": "Пустой вопрос."}
    if len(q) > 800:
        return {"ok": False, "error": "Слишком длинный вопрос."}
    if not yandex_gpt_configured():
        return {
            "ok": False,
            "error": "Чат не настроен: задайте YANDEX_GPT_API_KEY и YANDEX_GPT_FOLDER_ID в .env.secrets.",
        }

    page_ctx = normalize_page_context(page_context)
    used_tools: list[str] = []
    try:
        snapshot = build_warehouse_context(username=username or "")
    except Exception as exc:  # noqa: BLE001
        snapshot = f"(снимок склада недоступен: {exc})"

    max_sys = int(getattr(settings, "YANDEX_GPT_CONTEXT_CHARS", 7000) or 7000) + 1200
    page_line = _page_prompt_line(page_ctx)
    system_text = SYSTEM_PROMPT
    if page_line:
        system_text += "\n" + page_line
    system_text += "\n" + tools_schema_for_prompt() + "\n\n" + snapshot
    messages: list[dict[str, str]] = [
        {"role": "system", "text": system_text[:max_sys]},
    ]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "text": q[:800]})

    max_out = int(getattr(settings, "YANDEX_GPT_MAX_TOKENS", 700) or 700)

    forced_first = forced_tool_call(q, history, page_ctx)
    first = ""
    if forced_first:
        call = forced_first
    else:
        try:
            first = complete(messages, max_tokens=max_out)
        except YandexGptError as exc:
            return {"ok": False, "error": str(exc)}
        call = _pick_tool_call(first, q, history, page_ctx)
        if not call:
            return {"ok": True, "reply": first, "used_tools": used_tools}

    tool_name = call["tool"]
    tool_result = run_tool(
        tool_name,
        call.get("args") or {},
        context={
            "username": username or "",
            "source_question": q,
            "page_context": page_ctx,
        },
    )
    used_tools.append(tool_name)

    if tool_name == "add_site_note":
        if tool_result.get("ok"):
            return {
                "ok": True,
                "reply": tool_result.get("reply")
                or "Записал в блокнот для администратора.",
                "used_tools": used_tools,
                "notebook_id": tool_result.get("id"),
            }
        return {
            "ok": False,
            "error": tool_result.get("error") or "Не удалось записать в блокнот.",
            "used_tools": used_tools,
        }

    if tool_name in _FACT_REPLY_TOOLS:
        return {
            "ok": True,
            "reply": _fallback_reply(tool_result),
            "used_tools": used_tools,
        }

    empty_msg = "Если rows пустой — скажи, что по этому смыслу ничего не найдено (не подменяй сверло метчиком)."
    messages.append({"role": "assistant", "text": json.dumps(call, ensure_ascii=False)})
    messages.append(
        {
            "role": "user",
            "text": (
                f"Результат {tool_name}:\n"
                f"{json.dumps(tool_result, ensure_ascii=False)[:3500]}\n"
                f"Ответь только по этому результату. {empty_msg} Без JSON. "
                "Не предлагай пользователю вызывать tools."
            ),
        }
    )
    try:
        second = complete(messages, max_tokens=max_out)
    except YandexGptError as exc:
        return {
            "ok": True,
            "reply": _fallback_reply(tool_result),
            "used_tools": used_tools,
            "error": str(exc),
        }

    call2 = _extract_tool_call(second)
    rows = tool_result.get("rows") if isinstance(tool_result, dict) else None
    has_rows = isinstance(rows, list) and bool(rows)
    if call2 or _REFUSAL_RE.search(second or "") or (has_rows and _EMPTYISH_RE.search(second or "")):
        return {
            "ok": True,
            "reply": _fallback_reply(tool_result),
            "used_tools": used_tools,
        }
    return {"ok": True, "reply": second, "used_tools": used_tools}


def _fallback_reply(tool_result: dict[str, Any]) -> str:
    if tool_result.get("error"):
        return str(tool_result["error"])
    rows = tool_result.get("rows")
    hint = (tool_result.get("hint") or "").strip()
    if isinstance(rows, list) and not rows:
        return hint or "По запросу ничего не найдено."
    metric = (tool_result.get("metric") or "").strip()
    title = (tool_result.get("title") or "").strip()
    d_from = tool_result.get("from") or ""
    d_to = tool_result.get("to") or ""
    first = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    looks_like_issues = bool(first.get("employee"))
    if title:
        head = title
    elif "остат" in metric.lower():
        head = "Топ по остатку на складе"
    elif looks_like_issues:
        head = "Выдачи"
    elif d_from or "выдач" in metric.lower():
        head = "Топ по выдачам"
    else:
        head = "Найдено"
    if d_from and d_to and "(" not in head:
        head += f" ({d_from} — {d_to})"
    if isinstance(rows, list):
        lines = []
        for i, row in enumerate(rows[:15], start=1):
            if not isinstance(row, dict):
                continue
            tool = row.get("tool") or row.get("name") or "—"
            emp = (row.get("employee") or "").strip()
            dt = (row.get("date") or "").strip()
            qty = row.get("total_qty", row.get("qty", row.get("remaining")))
            remaining = row.get("remaining")
            days = row.get("days")
            issues = row.get("issues")
            cat = row.get("category") or ""
            addr = (row.get("address") or "").strip()
            status = (row.get("status") or "").strip()
            idle = row.get("idle_days")
            last_move = (row.get("last_move") or "").strip()
            bit = f"{i}."
            if dt:
                bit += f" {dt}"
            if days is not None:
                bit += f" ({days} дн.)"
            if emp:
                bit += f" {emp} — {tool}"
            else:
                bit += f" {tool}"
            if remaining is not None and row.get("qty") is None and row.get("total_qty") is None:
                bit += f" — остаток {remaining} шт."
            elif qty is not None and remaining is None:
                bit += f" — {qty} шт."
            elif qty is not None and remaining is not None and remaining != qty:
                bit += f" — {qty} шт., на руках {remaining}"
            if issues is not None:
                bit += f", выдач: {issues}"
            if cat:
                bit += f" ({cat})"
            if addr:
                bit += f" [{addr}]"
            if status:
                bit += f" [{status}]"
            if idle is not None and last_move:
                bit += f" · простой {idle} дн. (посл. {last_move})"
            elif idle is not None:
                bit += f" · простой {idle} дн."
            lines.append(bit)
        return head + ":\n" + "\n".join(lines)
    return json.dumps(tool_result, ensure_ascii=False)[:1200]
