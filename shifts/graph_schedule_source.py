"""Источник графика на странице /graph/: локальный Excel или Google Sheets."""
from __future__ import annotations

from biota_shifts.schedule_google import (
    SCHEDULE_SOURCE_GOOGLE,
    SCHEDULE_SOURCE_LOCAL,
    google_schedule_configured,
    parse_schedule_source,
)

SESSION_KEY = "graph_schedule_source"


def get_graph_schedule_source(request) -> str:
    """
    Источник из GET/POST schedule_source (сохраняется в сессию) или из сессии.
    Google недоступен без конфигурации — всегда local.
    """
    raw = request.GET.get("schedule_source") or request.POST.get("schedule_source")
    if raw is not None and str(raw).strip() != "":
        src = parse_schedule_source(raw)
        if src == SCHEDULE_SOURCE_GOOGLE and not google_schedule_configured():
            src = SCHEDULE_SOURCE_LOCAL
        request.session[SESSION_KEY] = src
        return src

    cached = request.session.get(SESSION_KEY)
    if cached == SCHEDULE_SOURCE_GOOGLE and google_schedule_configured():
        return SCHEDULE_SOURCE_GOOGLE
    return SCHEDULE_SOURCE_LOCAL


def schedule_source_query_param(source: str) -> str:
    if source == SCHEDULE_SOURCE_GOOGLE:
        return f"schedule_source={SCHEDULE_SOURCE_GOOGLE}"
    return ""


def append_schedule_source(url: str, source: str) -> str:
    qp = schedule_source_query_param(source)
    if not qp:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{qp}"


def get_skud_schedule_source() -> str:
    """Google-график для модулей без переключателя (СКУД, Часы), если интеграция настроена."""
    if google_schedule_configured():
        return SCHEDULE_SOURCE_GOOGLE
    return SCHEDULE_SOURCE_LOCAL


def load_schedule_table_resolved(
    employees_df,
    year: int,
    month: int,
    *,
    source: str,
):
    """Загрузка графика с fallback на локальный Excel при ошибке Google."""
    from biota_shifts import schedule as biota_schedule
    from biota_shifts.schedule_google import GoogleScheduleError

    try:
        return biota_schedule.load_schedule_table(
            employees_df, year, month, source=source
        )
    except GoogleScheduleError:
        return biota_schedule.load_schedule_table(
            employees_df, year, month, source=SCHEDULE_SOURCE_LOCAL
        )
