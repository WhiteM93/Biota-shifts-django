"""Лента обновлений сайта — читается из site_updates.json в git."""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user
from .site_updates import (
    acknowledge_site_update,
    acks_by_update_id,
    latest_site_update_id,
    load_site_updates,
    set_account_site_updates_seen_id,
)

SITE_UPDATES_SEEN_SESSION_KEY = "site_updates_seen_id"


def _mark_updates_seen(request) -> None:
    latest = latest_site_update_id()
    request.session[SITE_UPDATES_SEEN_SESSION_KEY] = latest
    request.session.modified = True
    u = biota_user(request)
    if u:
        set_account_site_updates_seen_id(u, latest)


def _enrich_rows(rows, username: str) -> list:
    me = (username or "").strip()
    ack_map = acks_by_update_id([r.id for r in rows])
    enriched = []
    for row in rows:
        names = list(ack_map.get(row.id) or [])
        enriched.append(
            {
                "id": row.id,
                "title": row.title,
                "body": row.body,
                "created_at": row.created_at,
                "ack_users": names,
                "ack_count": len(names),
                "i_acked": bool(me and me in names),
            }
        )
    return enriched


@biota_login_required
@require_http_methods(["GET", "HEAD"])
def site_updates_view(request):
    rows = load_site_updates()
    _mark_updates_seen(request)
    return render(
        request,
        "shifts/site_updates.html",
        {"rows": _enrich_rows(rows, biota_user(request) or "")},
    )


@biota_login_required
@require_http_methods(["POST"])
def site_update_ack_api(request, update_id: int):
    who = biota_user(request) or ""
    if not who:
        return JsonResponse({"ok": False, "error": "need login"}, status=401)
    created, names = acknowledge_site_update(update_id, who)
    known = {r.id for r in load_site_updates()}
    if int(update_id) not in known:
        return JsonResponse({"ok": False, "error": "not found"}, status=404)
    return JsonResponse(
        {
            "ok": True,
            "created": bool(created),
            "update_id": int(update_id),
            "ack_users": names,
            "ack_count": len(names),
            "i_acked": True,
        }
    )
