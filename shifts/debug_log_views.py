"""API журнала действий графика/регламентов — только для admin."""
from __future__ import annotations

import json

from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from biota_shifts.auth import _is_admin
from shifts.auth_utils import biota_login_required, biota_user
from shifts.models import SectionActionLog
from shifts.section_action_log import SECTION_CHOICES, record_from_request


def _admin_only(request):
    u = biota_user(request)
    if not u or not _is_admin(u):
        return False
    return True


@biota_login_required
@require_POST
def debug_log_ingest(request):
    """Запись с клиента: любой вошедший пользователь (просмотр — только admin)."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    section = (payload.get("section") or "").strip()
    if section not in SECTION_CHOICES:
        return JsonResponse({"ok": False, "error": "bad section"}, status=400)
    event_type = (payload.get("event_type") or "client")[:32]
    summary = (payload.get("summary") or "")[:500]
    details = payload.get("details")
    if not isinstance(details, dict):
        details = {}
    record_from_request(request, section, event_type, summary, details)
    return JsonResponse({"ok": True})


@biota_login_required
@require_GET
def debug_log_list(request):
    if not _admin_only(request):
        return HttpResponseForbidden("admin only")
    section = (request.GET.get("section") or "").strip()
    if section not in SECTION_CHOICES:
        return JsonResponse({"ok": False, "error": "bad section"}, status=400)
    try:
        limit = min(200, max(1, int(request.GET.get("limit") or "80")))
    except (TypeError, ValueError):
        limit = 80
    after_id = request.GET.get("after_id")
    qs = SectionActionLog.objects.filter(section=section).order_by("-id")
    if after_id and str(after_id).isdigit():
        qs = qs.filter(id__gt=int(after_id))
    rows = []
    for log in qs[:limit]:
        rows.append(
            {
                "id": log.id,
                "at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "actor": log.actor_username,
                "event_type": log.event_type,
                "summary": log.summary,
                "details": log.details or {},
            }
        )
    return JsonResponse({"ok": True, "rows": rows})
