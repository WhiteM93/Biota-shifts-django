"""Адрес ячейки визуального склада: буква мебели + полка + место (A-01-02).

В БД полка хранится сверху вниз (1 = верх). Для адреса и подписей
нумерация полок — снизу вверх: 01 у нижней полки.
Места — слева направо: 01, 02, …
Буква мебели: латиница A–Z или кириллица А–Я.
"""
from __future__ import annotations

import re

from shifts.models import VisualCabinet, VisualContainer

_ADDR_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]{1,8}-\d{2}-\d{2}$")
_CODE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё]{1,8}$")

LATIN_CODES = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
CYRILLIC_CODES = list("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ")


def pad2(n: int) -> str:
    return f"{max(0, int(n)):02d}"


def shelf_display_num(*, shelves: int, shelf_top1: int) -> str:
    """Отображаемый номер полки снизу вверх (01 = низ)."""
    total = max(1, int(shelves or 1))
    top = max(1, min(int(shelf_top1 or 1), total))
    return pad2(total - top + 1)


def place_display_num(column: int) -> str:
    return pad2(max(1, int(column or 1)))


def normalize_furniture_code(raw: str) -> str:
    text = (raw or "").strip().upper().replace(" ", "")
    if not text or not _CODE_RE.match(text):
        return ""
    return text[:8]


def cabinet_code_of(cab: VisualCabinet | None) -> str:
    if cab is None:
        return "?"
    code = normalize_furniture_code(getattr(cab, "code", "") or "")
    return code or "?"


def next_available_furniture_code(exclude_id: int | None = None) -> str:
    qs = VisualCabinet.objects.all()
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    used = {normalize_furniture_code(c) for c in qs.values_list("code", flat=True)}
    used.discard("")
    for ch in LATIN_CODES + CYRILLIC_CODES:
        if ch not in used:
            return ch
    for a in LATIN_CODES:
        for b in LATIN_CODES:
            cand = f"{a}{b}"
            if cand not in used:
                return cand
    return "X"


def suggested_address(
    cab: VisualCabinet,
    *,
    shelf: int,
    column: int,
    furniture_code: str | None = None,
) -> str:
    code = (furniture_code or cabinet_code_of(cab) or "?").strip().upper() or "?"
    return f"{code}-{shelf_display_num(shelves=cab.shelves, shelf_top1=shelf)}-{place_display_num(column)}"


def normalize_address(raw: str) -> str:
    text = (raw or "").strip().upper().replace(" ", "")
    text = text.replace("_", "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text[:32]


def is_plausible_address(addr: str) -> bool:
    return bool(_ADDR_RE.match((addr or "").strip()))


def resolve_container_address(
    cont: VisualContainer,
    cab: VisualCabinet | None = None,
    *,
    prefer_stored: bool = True,
) -> str:
    """Адрес контейнера для склада и UI.

    Хранимый address уважаем, если это осознанный кастом.
    Если address похож на авто (буква-полка-место этой мебели), но не совпадает
    с текущими полкой/местом — считаем устаревшим и берём геометрию
    (иначе в «Куда добавить» видно 02/01, а сохраняется A-03-02).
    """
    cabinet = cab or getattr(cont, "cabinet", None)
    stored = normalize_address(getattr(cont, "address", "") or "")
    suggested = ""
    if cabinet is not None:
        suggested = normalize_address(
            suggested_address(cabinet, shelf=cont.shelf, column=cont.column)
        )

    if prefer_stored and stored:
        if suggested and stored != suggested and _is_stale_auto_address(stored, cabinet):
            return suggested
        return stored
    return suggested or stored


def _is_stale_auto_address(stored: str, cab: VisualCabinet | None) -> bool:
    """Авто-адрес буквы мебели, который мог остаться после смены полки/логики нумерации."""
    if not is_plausible_address(stored):
        return False
    if cab is None:
        return True
    code = cabinet_code_of(cab)
    if code and code != "?":
        return stored.startswith(f"{code}-")
    return True


def repair_container_address_if_stale(cont: VisualContainer) -> str:
    """Вернуть актуальный адрес; при устаревшем авто-адресе записать в БД."""
    addr = normalize_address(resolve_container_address(cont, prefer_stored=True))
    stored = normalize_address(getattr(cont, "address", "") or "")
    if addr and addr != stored and not getattr(cont, "parent_id", None):
        VisualContainer.objects.filter(pk=cont.pk).update(address=addr)
        cont.address = addr
    return addr


_KIND_LABELS = {
    "bin": "Контейнер",
    "shelf_slot": "На полке",
    "drawer_cell": "Ячейка",
    "organizer": "Органайзер",
    "empty": "Место",
}


def build_location_catalog() -> dict:
    """Мебель / полки / места для выбора адреса на складе.

    В каталог попадают только созданные на визуальном складе места (контейнеры).
    Пустые ячейки сетки без контейнера не предлагаются — сначала создайте место.
    """
    furniture = []
    places: list[dict] = []
    seen_addr: set[str] = set()

    cabinets = VisualCabinet.objects.prefetch_related("containers").order_by(
        "sort_order", "code", "name", "id"
    )
    for cab in cabinets:
        fcode = cabinet_code_of(cab)
        furniture.append(
            {
                "id": cab.id,
                "code": fcode if fcode != "?" else "",
                "name": cab.name,
                "shelves": int(cab.shelves or 1),
                "columns": int(cab.columns or 1),
                "sort_order": int(cab.sort_order or 0),
            }
        )
        tops = [c for c in cab.containers.all() if not getattr(c, "parent_id", None)]
        for cont in tops:
            shelf_lab = shelf_display_num(shelves=cab.shelves, shelf_top1=cont.shelf)
            place_lab = place_display_num(cont.column)
            addr = repair_container_address_if_stale(cont) or normalize_address(
                suggested_address(cab, shelf=cont.shelf, column=cont.column, furniture_code=fcode)
            )
            kind = cont.kind or "bin"
            label = (cont.label or "").strip() or _KIND_LABELS.get(kind, "Место")
            places.append(
                {
                    "address": addr,
                    "furniture_id": cab.id,
                    "furniture_code": fcode,
                    "furniture_name": cab.name,
                    "shelf": int(cont.shelf),
                    "shelf_label": shelf_lab,
                    "column": int(cont.column),
                    "place_label": place_lab,
                    "container_id": cont.id,
                    "label": label,
                    "kind": kind,
                    "kind_label": _KIND_LABELS.get(kind, "Место"),
                }
            )
            seen_addr.add(addr)

    places.sort(
        key=lambda p: (
            p.get("furniture_code") or "",
            p.get("shelf_label") or "",
            p.get("place_label") or "",
            0 if p.get("container_id") else 1,
            p.get("furniture_name") or "",
        )
    )
    unique: list[dict] = []
    used: set[str] = set()
    for p in places:
        addr = p.get("address") or ""
        if not addr or addr in used:
            continue
        used.add(addr)
        unique.append(p)
    return {"furniture": furniture, "places": unique}
