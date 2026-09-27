"""ИИ-анализ наладки (YandexGPT) по строкам инструмента и наличию на складе."""
from __future__ import annotations

from typing import Any

from django.conf import settings

from .setup_stock_match import SetupStockRowResult, match_setup_tools
from .yandex_gpt import YandexGptError, complete, yandex_gpt_configured

SYSTEM_PROMPT = """Технолог CNC + склад. Кратко по фактам (RU):
1) вердикт 2) наличие 3) кого попросить вернуть (если есть «на руках») 4) замечания по таблице 5) советы.
Не выдумывай остатки и фамилии. Без JSON. До ~250 слов."""


def _row_to_text(row: SetupStockRowResult) -> str:
    parts = [
        f"T{row.tool_number or '—'}",
        row.tool_type or "тип?",
    ]
    if row.diameter:
        parts.append(f"⌀{row.diameter}")
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
    return "\n".join(lines)


def build_setup_analysis_prompt(*, product, setup, match_rows: list[SetupStockRowResult]) -> str:
    lines = [
        f"Изделие: {(getattr(product, 'name', None) or '').strip() or f'#{product.pk}'}",
        f"Уст: {(setup.name or '').strip() or f'#{setup.pk}'}",
        f"Загот/мат/размер: {(setup.workpiece or '—').strip()} / {(setup.material or '—').strip()} / {(setup.size or '—').strip()}",
        f"XYZ/G: {(setup.binding_x or '—').strip()}/{(setup.binding_y or '—').strip()}/{(setup.binding_z or '—').strip()}/{(setup.gcode_system or '—').strip()}",
    ]
    notes = (setup.setup_notes or "").strip()
    if notes:
        lines.append("Наладка: " + notes[:900])
    lines.append("Инструмент↔склад:")
    if not match_rows:
        lines.append("(пусто)")
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
    user_blob = build_setup_analysis_prompt(product=product, setup=setup, match_rows=match_rows)
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
