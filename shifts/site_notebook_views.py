"""Блокнот доработок сайта — только админ: список и отметка «выполнено»."""
from __future__ import annotations

from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import _is_admin

from .auth_utils import biota_login_required, biota_user
from .models import SiteNotebookTask


def _admin_only(request) -> bool:
    u = biota_user(request)
    return bool(u and _is_admin(u))


@biota_login_required
@require_http_methods(["GET", "POST"])
def site_notebook_view(request):
    if not _admin_only(request):
        return HttpResponseForbidden("admin only")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            pk = int(request.POST.get("id") or "0")
        except (TypeError, ValueError):
            pk = 0
        row = get_object_or_404(SiteNotebookTask, pk=pk) if pk else None
        who = biota_user(request) or ""
        if row and action == "done" and row.status != SiteNotebookTask.STATUS_DONE:
            row.status = SiteNotebookTask.STATUS_DONE
            row.done_at = timezone.now()
            row.done_by = who[:120]
            row.save(update_fields=["status", "done_at", "done_by"])
        elif row and action == "reopen" and row.status == SiteNotebookTask.STATUS_DONE:
            row.status = SiteNotebookTask.STATUS_OPEN
            row.done_at = None
            row.done_by = ""
            row.save(update_fields=["status", "done_at", "done_by"])
        status_q = (request.POST.get("status") or request.GET.get("status") or "open").strip()
        url = reverse("site_notebook")
        if status_q in {"open", "done", "all"}:
            url += f"?status={status_q}"
        return HttpResponseRedirect(url)

    status = (request.GET.get("status") or "open").strip()
    qs = SiteNotebookTask.objects.all()
    if status == "open":
        qs = qs.filter(status=SiteNotebookTask.STATUS_OPEN)
    elif status == "done":
        qs = qs.filter(status=SiteNotebookTask.STATUS_DONE)
    else:
        status = "all"
    rows = list(qs[:150])
    open_count = SiteNotebookTask.objects.filter(status=SiteNotebookTask.STATUS_OPEN).count()
    return render(
        request,
        "shifts/site_notebook.html",
        {
            "rows": rows,
            "status_filter": status,
            "open_count": open_count,
        },
    )


@biota_login_required
@require_http_methods(["POST"])
def site_notebook_mark_api(request, pk: int):
    """JSON API: отметить выполнено / открыть снова."""
    if not _admin_only(request):
        return JsonResponse({"ok": False, "error": "admin only"}, status=403)
    row = get_object_or_404(SiteNotebookTask, pk=pk)
    try:
        import json

        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    action = (payload.get("action") or request.POST.get("action") or "done").strip()
    who = biota_user(request) or ""
    if action == "done":
        row.status = SiteNotebookTask.STATUS_DONE
        row.done_at = timezone.now()
        row.done_by = who[:120]
        row.save(update_fields=["status", "done_at", "done_by"])
    elif action == "reopen":
        row.status = SiteNotebookTask.STATUS_OPEN
        row.done_at = None
        row.done_by = ""
        row.save(update_fields=["status", "done_at", "done_by"])
    else:
        return JsonResponse({"ok": False, "error": "unknown action"}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "id": row.id,
            "status": row.status,
            "done_at": row.done_at.isoformat() if row.done_at else "",
            "done_by": row.done_by,
        }
    )
