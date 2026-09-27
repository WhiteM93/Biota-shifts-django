"""HTTP API чата склада (YandexGPT)."""
from __future__ import annotations

import json

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, inventory_route_nav_access_required
from .inventory_chat import ask_inventory_chat
from .yandex_gpt import yandex_gpt_configured


def _rate_limit_ok(username: str) -> bool:
    limit = int(getattr(settings, "YANDEX_GPT_CHAT_RATE_LIMIT", 20) or 20)
    if limit <= 0:
        return True
    key = f"inv_chat_rl:{username or 'anon'}"
    n = cache.get(key)
    if n is None:
        cache.set(key, 1, timeout=600)
        return True
    if int(n) >= limit:
        return False
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, int(n) + 1, timeout=600)
    return True


@biota_login_required
@inventory_route_nav_access_required
@require_http_methods(["POST"])
def inventory_chat_api(request):
    username = biota_user(request) or ""
    if not _rate_limit_ok(username):
        return JsonResponse(
            {"ok": False, "error": "Слишком много запросов. Подождите несколько минут."},
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
