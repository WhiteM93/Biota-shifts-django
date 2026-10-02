"""Блокнот доработок сайта — только админ: список, выполнено / отказ / снова открыть."""
from __future__ import annotations

from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import _is_admin

from .auth_utils import biota_login_required, biota_user
from .models import SiteNotebookTask

_STATUS_FILTERS = frozenset({"open", "done", "rejected", "all"})


def _admin_only(request) -> bool:
    u = biota_user(request)
    return bool(u and _is_admin(u))


def _redirect_notebook(status_q: str) -> HttpResponseRedirect:
    url = reverse("site_notebook")
    if status_q in _STATUS_FILTERS:
        url += f"?status={status_q}"
    return HttpResponseRedirect(url)


def _mark_done(row: SiteNotebookTask, who: str) -> None:
    row.status = SiteNotebookTask.STATUS_DONE
    row.done_at = timezone.now()
    row.done_by = who[:120]
    row.reject_reason = ""
    row.save(update_fields=["status", "done_at", "done_by", "reject_reason"])


def _mark_rejected(row: SiteNotebookTask, who: str, reason: str) -> None:
    row.status = SiteNotebookTask.STATUS_REJECTED
    row.done_at = timezone.now()
    row.done_by = who[:120]
    row.reject_reason = reason[:2000]
    row.save(update_fields=["status", "done_at", "done_by", "reject_reason"])


def _mark_reopen(row: SiteNotebookTask) -> None:
    row.status = SiteNotebookTask.STATUS_OPEN
    row.done_at = None
    row.done_by = ""
    row.reject_reason = ""
    row.save(update_fields=["status", "done_at", "done_by", "reject_reason"])


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
        if row and action == "done" and row.status == SiteNotebookTask.STATUS_OPEN:
            _mark_done(row, who)
        elif row and action == "reject" and row.status == SiteNotebookTask.STATUS_OPEN:
            reason = (request.POST.get("reject_reason") or "").strip()
            if reason:
                _mark_rejected(row, who, reason)
        elif row and action == "reopen" and row.status in {
            SiteNotebookTask.STATUS_DONE,
            SiteNotebookTask.STATUS_REJECTED,
        }:
            _mark_reopen(row)
        status_q = (request.POST.get("status") or request.GET.get("status") or "open").strip()
        return _redirect_notebook(status_q)

    status = (request.GET.get("status") or "open").strip()
    qs = SiteNotebookTask.objects.all()
    if status == "open":
        qs = qs.filter(status=SiteNotebookTask.STATUS_OPEN)
    elif status == "done":
        qs = qs.filter(status=SiteNotebookTask.STATUS_DONE)
    elif status == "rejected":
        qs = qs.filter(status=SiteNotebookTask.STATUS_REJECTED)
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
    """JSON API: отметить выполнено / отказать / открыть снова."""
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
        if row.status != SiteNotebookTask.STATUS_OPEN:
            return JsonResponse({"ok": False, "error": "not open"}, status=400)
        _mark_done(row, who)
    elif action == "reject":
        if row.status != SiteNotebookTask.STATUS_OPEN:
            return JsonResponse({"ok": False, "error": "not open"}, status=400)
        reason = (payload.get("reject_reason") or request.POST.get("reject_reason") or "").strip()
        if not reason:
            return JsonResponse({"ok": False, "error": "reject_reason required"}, status=400)
        _mark_rejected(row, who, reason)
    elif action == "reopen":
        if row.status not in {SiteNotebookTask.STATUS_DONE, SiteNotebookTask.STATUS_REJECTED}:
            return JsonResponse({"ok": False, "error": "not closed"}, status=400)
        _mark_reopen(row)
    else:
        return JsonResponse({"ok": False, "error": "unknown action"}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "id": row.id,
            "status": row.status,
            "done_at": row.done_at.isoformat() if row.done_at else "",
            "done_by": row.done_by,
            "reject_reason": row.reject_reason,
        }
    )
