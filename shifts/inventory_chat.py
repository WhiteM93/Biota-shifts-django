"""Оркестратор чата склада: YandexGPT + снимок склада + tools."""
from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings

from .inventory_chat_tools import build_warehouse_context, run_tool, tools_schema_for_prompt
from .yandex_gpt import YandexGptError, complete, yandex_gpt_configured

SYSTEM_PROMPT = """Склад Biota. Отвечай кратко по-русски.
Данные: СНИМОК (остатки + свежие выдачи) и tools. Не выдумывай цифры. Даты ДД.ММ.ГГГГ. Только чтение.

Обязательно вызывай tool JSON (сам, не проси пользователя):
- «чаще используют / популярные / топ выдач / расход» → top_issued_tools (НЕ top_stock_tools);
- «больше всего на складе / топ остатков» → top_stock_tools;
- «кто брал …» → search_issues или issues_by_employee.
На «проводи / сделай / точнее» после такого вопроса — снова вызови нужный tool.
Формат только: {"tool":"имя","args":{...}} без пояснений вокруг, если нужен tool.
Иначе обычный текст по снимку."""

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
_REFUSAL_RE = re.compile(
    r"не\s+могу\s+выполнить|вам\s+нужно|используйте\s+инструмент|запросить\s+этот\s+инструмент|"
    r"в\s+рамках\s+текущего\s+доступа",
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


def forced_tool_call(
    question: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """
    Надёжный маршрутизатор для Lite: «чаще используют» → выдачи, не остатки.
    Follow-up «проводи» смотрит на историю.
    """
    q = (question or "").strip()
    if not q:
        return None
    hist = _history_blob(history)
    blob = f"{q}\n{hist}"
    usage = bool(_USAGE_RE.search(q) or (_FOLLOW_RE.search(q) and _USAGE_RE.search(blob)))
    stock_top = bool(_STOCK_TOP_RE.search(q) or (_FOLLOW_RE.search(q) and _STOCK_TOP_RE.search(blob)))
    if usage and not (stock_top and not _USAGE_RE.search(q)):
        return {"tool": "top_issued_tools", "args": {"limit": 15}}
    if stock_top:
        return {"tool": "top_stock_tools", "args": {"limit": 15}}
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
) -> dict[str, Any] | None:
    forced = forced_tool_call(question, history)
    call = _extract_tool_call(first)
    if forced:
        # Модель часто путает остатки и выдачи — приоритет у маршрутизатора.
        if not call or call.get("tool") in {"top_stock_tools", "top_issued_tools"}:
            return forced
        return call
    if call:
        return call
    if _REFUSAL_RE.search(first or ""):
        # «проводи» без явного ключа в текущей фразе — по истории
        return forced_tool_call(question, history) or {"tool": "top_issued_tools", "args": {"limit": 15}}
    return None


def ask_inventory_chat(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
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

    used_tools: list[str] = []
    try:
        snapshot = build_warehouse_context()
    except Exception as exc:  # noqa: BLE001
        snapshot = f"(снимок склада недоступен: {exc})"

    max_sys = int(getattr(settings, "YANDEX_GPT_CONTEXT_CHARS", 7000) or 7000) + 1200
    system_text = SYSTEM_PROMPT + "\n" + tools_schema_for_prompt() + "\n\n" + snapshot
    messages: list[dict[str, str]] = [
        {"role": "system", "text": system_text[:max_sys]},
    ]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "text": q[:800]})

    max_out = int(getattr(settings, "YANDEX_GPT_MAX_TOKENS", 700) or 700)

    # Для явных «топ выдач / чаще используют» сразу tool — без шанса Lite отмахнуться снимком.
    forced_first = forced_tool_call(q, history)
    first = ""
    if forced_first and forced_first["tool"] == "top_issued_tools" and (
        _USAGE_RE.search(q) or _FOLLOW_RE.search(q)
    ):
        call = forced_first
    else:
        try:
            first = complete(messages, max_tokens=max_out)
        except YandexGptError as exc:
            return {"ok": False, "error": str(exc)}
        call = _pick_tool_call(first, q, history)
        if not call:
            return {"ok": True, "reply": first, "used_tools": used_tools}

    tool_name = call["tool"]
    tool_result = run_tool(tool_name, call.get("args") or {})
    used_tools.append(tool_name)

    messages.append({"role": "assistant", "text": json.dumps(call, ensure_ascii=False)})
    messages.append(
        {
            "role": "user",
            "text": (
                f"Результат {tool_name}:\n"
                f"{json.dumps(tool_result, ensure_ascii=False)[:3500]}\n"
                "Ответь кратко текстом по этому результату (топ позиций). Без JSON. "
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
    if call2 or _REFUSAL_RE.search(second or ""):
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
    metric = (tool_result.get("metric") or "").strip()
    d_from = tool_result.get("from") or ""
    d_to = tool_result.get("to") or ""
    if "остат" in metric.lower():
        head = "Топ по остатку на складе"
    elif d_from or "выдач" in metric.lower():
        head = "Топ по выдачам"
    else:
        head = "Найдено"
    if d_from and d_to:
        head += f" ({d_from} — {d_to})"
    if isinstance(rows, list):
        if not rows:
            return "По запросу ничего не найдено."
        lines = []
        for i, row in enumerate(rows[:15], start=1):
            if not isinstance(row, dict):
                continue
            tool = row.get("tool") or "—"
            qty = row.get("total_qty", row.get("qty"))
            issues = row.get("issues")
            cat = row.get("category") or ""
            bit = f"{i}. {tool}"
            if qty is not None:
                bit += f" — {qty} шт."
            if issues is not None:
                bit += f", выдач: {issues}"
            if cat:
                bit += f" ({cat})"
            lines.append(bit)
        return head + ":\n" + "\n".join(lines)
    return json.dumps(tool_result, ensure_ascii=False)[:1200]
