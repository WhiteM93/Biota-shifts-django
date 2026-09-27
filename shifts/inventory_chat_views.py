"""HTTP API чата склада (YandexGPT)."""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, inventory_route_nav_access_required
from .gpt_rate_limit import gpt_rate_limit_allow
from .inventory_chat import ask_inventory_chat
from .yandex_gpt import yandex_gpt_configured


@biota_login_required
@inventory_route_nav_access_required
@require_http_methods(["POST"])
def inventory_chat_api(request):
    username = biota_user(request) or ""
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

    result = ask_inventory_chat(question, history=history)
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
