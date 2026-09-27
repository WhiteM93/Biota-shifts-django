"""Оркестратор чата склада: YandexGPT + read-only tools."""
from __future__ import annotations

import json
import re
from typing import Any

from .inventory_chat_tools import run_tool, tools_schema_for_prompt
from .yandex_gpt import YandexGptError, complete, yandex_gpt_configured

SYSTEM_PROMPT = """Ты ассистент склада инструмента Biota.
Отвечай кратко по-русски, только по фактам из результатов инструментов.
Не выдумывай остатки и выдачи. Даты в ответах — ДД.ММ.ГГГГ.
Не предлагай менять склад и не выполняй запись — только чтение.
Если данных нет — так и скажи.

Выбор инструмента:
- «какой позиции больше всего», «самый большой остаток», «топ по количеству на складе» → top_stock_tools
- «что чаще выдавали», «топ выдач», расход за период → top_issued_tools
- ФИО сотрудника и что ему выдавали → issues_by_employee
- поиск по названию/бренду → tool_stock_search
Не подставляй произвольный год (например 2023), если пользователь период не назвал.

Чтобы получить данные, верни один JSON-вызов инструмента (без markdown и пояснений).
Когда данных достаточно — ответь обычным текстом пользователю.
"""

_TOOL_JSON_RE = re.compile(
    r"\{[^{}]*\"tool\"\s*:\s*\"[a-z_]+\"[^{}]*\}",
    re.DOTALL,
)


def _extract_tool_call(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # срезать ```json ... ```
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


def _history_messages(history: list[dict[str, str]] | None, *, max_turns: int = 6) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not history:
        return out
    for item in history[-max_turns:]:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip()
        text = (item.get("text") or item.get("content") or "").strip()
        if role in {"user", "assistant"} and text:
            out.append({"role": role, "text": text[:2000]})
    return out


def ask_inventory_chat(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Возвращает {ok, reply, used_tools?, error?}.
    До 2 вызовов модели: выбор tool → ответ по данным.
    """
    q = (question or "").strip()
    if not q:
        return {"ok": False, "error": "Пустой вопрос."}
    if len(q) > 1500:
        return {"ok": False, "error": "Слишком длинный вопрос."}
    if not yandex_gpt_configured():
        return {
            "ok": False,
            "error": "Чат не настроен: задайте YANDEX_GPT_API_KEY и YANDEX_GPT_FOLDER_ID в .env.secrets.",
        }

    used_tools: list[str] = []
    messages: list[dict[str, str]] = [
        {"role": "system", "text": SYSTEM_PROMPT + "\n\n" + tools_schema_for_prompt()},
    ]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "text": q})

    try:
        first = complete(messages)
    except YandexGptError as exc:
        return {"ok": False, "error": str(exc)}

    call = _extract_tool_call(first)
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
                f"Результат инструмента {tool_name}:\n"
                f"{json.dumps(tool_result, ensure_ascii=False)[:6000]}\n\n"
                "Ответь пользователю обычным текстом на русском по этим данным. "
                "Не вызывай инструменты повторно, если данных достаточно."
            ),
        }
    )
    try:
        second = complete(messages)
    except YandexGptError as exc:
        return {"ok": False, "error": str(exc), "used_tools": used_tools}

    # если модель снова вернула tool — один повтор
    call2 = _extract_tool_call(second)
    if call2 and call2["tool"] != tool_name:
        tool_name2 = call2["tool"]
        tool_result2 = run_tool(tool_name2, call2.get("args") or {})
        used_tools.append(tool_name2)
        messages.append({"role": "assistant", "text": json.dumps(call2, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "text": (
                    f"Результат инструмента {tool_name2}:\n"
                    f"{json.dumps(tool_result2, ensure_ascii=False)[:6000]}\n\n"
                    "Ответь пользователю обычным текстом. Больше инструменты не вызывай."
                ),
            }
        )
        try:
            third = complete(messages)
        except YandexGptError as exc:
            return {"ok": False, "error": str(exc), "used_tools": used_tools}
        if _extract_tool_call(third):
            return {
                "ok": True,
                "reply": "Получил данные, но не смог сформулировать ответ. Уточните вопрос.",
                "used_tools": used_tools,
            }
        return {"ok": True, "reply": third, "used_tools": used_tools}

    if call2:
        # повтор того же tool — отдаём текстовый fallback по уже полученным данным
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
    if isinstance(rows, list):
        if not rows:
            return "По запросу ничего не найдено."
        lines = []
        for row in rows[:15]:
            if isinstance(row, dict):
                lines.append(" · ".join(f"{k}: {v}" for k, v in row.items() if v not in ("", None)))
        return "Найдено:\n" + "\n".join(lines)
    return json.dumps(tool_result, ensure_ascii=False)[:1500]
