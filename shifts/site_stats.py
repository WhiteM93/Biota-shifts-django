"""Статистика использования сайта: открытия страниц, скорость, ошибки сервера и браузера."""

from __future__ import annotations

import math
import time
import uuid
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from shifts.graph_device import is_mobile_user_agent
from shifts.models import SiteErrorLog, SiteRequestLog

_SKIP_PREFIXES = ("/favicon", "/site-stats/ingest/", "/perf-diagnostic/ingest/", "/apple-touch-icon")
_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
_MAX_MS = 600_000
_CLEANUP_EVERY_SEC = 3600
_JS_ERRORS_PER_USER_HOUR = 120

_last_cleanup = 0.0


def stats_enabled() -> bool:
    return bool(getattr(settings, "BIOTA_SITE_STATS", False))


def new_req_id() -> str:
    return uuid.uuid4().hex


def _skip_path(path: str) -> bool:
    for prefix in (getattr(settings, "STATIC_URL", "/static/") or "/static/", getattr(settings, "MEDIA_URL", "/media/") or "/media/"):
        if prefix and path.startswith(prefix):
            return True
    return path.startswith(_SKIP_PREFIXES)


def route_label(request: HttpRequest) -> str:
    rm = getattr(request, "resolver_match", None)
    route = getattr(rm, "route", "") if rm else ""
    label = ("/" + route.lstrip("^")) if route else (request.path or "/")
    panel = (request.GET.get("panel") or "").strip()
    if panel and len(panel) <= 40:
        label = f"{label}?panel={panel}"
    return label[:200]


def _is_page(request: HttpRequest, response: HttpResponse) -> bool:
    if request.method != "GET" or response.status_code != 200:
        return False
    if "text/html" not in (response.get("Content-Type") or "").lower():
        return False
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return False
    dest = (request.headers.get("Sec-Fetch-Dest") or "").lower()
    return dest in ("", "document")


def _session_username(request: HttpRequest) -> str:
    try:
        return (request.session.get("biota_username") or "").strip()[:120]
    except Exception:
        return ""


def record_request(request: HttpRequest, response: HttpResponse, server_ms: int, exc_text: str = "") -> None:
    if _skip_path(request.path or ""):
        return
    status = int(getattr(response, "status_code", 200) or 200)
    username = _session_username(request)
    is_page = _is_page(request, response)
    slow_ms = int(getattr(settings, "BIOTA_SITE_STATS_SLOW_MS", 1000) or 1000)

    if status >= 500:
        keep = True
    elif not username:
        keep = is_page
    else:
        keep = is_page or request.method not in _SAFE_METHODS or status >= 400 or server_ms >= slow_ms
    if not keep:
        return

    route = route_label(request)
    is_mobile = is_mobile_user_agent(request)
    SiteRequestLog.objects.create(
        req_id=getattr(request, "biota_req_id", "") if is_page else "",
        username=username,
        method=(request.method or "GET")[:8],
        path=(request.get_full_path() or "")[:300],
        route=route,
        is_page=is_page,
        status=min(status, 999),
        server_ms=min(max(0, server_ms), _MAX_MS),
        is_mobile=is_mobile,
    )
    if status >= 500 and exc_text:
        lines = [ln for ln in exc_text.strip().splitlines() if ln.strip()]
        SiteErrorLog.objects.create(
            source=SiteErrorLog.SOURCE_SERVER,
            username=username,
            path=(request.get_full_path() or "")[:300],
            route=route,
            status=min(status, 999),
            message=(lines[-1] if lines else "Ошибка сервера")[:500],
            detail=exc_text[-6000:],
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
        )
    maybe_cleanup()


def maybe_cleanup(force: bool = False) -> None:
    global _last_cleanup
    now = time.monotonic()
    if not force and now - _last_cleanup < _CLEANUP_EVERY_SEC:
        return
    _last_cleanup = now
    days = int(getattr(settings, "BIOTA_SITE_STATS_KEEP_DAYS", 90) or 0)
    if days <= 0:
        return
    cutoff = timezone.now() - timedelta(days=days)
    SiteRequestLog.objects.filter(created_at__lt=cutoff).delete()
    SiteErrorLog.objects.filter(created_at__lt=cutoff).delete()


def _clamp_int(val) -> int | None:
    try:
        if val is None or val == "":
            return None
        return min(max(0, int(float(val))), _MAX_MS)
    except (TypeError, ValueError):
        return None


def _apply_page_metrics(username: str, ev: dict) -> bool:
    req_id = str(ev.get("req_id") or "").strip()[:32]
    if not req_id:
        return False
    transfer = _clamp_int(ev.get("transfer_kb"))
    updated = SiteRequestLog.objects.filter(req_id=req_id, username=username, load_ms__isnull=True).update(
        ttfb_ms=_clamp_int(ev.get("ttfb_ms")),
        dom_ms=_clamp_int(ev.get("dom_ms")),
        load_ms=_clamp_int(ev.get("load_ms")),
        transfer_kb=transfer,
        net=str(ev.get("net") or "")[:16],
    )
    return bool(updated)


def _js_error_allowed(username: str) -> bool:
    key = f"site-stats-js-err:{username}"
    try:
        n = cache.get(key, 0)
        if n >= _JS_ERRORS_PER_USER_HOUR:
            return False
        cache.set(key, n + 1, 3600)
    except Exception:
        pass
    return True


def _record_js_error(request: HttpRequest, username: str, ev: dict) -> bool:
    message = str(ev.get("message") or "").strip()
    if not message or not _js_error_allowed(username):
        return False
    source = str(ev.get("source") or "")[:300]
    line = ev.get("line")
    col = ev.get("col")
    where = f"{source}:{line}:{col}" if source else ""
    stack = str(ev.get("stack") or "")[:4000]
    SiteErrorLog.objects.create(
        source=SiteErrorLog.SOURCE_JS,
        username=username,
        path=str(ev.get("path") or "")[:300],
        route=str(ev.get("route") or "")[:200],
        message=message[:500],
        detail="\n".join(x for x in (where, stack) if x)[:6000],
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
    )
    return True


def record_client_events(request: HttpRequest, events: list) -> int:
    username = _session_username(request)
    saved = 0
    for ev in events[:10]:
        if not isinstance(ev, dict):
            continue
        kind = ev.get("kind")
        if kind == "page" and _apply_page_metrics(username, ev):
            saved += 1
        elif kind == "js_error" and _record_js_error(request, username, ev):
            saved += 1
    return saved


# --- Сводка для страницы в кабинете ---


def _pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, math.ceil(p * len(s)) - 1))
    return s[idx]


def fmt_ms(val: int | None) -> str:
    if val is None:
        return "—"
    if val < 1000:
        return f"{val} мс"
    return f"{val / 1000:.1f} с".replace(".", ",")


def period_start(days: int):
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=max(1, days) - 1)


def _speed(server: list[int], loads: list[int]) -> dict:
    return {
        "server_med": fmt_ms(_pct(server, 0.5)),
        "server_p90": fmt_ms(_pct(server, 0.9)),
        "load_med": fmt_ms(_pct(loads, 0.5)),
        "load_p90": fmt_ms(_pct(loads, 0.9)),
        "load_p90_raw": _pct(loads, 0.9) or 0,
    }


def build_dashboard(days: int, user: str = "") -> dict:
    since = period_start(days)
    qs = SiteRequestLog.objects.filter(created_at__gte=since)
    eqs = SiteErrorLog.objects.filter(created_at__gte=since)
    if user:
        qs = qs.filter(username=user)
        eqs = eqs.filter(username=user)
    rows = list(
        qs.values_list(
            "created_at", "username", "route", "is_page", "status", "server_ms", "load_ms", "is_mobile", "net", "method"
        )[:300_000]
    )

    pages = [r for r in rows if r[3]]
    page_server = [r[5] for r in pages]
    page_loads = [r[6] for r in pages if r[6] is not None]
    js_count = eqs.filter(source=SiteErrorLog.SOURCE_JS).count()
    exc_count = eqs.filter(source=SiteErrorLog.SOURCE_SERVER).count()
    summary = {
        "views": len(pages),
        "users": len({r[1] for r in pages if r[1]}),
        "measured": len(page_loads),
        "mobile_pct": round(100 * sum(1 for r in pages if r[7]) / len(pages)) if pages else 0,
        "err5xx": sum(1 for r in rows if r[4] >= 500),
        "err4xx": sum(1 for r in rows if 400 <= r[4] < 500),
        "js_errors": js_count,
        "exceptions": exc_count,
        **_speed(page_server, page_loads),
    }

    by_day: dict = defaultdict(lambda: {"views": 0, "users": set(), "loads": [], "errors": 0})
    for r in rows:
        d = by_day[timezone.localtime(r[0]).date()]
        if r[3]:
            d["views"] += 1
            if r[1]:
                d["users"].add(r[1])
            if r[6] is not None:
                d["loads"].append(r[6])
        if r[4] >= 500:
            d["errors"] += 1
    max_views = max((d["views"] for d in by_day.values()), default=0) or 1
    days_list = []
    for day in sorted(by_day.keys(), reverse=True):
        d = by_day[day]
        days_list.append(
            {
                "date": day,
                "views": d["views"],
                "users": len(d["users"]),
                "load_med": fmt_ms(_pct(d["loads"], 0.5)),
                "load_p90": fmt_ms(_pct(d["loads"], 0.9)),
                "errors": d["errors"],
                "bar_pct": round(100 * d["views"] / max_views),
            }
        )

    by_route: dict = defaultdict(lambda: {"views": 0, "users": set(), "server": [], "loads": [], "errors": 0})
    for r in rows:
        d = by_route[r[2]]
        if r[3]:
            d["views"] += 1
            if r[1]:
                d["users"].add(r[1])
            d["server"].append(r[5])
            if r[6] is not None:
                d["loads"].append(r[6])
        if r[4] >= 400:
            d["errors"] += 1
    routes = [
        {
            "route": k,
            "views": d["views"],
            "users": len(d["users"]),
            "measured": len(d["loads"]),
            "errors": d["errors"],
            **_speed(d["server"], d["loads"]),
        }
        for k, d in by_route.items()
        if d["views"]
    ]
    popular = sorted(routes, key=lambda x: -x["views"])[:30]
    slowest = sorted((x for x in routes if x["measured"] >= 3), key=lambda x: -x["load_p90_raw"])[:12]

    by_user: dict = defaultdict(
        lambda: {"views": 0, "last": None, "loads": [], "mobile": 0, "nets": Counter(), "errors": 0}
    )
    for r in rows:
        if not r[1]:
            continue
        d = by_user[r[1]]
        if d["last"] is None or r[0] > d["last"]:
            d["last"] = r[0]
        if r[4] >= 400:
            d["errors"] += 1
        if not r[3]:
            continue
        d["views"] += 1
        if r[6] is not None:
            d["loads"].append(r[6])
        if r[7]:
            d["mobile"] += 1
        if r[8]:
            d["nets"][r[8]] += 1
    users = sorted(
        (
            {
                "username": k,
                "views": d["views"],
                "last": d["last"],
                "load_med": fmt_ms(_pct(d["loads"], 0.5)),
                "load_p90": fmt_ms(_pct(d["loads"], 0.9)),
                "mobile_pct": round(100 * d["mobile"] / d["views"]) if d["views"] else 0,
                "net": d["nets"].most_common(1)[0][0] if d["nets"] else "",
                "errors": d["errors"],
            }
            for k, d in by_user.items()
        ),
        key=lambda x: -x["views"],
    )

    bad: dict = defaultdict(lambda: {"count": 0, "last": None, "users": set(), "path": ""})
    for r in rows:
        if r[4] < 400:
            continue
        d = bad[(r[2], r[4], r[9])]
        d["count"] += 1
        if r[1]:
            d["users"].add(r[1])
        if d["last"] is None or r[0] > d["last"]:
            d["last"] = r[0]
    bad_responses = sorted(
        (
            {"route": k[0], "status": k[1], "method": k[2], "count": d["count"], "last": d["last"], "users": ", ".join(sorted(d["users"]))[:120]}
            for k, d in bad.items()
        ),
        key=lambda x: (-x["count"], x["route"]),
    )[:40]

    slow_actions_map: dict = defaultdict(list)
    slow_ms = int(getattr(settings, "BIOTA_SITE_STATS_SLOW_MS", 1000) or 1000)
    for r in rows:
        if not r[3] and r[5] >= slow_ms and r[4] < 500:
            slow_actions_map[(r[2], r[9])].append(r[5])
    slow_actions = sorted(
        (
            {"route": k[0], "method": k[1], "count": len(v), "med": fmt_ms(_pct(v, 0.5)), "max": fmt_ms(max(v))}
            for k, v in slow_actions_map.items()
        ),
        key=lambda x: -x["count"],
    )[:20]

    grouped: dict = {}
    for e in eqs.order_by("-id")[:3000]:
        key = (e.source, e.message)
        g = grouped.get(key)
        if g is None:
            grouped[key] = g = {
                "source": e.get_source_display(),
                "message": e.message,
                "count": 0,
                "last": e.created_at,
                "path": e.path,
                "users": set(),
                "detail": e.detail,
            }
        g["count"] += 1
        if e.username:
            g["users"].add(e.username)
    errors = sorted(grouped.values(), key=lambda x: (-x["count"], -x["last"].timestamp()))[:40]
    for g in errors:
        g["users"] = ", ".join(sorted(g["users"]))[:120]

    return {
        "since": since,
        "summary": summary,
        "days": days_list,
        "popular": popular,
        "slowest": slowest,
        "users": users,
        "bad_responses": bad_responses,
        "slow_actions": slow_actions,
        "errors": errors,
        "slow_ms": slow_ms,
    }
