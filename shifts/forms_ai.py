"""Сверстать печатный бланк из сырого текста (YandexGPT)."""
from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings

from .yandex_gpt import YandexGptError, complete, yandex_gpt_configured

MAX_SOURCE_CHARS = 12000
MAX_INSTRUCTION_CHARS = 500

SYSTEM_PROMPT = """Ты верстальщик печатных бланков A4 для цеха.
По сырому тексту (часто из другого ИИ) собери аккуратный бланк.
Верни ТОЛЬКО JSON без markdown:
{"elements":[...]}

Типы элементов (поле type):
- heading: {"type":"heading","text":"...","align":"center|left|right","font_size":16}
- text: {"type":"text","text":"..."}  — абзац, не стена текста
- checkbox: {"type":"checkbox","label":"...","checked":false}
- list: {"type":"list","ordered":false,"items":["..."]}
- item: {"type":"item","num":"1.","label":"...","value":"","placeholder":""}
- date: {"type":"date","label":"Дата:","value":"","placeholder":"дд.мм.гггг"}
- fio: {"type":"fio","label":"ФИО:","value":"","placeholder":"Фамилия Имя Отчество"}
- line: {"type":"line"}
- table: {"type":"table","rows":2,"cols":2,"cells":[[{"text":"A"},{"text":"B"}]]}

Правила:
- Сохрани смысл и формулировки, не выдумывай цифры, ФИО, даты.
- Заголовок документа — heading по центру.
- Чек-листы и «подписи к галочке» — checkbox, не пихай всё в один checkbox.
- Нумерованные шаги — list ordered true или несколько item.
- Поля подписи/даты — fio и date.
- Таблицу только если в тексте реально таблица/графы.
- Без картинок. Не больше 60 элементов. page не указывай.
- Пустые декоративные элементы не добавляй."""


def extract_json_object(text: str) -> dict[str, Any] | None:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def layout_form_from_text(source: str, instruction: str = "") -> dict[str, Any]:
    if not yandex_gpt_configured():
        return {"ok": False, "error": "ИИ не настроен."}
    src = (source or "").strip()
    if not src:
        return {"ok": False, "error": "Вставьте текст."}
    if len(src) > MAX_SOURCE_CHARS:
        src = src[: MAX_SOURCE_CHARS - 1] + "…"
    hint = " ".join((instruction or "").split()).strip()[:MAX_INSTRUCTION_CHARS]
    user = "Текст бланка:\n" + src
    if hint:
        user += "\n\nКак оформить:\n" + hint
    else:
        user += "\n\nКак оформить: сделай понятный печатный бланк (заголовок, абзацы, галочки, поля)."
    try:
        raw = complete(
            [
                {"role": "system", "text": SYSTEM_PROMPT},
                {"role": "user", "text": user},
            ],
            temperature=0.2,
            max_tokens=int(getattr(settings, "YANDEX_GPT_MAX_TOKENS_SETUP", 900) or 900) + 1600,
            timeout=float(getattr(settings, "YANDEX_GPT_TIMEOUT", 45) or 45) + 20,
        )
    except YandexGptError as exc:
        return {"ok": False, "error": str(exc)}
    data = extract_json_object(raw)
    if not data:
        return {"ok": False, "error": "ИИ вернул неразборчивый ответ. Попробуйте ещё раз."}
    elements = data.get("elements")
    if not isinstance(elements, list) or not elements:
        return {"ok": False, "error": "Не получилось собрать элементы бланка."}
    return {"ok": True, "elements": elements, "raw": raw}
