"""Приём метрик из браузера и страница статистики сайта."""

from __future__ import annotations

import json

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from biota_shifts.auth import _is_admin
from shifts.auth_utils import biota_login_required, biota_user
from shifts.site_stats import build_dashboard, record_client_events, stats_enabled

PERIODS = [(1, "Сегодня"), (7, "7 дней"), (30, "30 дней"), (90, "90 дней")]
_MAX_BODY = 64 * 1024


def _admin_only(request) -> bool:
    u = biota_user(request)
    return bool(u and _is_admin(u))


@biota_login_required
@require_POST
def site_stats_ingest(request):
    if not stats_enabled():
        return JsonResponse({"ok": True, "skipped": True})
    if len(request.body) > _MAX_BODY:
        return JsonResponse({"ok": False, "error": "too large"}, status=413)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return JsonResponse({"ok": False, "error": "bad payload"}, status=400)
    saved = record_client_events(request, events)
    return JsonResponse({"ok": True, "saved": saved})


@biota_login_required
@require_GET
def site_stats_view(request):
    if not _admin_only(request):
        return HttpResponseForbidden("admin only")
    try:
        days = int(request.GET.get("days") or "7")
    except (TypeError, ValueError):
        days = 7
    if days not in {d for d, _ in PERIODS}:
        days = 7
    user = (request.GET.get("user") or "").strip()[:120]
    ctx = {
        "enabled": stats_enabled(),
        "periods": PERIODS,
        "days_sel": days,
        "user_sel": user,
    }
    if ctx["enabled"]:
        ctx.update(build_dashboard(days, user))
    return render(request, "shifts/site_stats.html", ctx)
