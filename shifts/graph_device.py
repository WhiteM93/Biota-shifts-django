"""Определение телефона и предпочтения вида графика (десктоп / мобильный)."""

from __future__ import annotations

import re

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse

GRAPH_DESKTOP_COOKIE = "graph_prefer_desktop"
_GRAPH_DESKTOP_MAX_AGE = 60 * 60 * 24 * 90  # 90 дней

_MOBILE_UA_RE = re.compile(
    r"android|webos|iphone|ipod|blackberry|iemobile|opera mini|mobile",
    re.IGNORECASE,
)


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def is_mobile_user_agent(request: HttpRequest) -> bool:
    """Телефон / компактное устройство по User-Agent и Client Hints."""
    if _truthy(request.META.get("HTTP_SEC_CH_UA_MOBILE")):
        return True
    ua = request.META.get("HTTP_USER_AGENT", "")
    return bool(_MOBILE_UA_RE.search(ua))


def prefers_desktop_graph(request: HttpRequest) -> bool:
    """Пользователь явно выбрал полную таблицу графика."""
    if _truthy(request.GET.get("desktop")):
        return True
    return request.COOKIES.get(GRAPH_DESKTOP_COOKIE) == "1"


def prefers_mobile_graph(request: HttpRequest) -> bool:
    return _truthy(request.GET.get("prefer_mobile"))


def should_auto_redirect_mobile_graph(request: HttpRequest) -> bool:
    """Авто-переход на /graph/mobile/ для телефонов (если включён BIOTA_PERF_MOBILE_GRAPH)."""
    from django.conf import settings

    if not getattr(settings, "BIOTA_PERF_MOBILE_GRAPH", False):
        return False
    if prefers_desktop_graph(request):
        return False
    return is_mobile_user_agent(request)


def mobile_graph_url(request: HttpRequest) -> str:
    q = request.GET.copy()
    q.pop("desktop", None)
    q.pop("prefer_mobile", None)
    base = reverse("graph_mobile")
    encoded = q.urlencode()
    return f"{base}?{encoded}" if encoded else base


def desktop_graph_url(request: HttpRequest, *, year: int | None = None, month: int | None = None) -> str:
    from django.http import QueryDict

    q = QueryDict(mutable=True)
    q.update(request.GET)
    if year is not None:
        q["year"] = str(year)
    if month is not None:
        q["month"] = str(month)
    q["desktop"] = "1"
    q.pop("prefer_mobile", None)
    return f"{reverse('graph')}?{q.urlencode()}"


def set_desktop_graph_cookie(response: HttpResponse) -> None:
    response.set_cookie(
        GRAPH_DESKTOP_COOKIE,
        "1",
        max_age=_GRAPH_DESKTOP_MAX_AGE,
        samesite="Lax",
        httponly=False,
    )


def clear_desktop_graph_cookie(response: HttpResponse) -> None:
    response.delete_cookie(GRAPH_DESKTOP_COOKIE)


def redirect_to_mobile_graph(request: HttpRequest) -> HttpResponseRedirect:
    resp = HttpResponseRedirect(mobile_graph_url(request))
    if prefers_mobile_graph(request):
        clear_desktop_graph_cookie(resp)
    return resp


def apply_desktop_graph_query_redirect(request: HttpRequest) -> HttpResponseRedirect | None:
    """
    GET /graph/?desktop=1 → тот же URL без параметра + cookie (один раз).
    """
    if not _truthy(request.GET.get("desktop")):
        return None
    q = request.GET.copy()
    q.pop("desktop", None)
    target = reverse("graph")
    encoded = q.urlencode()
    if encoded:
        target = f"{target}?{encoded}"
    resp = HttpResponseRedirect(target)
    set_desktop_graph_cookie(resp)
    return resp
