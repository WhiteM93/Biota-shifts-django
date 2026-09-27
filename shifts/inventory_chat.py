"""Оркестратор чата склада: YandexGPT + снимок склада + tools."""
from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings

from .inventory_chat_tools import build_warehouse_context, run_tool, tools_schema_for_prompt
from .yandex_gpt import YandexGptError, complete, yandex_gpt_configured

SYSTEM_PROMPT = """Склад Biota. Отвечай кратко по-русски по СНИМКУ (остатки + свежие выдачи).
Не выдумывай. Даты ДД.ММ.ГГГГ. Только чтение.
Tool JSON — только если снимка мало (старые выдачи, узкий поиск, топ за период).
Иначе обычный текст."""

_TOOL_JSON_RE = re.compile(
    r"\{[^{}]*\"tool\"\s*:\s*\"[a-z_]+\"[^{}]*\}",
    re.DOTALL,
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
    try:
        first = complete(messages, max_tokens=max_out)
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
                f"Результат {tool_name}:\n"
                f"{json.dumps(tool_result, ensure_ascii=False)[:3500]}\n"
                "Ответь кратко текстом. Без JSON."
            ),
        }
    )
    try:
        second = complete(messages, max_tokens=max_out)
    except YandexGptError as exc:
        return {"ok": False, "error": str(exc), "used_tools": used_tools}

    call2 = _extract_tool_call(second)
    if call2:
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
        for row in rows[:12]:
            if isinstance(row, dict):
                lines.append(" · ".join(f"{k}: {v}" for k, v in row.items() if v not in ("", None)))
        return "Найдено:\n" + "\n".join(lines)
    return json.dumps(tool_result, ensure_ascii=False)[:1200]
