"""API и страница диагностики медленных загрузок."""

from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from biota_shifts.auth import _is_admin
from shifts.auth_utils import biota_login_required, biota_user
from shifts.models import PageLoadDiagnostic
from shifts.perf_diagnostic import record_client_diagnostic


def _diagnostics_enabled() -> bool:
    return bool(getattr(settings, "BIOTA_PERF_DIAGNOSTICS", False))


def _admin_only(request) -> bool:
    u = biota_user(request)
    return bool(u and _is_admin(u))


@biota_login_required
@require_POST
def perf_diagnostic_ingest(request):
    if not _diagnostics_enabled():
        return JsonResponse({"ok": True, "skipped": True})
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "bad payload"}, status=400)

    ttfb_ms = payload.get("ttfb_ms")
    load_ms = payload.get("load_ms")
    try:
        ttfb_i = int(ttfb_ms) if ttfb_ms is not None else 0
        load_i = int(load_ms) if load_ms is not None else 0
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "bad metrics"}, status=400)

    ttfb_limit = int(getattr(settings, "BIOTA_PERF_DIAG_TTFB_MS", 2500) or 2500)
    load_limit = int(getattr(settings, "BIOTA_PERF_DIAG_LOAD_MS", 5000) or 5000)
    if ttfb_i < ttfb_limit and load_i < load_limit:
        return JsonResponse({"ok": True, "skipped": True})

    row = record_client_diagnostic(request, payload)
    return JsonResponse({"ok": True, "id": row.id})


@biota_login_required
@require_GET
def perf_diagnostics_view(request):
    if not _admin_only(request):
        return HttpResponseForbidden("admin only")
    if not _diagnostics_enabled():
        return render(
            request,
            "shifts/perf_diagnostics.html",
            {
                "enabled": False,
                "rows": [],
                "thresholds": {},
            },
        )
    try:
        limit = min(200, max(1, int(request.GET.get("limit") or "80")))
    except (TypeError, ValueError):
        limit = 80
    source = (request.GET.get("source") or "").strip()
    qs = PageLoadDiagnostic.objects.all().order_by("-id")
    if source in (PageLoadDiagnostic.SOURCE_CLIENT, PageLoadDiagnostic.SOURCE_SERVER):
        qs = qs.filter(source=source)
    rows = list(qs[:limit])
    return render(
        request,
        "shifts/perf_diagnostics.html",
        {
            "enabled": True,
            "rows": rows,
            "source_filter": source,
            "thresholds": {
                "ttfb_ms": getattr(settings, "BIOTA_PERF_DIAG_TTFB_MS", 2500),
                "load_ms": getattr(settings, "BIOTA_PERF_DIAG_LOAD_MS", 5000),
                "server_ms": getattr(settings, "BIOTA_PERF_DIAG_SERVER_MS", 2000),
            },
        },
    )
