"""Архив диалогов ИИ — только аккаунт админа."""
from __future__ import annotations

from django.http import Http404, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.http import require_GET

from biota_shifts.auth import _is_admin

from .auth_utils import biota_login_required, biota_user
from .models import InventoryAiTurn


def _admin_only(request) -> bool:
    u = biota_user(request)
    return bool(u and _is_admin(u))


@biota_login_required
@require_GET
def inventory_ai_archive_view(request):
    if not _admin_only(request):
        return HttpResponseForbidden("admin only")
    kind = (request.GET.get("kind") or "").strip()
    user_q = (request.GET.get("user") or "").strip()
    try:
        limit = min(200, max(1, int(request.GET.get("limit") or "80")))
    except (TypeError, ValueError):
        limit = 80
    qs = InventoryAiTurn.objects.all()
    if kind in {InventoryAiTurn.KIND_INV_CHAT, InventoryAiTurn.KIND_SETUP_AI}:
        qs = qs.filter(kind=kind)
    if user_q:
        qs = qs.filter(username__icontains=user_q)
    rows = list(qs[:limit])
    users = list(
        InventoryAiTurn.objects.order_by("username").values_list("username", flat=True).distinct()[:80]
    )
    return render(
        request,
        "shifts/inventory_ai_archive.html",
        {
            "rows": rows,
            "kind_filter": kind,
            "user_filter": user_q,
            "users": users,
            "limit": limit,
        },
    )


@biota_login_required
@require_GET
def inventory_ai_archive_session_view(request, session_key: str):
    if not _admin_only(request):
        return HttpResponseForbidden("admin only")
    key = (session_key or "").strip()[:40]
    if not key:
        return HttpResponseForbidden("bad session")
    rows = list(InventoryAiTurn.objects.filter(session_key=key).order_by("id"))
    if not rows:
        raise Http404("Сессия не найдена.")
    return render(
        request,
        "shifts/inventory_ai_archive_session.html",
        {"rows": rows, "session_key": key},
    )
