"""Лента обновлений сайта — читается из site_updates.json в git."""
from __future__ import annotations

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user
from .site_updates import (
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


@biota_login_required
@require_http_methods(["GET", "HEAD"])
def site_updates_view(request):
    rows = load_site_updates()
    _mark_updates_seen(request)
    return render(
        request,
        "shifts/site_updates.html",
        {"rows": rows},
    )
