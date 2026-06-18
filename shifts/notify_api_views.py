"""HTTP API: ручной вызов сводки СКУД (для Telegram-бота)."""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from biota_shifts.attendance_summary import SLOT_EVENING, SLOT_MORNING
from biota_shifts.notification_settings import load_notification_settings
from biota_shifts.notify_trigger import (
    chat_id_allowed,
    resolve_slot_from_request,
    trigger_attendance_summary,
    verify_notify_api_bearer,
)


@csrf_exempt
@require_POST
def notify_attendance_trigger(request):
    """
    POST /api/notify/attendance/
    Authorization: Bearer <BIOTA_NOTIFY_RELAY_SECRET>
    Body: {"chat_id": "123", "slot": "morning"|"evening"|"auto", "send": true}
    """
    if not verify_notify_api_bearer(request):
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    chat_id = str(payload.get("chat_id") or "").strip()
    if not chat_id:
        return JsonResponse({"ok": False, "error": "chat_id required"}, status=400)

    settings = load_notification_settings()
    if not chat_id_allowed(chat_id, settings):
        return JsonResponse({"ok": False, "error": "chat not allowed"}, status=403)

    try:
        slot = resolve_slot_from_request(str(payload.get("slot") or "auto"))
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    send = payload.get("send", True)
    if isinstance(send, str):
        send = send.strip().lower() not in ("0", "false", "no")

    try:
        result = trigger_attendance_summary(slot, chat_id=chat_id, settings=settings, send=bool(send))
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    status = 200 if result.get("ok") else 502
    return JsonResponse(result, status=status)
