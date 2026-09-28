"""Лента обновлений сайта — читается из site_updates.json в git."""
from __future__ import annotations

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required
from .site_updates import latest_site_update_id, load_site_updates

SITE_UPDATES_SEEN_SESSION_KEY = "site_updates_seen_id"


def _mark_updates_seen(request) -> None:
    request.session[SITE_UPDATES_SEEN_SESSION_KEY] = latest_site_update_id()


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
