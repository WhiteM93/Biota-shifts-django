"""ИИ-анализ наладки (YandexGPT) по строкам инструмента и наличию на складе."""
from __future__ import annotations

import re
from typing import Any

from django.conf import settings

from .setup_stock_match import SetupStockRowResult, match_setup_tools
from .yandex_gpt import YandexGptError, complete, yandex_gpt_configured

SYSTEM_PROMPT = """Технолог CNC + склад. Кратко по фактам из блока «Инструмент↔склад» (RU):
1) вердикт 2) наличие по номерам T01… (один префикс T, не TT) 3) кого попросить вернуть по открытым выдачам
4) чем заменить — ТОЛЬКО из строк «замена:» в данных (не предлагай другие ⌀/M сами)
5) замечания 6) советы.
Правила:
- «Фреза с СМП» = корпусной инструмент со сменными пластинами (СМП): торцевая фреза, концевая/насадная головка и т.п. На складе категория «Корпусной инструмент». Не пиши, что тип не сопоставлен.
- Датчик привязки по складу не проверяй и не включай в наличие/вердикт.
- Если список сверки пуст — скажи, что в таблице нет заполненного инструмента для сверки (пустые слоты / только датчик). Не пиши «нет данных склада» и не выдумывай остатки.
- Не выдумывай остатки, фамилии и замены. Без JSON. До ~280 слов."""


def _tools_slot_summary(tools) -> str:
    filled = 0
    probe = 0
    empty = 0
    for t in tools or []:
        tt = (getattr(t, "tool_type", None) or "").strip()
        diam = (getattr(t, "diameter", None) or "").strip()
        note = (getattr(t, "name", None) or "").strip()
        if tt == "Датчик привязки":
            probe += 1
        elif tt or diam or note:
            filled += 1
        else:
            empty += 1
    return (
        f"Сводка слотов: к сверке со складом {filled}, "
        f"датчик привязки (не проверяем) {probe}, пустых {empty}."
    )



def _format_tool_no(raw: str) -> str:
    src = (raw or "").strip()
    if not src:
        return "—"
    m = re.match(r"^(?:T\s*)?(\d{1,4})$", src, re.IGNORECASE)
    if not m:
        return src
    n = int(m.group(1), 10)
    if n < 100:
        return f"T{n:02d}"
    return f"T{n}"


def _format_diam(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if re.match(r"^[⌀ØøΦφ]", s):
        return s
    if re.match(r"^[mM]\d", s) or re.match(r"^\d+\s*[Rr]", s):
        return s
    return "⌀" + s


def _row_to_text(row: SetupStockRowResult) -> str:
    parts = [
        _format_tool_no(row.tool_number or ""),
        row.tool_type or "тип?",
    ]
    diam = _format_diam(row.diameter or "")
    if diam:
        parts.append(diam)
    if row.tap_hole_type:
        parts.append(row.tap_hole_type)
    if row.overhang:
        parts.append(f"вылет {row.overhang}")
    if row.note:
        parts.append(f"зам:{row.note[:80]}")
    head = " · ".join(parts)
    lines = [f"- {head} | {row.status}: {row.status_label}; qtyΣ={row.total_qty}"]
    for c in row.candidates[:3]:
        addr = f" @{c.address}" if c.address else ""
        lines.append(f"  → {c.label[:90]} | {c.qty}{addr}")
    if len(row.candidates) > 3:
        lines.append(f"  → +{len(row.candidates) - 3}")
    holders = getattr(row, "open_holders", None) or []
    if holders:
        lines.append("  на руках (не возвращены):")
        for h in holders[:5]:
            lines.append(
                f"  · {h.employee}: {h.remaining} шт. от {h.movement_date or '?'} — {h.tool_label[:70]}"
            )
        if len(holders) > 5:
            lines.append(f"  · +{len(holders) - 5}")
    alts = getattr(row, "alternatives", None) or []
    if alts:
        lines.append("  замена (только эти позиции со склада):")
        for a in alts[:5]:
            addr = f" @{a.address}" if a.address else ""
            lines.append(
                f"  · {a.label[:80]} | {a.qty}{addr} — {a.reason}"
            )
        if len(alts) > 5:
            lines.append(f"  · +{len(alts) - 5}")
    return "\n".join(lines)


def build_setup_analysis_prompt(
    *,
    product,
    setup,
    match_rows: list[SetupStockRowResult],
    tools=None,
) -> str:
    lines = [
        f"Изделие: {(getattr(product, 'name', None) or '').strip() or f'#{product.pk}'}",
        f"Уст: {(setup.name or '').strip() or f'#{setup.pk}'}",
        f"Загот/мат/размер: {(setup.workpiece or '—').strip()} / {(setup.material or '—').strip()} / {(setup.size or '—').strip()}",
        f"XYZ/G: {(setup.binding_x or '—').strip()}/{(setup.binding_y or '—').strip()}/{(setup.binding_z or '—').strip()}/{(setup.gcode_system or '—').strip()}",
        "Справка: Фреза с СМП → корпусной инструмент (торцевая / головка со сменными пластинами).",
        _tools_slot_summary(tools if tools is not None else getattr(setup, "tools", None)),
    ]
    notes = (setup.setup_notes or "").strip()
    if notes:
        lines.append("Наладка: " + notes[:900])
    lines.append("Инструмент↔склад (без датчика привязки):")
    if not match_rows:
        lines.append(
            "(пусто — нет заполненных строк для сверки; датчик привязки и пустые слоты сюда не входят)"
        )
    else:
        for row in match_rows:
            lines.append(_row_to_text(row))
    return "\n".join(lines)


def analyze_setup(*, product, setup) -> dict[str, Any]:
    if not yandex_gpt_configured():
        return {
            "ok": False,
            "error": "ИИ не настроен: задайте YANDEX_GPT_API_KEY и YANDEX_GPT_FOLDER_ID в .env.secrets.",
        }
    tools = list(setup.tools.all().order_by("sort_order", "id"))
    match_rows = match_setup_tools(tools)
    user_blob = build_setup_analysis_prompt(
        product=product, setup=setup, match_rows=match_rows, tools=tools
    )
    summary = {
        "rows": len(match_rows),
        "ok": sum(1 for r in match_rows if r.status == "ok"),
        "empty": sum(1 for r in match_rows if r.status == "empty"),
        "unmapped": sum(1 for r in match_rows if r.status == "unmapped"),
    }
    model = (getattr(settings, "YANDEX_GPT_MODEL_SETUP", "") or "").strip() or None
    max_tok = int(getattr(settings, "YANDEX_GPT_MAX_TOKENS_SETUP", 900) or 900)
    try:
        reply = complete(
            [
                {"role": "system", "text": SYSTEM_PROMPT},
                {"role": "user", "text": user_blob[:8000]},
            ],
            temperature=0.15,
            max_tokens=max_tok,
            model=model,
        )
    except YandexGptError as exc:
        return {"ok": False, "error": str(exc), "match_summary": summary}
    return {"ok": True, "reply": reply, "match_summary": summary}
