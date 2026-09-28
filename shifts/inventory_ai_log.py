"""Сохранение реплик ИИ для архива (разбор тестов)."""
from __future__ import annotations

from typing import Any

from .models import InventoryAiTurn

_Q_MAX = 4000
_R_MAX = 12000
_ERR_MAX = 400
_SESS_MAX = 40


def _clip(text: Any, limit: int) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def record_ai_turn(
    *,
    username: str,
    kind: str,
    question: str,
    result: dict[str, Any] | None = None,
    session_key: str = "",
    extra: dict[str, Any] | None = None,
) -> InventoryAiTurn | None:
    q = _clip(question, _Q_MAX)
    if not q:
        return None
    data = result if isinstance(result, dict) else {}
    tools = data.get("used_tools") or []
    if not isinstance(tools, list):
        tools = []
    ctx = extra if isinstance(extra, dict) else {}
    return InventoryAiTurn.objects.create(
        username=(username or "").strip()[:120] or "anon",
        kind=kind if kind in {InventoryAiTurn.KIND_INV_CHAT, InventoryAiTurn.KIND_SETUP_AI} else InventoryAiTurn.KIND_INV_CHAT,
        session_key=_clip(session_key, _SESS_MAX),
        question=q,
        reply=_clip(data.get("reply") or "", _R_MAX),
        error=_clip(data.get("error") or "", _ERR_MAX),
        ok=bool(data.get("ok")),
        used_tools=[str(t)[:80] for t in tools[:20]],
        extra=ctx,
    )
