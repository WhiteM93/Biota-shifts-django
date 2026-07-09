"""Сохранение и интерпретация диагностики медленных загрузок."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

from shifts.graph_device import is_mobile_user_agent
from shifts.models import PageLoadDiagnostic

_KEEP_DEFAULT = 1000


def _int_setting(name: str, default: int) -> int:
    try:
        return max(0, int(getattr(settings, name, default) or default))
    except (TypeError, ValueError):
        return default


def build_diagnosis(
    source: str,
    *,
    ttfb_ms: int | None = None,
    load_ms: int | None = None,
    dom_ms: int | None = None,
    server_ms: int | None = None,
    connection: dict | None = None,
    slow_resources: list | None = None,
) -> str:
    hints: list[str] = []
    conn = connection or {}
    et = (conn.get("effectiveType") or "").strip()

    if source == "server" and server_ms is not None and server_ms >= _int_setting("BIOTA_PERF_DIAG_SERVER_MS", 2000):
        hints.append(f"Сервер отвечал {server_ms} мс — вероятно БД или тяжёлый view")

    if ttfb_ms is not None and ttfb_ms >= _int_setting("BIOTA_PERF_DIAG_TTFB_MS", 2500):
        if server_ms and server_ms >= int(ttfb_ms * 0.55):
            hints.append("Долго до первого байта — в основном сервер")
        else:
            hints.append("Долго до первого байта — сеть или сервер")

    if load_ms is not None and ttfb_ms is not None and (load_ms - ttfb_ms) >= 4000:
        hints.append("После ответа долго грузятся CSS/JS — интернет или большие файлы")

    if dom_ms is not None and dom_ms >= 6000:
        hints.append("DOM долго становится готовым — тяжёлая страница или слабое устройство")

    if et in ("slow-2g", "2g", "3g"):
        hints.append(f"Сеть пользователя: {et}")
    elif et == "4g" and conn.get("downlink") is not None:
        try:
            if float(conn["downlink"]) < 1.5:
                hints.append("Слабый 4G (низкий downlink)")
        except (TypeError, ValueError):
            pass

    if conn.get("saveData"):
        hints.append("Включена экономия трафика в браузере")

    if slow_resources and len(slow_resources) >= 3:
        hints.append(f"Медленных файлов: {len(slow_resources)}")

    if not hints:
        hints.append("Порог превышен — см. детали JSON")
    return " · ".join(hints)[:500]


def trim_old_diagnostics(keep: int | None = None) -> None:
    limit = keep if keep is not None else _int_setting("BIOTA_PERF_DIAG_KEEP", _KEEP_DEFAULT)
    if limit <= 0:
        return
    cutoff = (
        PageLoadDiagnostic.objects.order_by("-id").values_list("id", flat=True)[limit : limit + 1].first()
    )
    if cutoff is not None:
        PageLoadDiagnostic.objects.filter(id__lte=cutoff).delete()


def record_client_diagnostic(request: HttpRequest, payload: dict) -> PageLoadDiagnostic:
    path = (payload.get("path") or request.path or "")[:500]
    ttfb_ms = _safe_int(payload.get("ttfb_ms"))
    load_ms = _safe_int(payload.get("load_ms"))
    dom_ms = _safe_int(payload.get("dom_ms"))
    server_ms = _safe_int(payload.get("server_ms"))
    connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
    slow_resources = payload.get("slow_resources") if isinstance(payload.get("slow_resources"), list) else []
    ua = (payload.get("user_agent") or request.META.get("HTTP_USER_AGENT") or "")[:300]
    is_mobile = bool(payload.get("is_mobile")) or is_mobile_user_agent(request)
    username = (request.session.get("biota_username") or "").strip()[:120]

    diagnosis = build_diagnosis(
        "client",
        ttfb_ms=ttfb_ms,
        load_ms=load_ms,
        dom_ms=dom_ms,
        server_ms=server_ms,
        connection=connection,
        slow_resources=slow_resources,
    )
    row = PageLoadDiagnostic.objects.create(
        source=PageLoadDiagnostic.SOURCE_CLIENT,
        actor_username=username,
        page_path=path,
        server_ms=server_ms,
        ttfb_ms=ttfb_ms,
        dom_ms=dom_ms,
        load_ms=load_ms,
        is_mobile=is_mobile,
        user_agent=ua,
        connection_type=(connection.get("effectiveType") or "")[:16],
        diagnosis=diagnosis,
        details={
            "connection": connection,
            "slow_resources": slow_resources[:15],
            "viewport": payload.get("viewport"),
            "device_memory": payload.get("device_memory"),
            "referrer": (payload.get("referrer") or "")[:300],
        },
    )
    trim_old_diagnostics()
    return row


def record_server_diagnostic(request: HttpRequest, server_ms: int) -> PageLoadDiagnostic | None:
    threshold = _int_setting("BIOTA_PERF_DIAG_SERVER_MS", 2000)
    if server_ms < threshold:
        return None
    username = (request.session.get("biota_username") or "").strip()[:120]
    path = (request.path or "")[:500]
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    diagnosis = build_diagnosis("server", server_ms=server_ms)
    row = PageLoadDiagnostic.objects.create(
        source=PageLoadDiagnostic.SOURCE_SERVER,
        actor_username=username,
        page_path=path,
        server_ms=server_ms,
        is_mobile=is_mobile_user_agent(request),
        user_agent=ua,
        diagnosis=diagnosis,
        details={"method": request.method},
    )
    trim_old_diagnostics()
    return row


def _safe_int(val) -> int | None:
    try:
        if val is None or val == "":
            return None
        return max(0, int(val))
    except (TypeError, ValueError):
        return None
