"""HTTP API чата склада (YandexGPT)."""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, inventory_route_nav_access_required
from .gpt_rate_limit import gpt_rate_limit_allow
from .inventory_ai_log import record_ai_turn
from .inventory_chat import ask_inventory_chat, is_notebook_chat_question, normalize_page_context
from .models import InventoryAiTurn
from .yandex_gpt import yandex_gpt_configured


@biota_login_required
@inventory_route_nav_access_required
@require_http_methods(["POST"])
def inventory_chat_api(request):
    username = biota_user(request) or ""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "Ожидается объект JSON."}, status=400)

    question = (payload.get("question") or payload.get("message") or "").strip()
    history = payload.get("history")
    if history is not None and not isinstance(history, list):
        history = None
    session_key = str(payload.get("session_key") or "").strip()[:40]
    page_context = payload.get("page_context") or payload.get("context")

    # Блокнот без GPT — лимит токенов/частоты ИИ не применяем.
    if not is_notebook_chat_question(question):
        ok_rl, retry = gpt_rate_limit_allow(username, scope="inv_chat", cooldown_sec=60)
        if not ok_rl:
            return JsonResponse(
                {
                    "ok": False,
                    "error": f"Не чаще 1 раза в минуту. Подождите ~{retry} сек.",
                    "retry_after": retry,
                },
                status=429,
            )

    result = ask_inventory_chat(
        question,
        history=history,
        page_context=page_context if isinstance(page_context, dict) else None,
        username=username,
    )
    extra = normalize_page_context(page_context if isinstance(page_context, dict) else {})
    try:
        record_ai_turn(
            username=username,
            kind=InventoryAiTurn.KIND_INV_CHAT,
            question=question,
            result=result,
            session_key=session_key,
            extra=extra,
        )
    except Exception:
        pass
    status = 200 if result.get("ok") else 400
    if not result.get("ok") and "не настроен" in (result.get("error") or "").lower():
        status = 503
    body = {
        "ok": bool(result.get("ok")),
        "reply": result.get("reply") or "",
        "error": result.get("error") or "",
        "used_tools": result.get("used_tools") or [],
        "configured": yandex_gpt_configured(),
    }
    return JsonResponse(body, status=status)
