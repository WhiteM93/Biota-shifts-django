"""Настройки и выборка блока «Мало на складе» на главной."""
from __future__ import annotations

from dataclasses import dataclass

from django.http import QueryDict

from shifts.models import ToolItem, UserHomeLowStockPrefs

TOOL_CATEGORY_ALL = "all"

TOOL_CATEGORY_CHOICES: list[tuple[str, str]] = [
    (TOOL_CATEGORY_ALL, "Все типы"),
    *ToolItem._meta.get_field("category").choices,
]
_VALID_CATEGORIES = frozenset(c for c, _ in TOOL_CATEGORY_CHOICES if c)
_DEFAULT_MAX_QTY = 10
_MIN_MAX_QTY = 1
_MAX_MAX_QTY = 9999
_LIST_LIMIT = 100


@dataclass(frozen=True)
class HomeLowStockPrefs:
    category: str
    max_qty: int


def _category_label(category: str) -> str:
    for key, label in TOOL_CATEGORY_CHOICES:
        if key == category:
            return str(label)
    return "Все типы"


def _clamp_max_qty(raw) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        v = _DEFAULT_MAX_QTY
    return max(_MIN_MAX_QTY, min(_MAX_MAX_QTY, v))


def _normalize_category(raw: str | None) -> str:
    c = (raw or "").strip()
    if c in ("", TOOL_CATEGORY_ALL):
        return ""
    if c in _VALID_CATEGORIES:
        return c
    return ""


def category_form_value(category: str) -> str:
    """Значение для select: пустая категория → «all» (пустой value в GET часто теряется)."""
    return category if category else TOOL_CATEGORY_ALL


def load_home_low_stock_prefs(username: str | None) -> HomeLowStockPrefs:
    if not username:
        return HomeLowStockPrefs(category="", max_qty=_DEFAULT_MAX_QTY)
    try:
        row = UserHomeLowStockPrefs.objects.only("category", "max_qty").get(username=username)
        return HomeLowStockPrefs(
            category=_normalize_category(row.category),
            max_qty=_clamp_max_qty(row.max_qty),
        )
    except UserHomeLowStockPrefs.DoesNotExist:
        return HomeLowStockPrefs(category="", max_qty=_DEFAULT_MAX_QTY)


def resolve_home_low_stock_prefs(username: str | None, query: QueryDict) -> HomeLowStockPrefs:
    saved = load_home_low_stock_prefs(username)
    if "stock_apply" in query:
        return HomeLowStockPrefs(
            category=_normalize_category(query.get("stock_category", TOOL_CATEGORY_ALL)),
            max_qty=_clamp_max_qty(query.get("stock_max_qty", saved.max_qty)),
        )
    prefs = saved
    if "stock_category" in query:
        prefs = HomeLowStockPrefs(
            category=_normalize_category(query.get("stock_category")),
            max_qty=prefs.max_qty,
        )
    if "stock_max_qty" in query:
        prefs = HomeLowStockPrefs(category=prefs.category, max_qty=_clamp_max_qty(query.get("stock_max_qty")))
    return prefs


def save_home_low_stock_prefs(username: str | None, prefs: HomeLowStockPrefs) -> None:
    if not username:
        return
    UserHomeLowStockPrefs.objects.update_or_create(
        username=username,
        defaults={
            "category": prefs.category,
            "max_qty": prefs.max_qty,
        },
    )


def should_persist_stock_prefs(query: QueryDict) -> bool:
    return "stock_apply" in query or "stock_category" in query or "stock_max_qty" in query


def low_stock_critical_threshold(max_qty: int) -> int:
    """Порог для «критичного» остатка (красный бейдж)."""
    return max(1, (max_qty + 2) // 3)


def fetch_low_stock_items(prefs: HomeLowStockPrefs) -> list[ToolItem]:
    qs = (
        ToolItem.objects.filter(is_deleted=False, quantity__lt=prefs.max_qty)
        .select_related(
            "end_mill_spec",
            "tap_spec",
            "center_drill_spec",
            "countersink_spec",
            "drill_spec",
        )
        .order_by("quantity", "category", "name")
    )
    if prefs.category:
        qs = qs.filter(category=prefs.category)
    return list(qs[:_LIST_LIMIT])


def apply_home_low_stock_context(ctx: dict, *, username: str | None, query: QueryDict, can_inventory: bool) -> None:
    ctx["low_stock_category_choices"] = TOOL_CATEGORY_CHOICES
    if not can_inventory:
        ctx["low_stock_items"] = []
        ctx["low_stock_prefs"] = HomeLowStockPrefs(category="", max_qty=_DEFAULT_MAX_QTY)
        ctx["low_stock_category_value"] = TOOL_CATEGORY_ALL
        ctx["low_stock_category_label"] = _category_label("")
        ctx["low_stock_critical_lt"] = low_stock_critical_threshold(_DEFAULT_MAX_QTY)
        return

    prefs = resolve_home_low_stock_prefs(username, query)
    if should_persist_stock_prefs(query):
        save_home_low_stock_prefs(username, prefs)

    ctx["low_stock_prefs"] = prefs
    ctx["low_stock_category_value"] = category_form_value(prefs.category)
    ctx["low_stock_items"] = fetch_low_stock_items(prefs)
    ctx["low_stock_category_label"] = _category_label(prefs.category)
    ctx["low_stock_critical_lt"] = low_stock_critical_threshold(prefs.max_qty)
