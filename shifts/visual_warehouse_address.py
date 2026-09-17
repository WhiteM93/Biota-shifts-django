"""Адрес ячейки визуального склада.

Одна секция: CODE-LEVEL-PLACE (A-01-02).
Несколько секций: CODE-SECTION-LEVEL-PLACE (A-1-01-02).

Уровень в БД: index сверху = 1. В адресе — снизу вверх (01 = низ секции).
Места на уровне — сверху вниз по стопке, слева направо.
"""
from __future__ import annotations

import re

from shifts.models import (
    VisualCabinet,
    VisualCabinetLevel,
    VisualCabinetSection,
    VisualContainer,
)

_ADDR_RE_3 = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]{1,8}-\d{2}-\d{2}$")
_ADDR_RE_4 = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]{1,8}-\d{1,2}-\d{2}-\d{2}$")
_CODE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё]{1,8}$")

LATIN_CODES = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
CYRILLIC_CODES = list("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ")


def pad2(n: int) -> str:
    return f"{max(0, int(n)):02d}"


def shelf_display_num(*, shelves: int, shelf_top1: int) -> str:
    """Отображаемый номер полки/уровня снизу вверх (01 = низ)."""
    total = max(1, int(shelves or 1))
    top = max(1, min(int(shelf_top1 or 1), total))
    return pad2(total - top + 1)


def place_display_num(place_num: int) -> str:
    return pad2(max(1, int(place_num or 1)))


def cabinet_section_count(cab: VisualCabinet | None) -> int:
    if cab is None:
        return 1
    n = cab.sections.count()
    return max(1, int(n or 1))


def level_total_in_section(level: VisualCabinetLevel | None, section=None) -> int:
    sec = section or (level.section if level is not None else None)
    if sec is None:
        return 1
    return max(1, sec.levels.count())


def place_sort_key(cont) -> tuple:
    """Сверху вниз (больший stack раньше), слева направо."""
    return (
        -int(getattr(cont, "stack", 1) or 1),
        int(getattr(cont, "column", 1) or 1),
        int(getattr(cont, "id", 0) or 0),
    )


def ordered_shelf_containers(peers: list) -> list:
    tops = [c for c in peers if not getattr(c, "parent_id", None)]
    return sorted(tops, key=place_sort_key)


def _peers_for_container(cont, peers: list | None = None) -> list:
    if peers is not None:
        return list(peers)
    cab = getattr(cont, "cabinet", None)
    if cab is None:
        return []
    level_id = getattr(cont, "level_id", None)
    if level_id:
        return [
            c
            for c in cab.containers.all()
            if not getattr(c, "parent_id", None) and getattr(c, "level_id", None) == level_id
        ]
    return [
        c
        for c in cab.containers.all()
        if not getattr(c, "parent_id", None) and int(c.shelf) == int(cont.shelf)
    ]


def place_index_on_shelf(cont, peers: list | None = None) -> int:
    """Порядковый номер места на уровне (1…): сверху вниз, слева направо."""
    if getattr(cont, "parent_id", None):
        return max(1, int(getattr(cont, "column", 1) or 1))
    peers = _peers_for_container(cont, peers)
    cont_id = getattr(cont, "id", None)
    if cont_id:
        if not any(getattr(c, "id", None) == cont_id for c in peers):
            peers.append(cont)
    elif cont not in peers:
        peers.append(cont)
    for i, c in enumerate(ordered_shelf_containers(peers), start=1):
        if c is cont:
            return i
        if cont_id and getattr(c, "id", None) == cont_id:
            return i
    return max(1, int(getattr(cont, "column", 1) or 1))


def place_labels_by_container_id(containers) -> dict[int, str]:
    by_key: dict[tuple, list] = {}
    for c in containers:
        if getattr(c, "parent_id", None):
            continue
        key = ("L", int(c.level_id)) if getattr(c, "level_id", None) else ("S", int(c.shelf))
        by_key.setdefault(key, []).append(c)
    out: dict[int, str] = {}
    for peers in by_key.values():
        for i, c in enumerate(ordered_shelf_containers(peers), start=1):
            cid = getattr(c, "id", None)
            if cid:
                out[int(cid)] = pad2(i)
    return out


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
    place_num: int | None = None,
    section_index: int | None = None,
    levels_in_section: int | None = None,
) -> str:
    code = (furniture_code or cabinet_code_of(cab) or "?").strip().upper() or "?"
    place = place_num if place_num is not None else column
    total_levels = max(1, int(levels_in_section or cab.shelves or 1))
    level_lab = shelf_display_num(shelves=total_levels, shelf_top1=shelf)
    place_lab = place_display_num(place)
    sec_count = cabinet_section_count(cab)
    if sec_count > 1 and section_index is not None:
        return f"{code}-{int(section_index)}-{level_lab}-{place_lab}"
    return f"{code}-{level_lab}-{place_lab}"


def suggested_address_for_container(
    cont: VisualContainer,
    cab: VisualCabinet | None = None,
    peers: list | None = None,
) -> str:
    cabinet = cab or getattr(cont, "cabinet", None)
    if cabinet is None:
        return ""
    place = place_index_on_shelf(cont, peers=peers)
    level = getattr(cont, "level", None)
    section_index = None
    levels_in_section = None
    shelf_top1 = int(cont.shelf or 1)
    if level is not None:
        shelf_top1 = int(level.index or shelf_top1)
        section = getattr(level, "section", None)
        if section is not None:
            section_index = int(section.index or 1)
            levels_in_section = level_total_in_section(level, section)
    return suggested_address(
        cabinet,
        shelf=shelf_top1,
        column=cont.column,
        place_num=place,
        section_index=section_index,
        levels_in_section=levels_in_section,
    )


def normalize_address(raw: str) -> str:
    text = (raw or "").strip().upper().replace(" ", "")
    text = text.replace("_", "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text[:32]


def is_plausible_address(addr: str) -> bool:
    text = (addr or "").strip()
    return bool(_ADDR_RE_3.match(text) or _ADDR_RE_4.match(text))


def resolve_container_address(
    cont: VisualContainer,
    cab: VisualCabinet | None = None,
    *,
    prefer_stored: bool = True,
    peers: list | None = None,
) -> str:
    cabinet = cab or getattr(cont, "cabinet", None)
    stored = normalize_address(getattr(cont, "address", "") or "")
    suggested = ""
    if cabinet is not None:
        suggested = normalize_address(
            suggested_address_for_container(cont, cab=cabinet, peers=peers)
        )

    if prefer_stored and stored:
        if suggested and stored != suggested and _is_stale_auto_address(stored, cabinet):
            return suggested
        return stored
    return suggested or stored


def _is_stale_auto_address(stored: str, cab: VisualCabinet | None) -> bool:
    if not is_plausible_address(stored):
        return False
    if cab is None:
        return True
    code = cabinet_code_of(cab)
    if code and code != "?":
        return stored.startswith(f"{code}-")
    return True


def repair_container_address_if_stale(cont: VisualContainer) -> str:
    addr = normalize_address(resolve_container_address(cont, prefer_stored=True))
    stored = normalize_address(getattr(cont, "address", "") or "")
    if addr and addr != stored and not getattr(cont, "parent_id", None):
        VisualContainer.objects.filter(pk=cont.pk).update(address=addr)
        cont.address = addr
    return addr


def resync_shelf_place_addresses(cab: VisualCabinet, shelf: int, *, move_tools=None) -> None:
    """Пересчитать авто-адреса контейнеров на уровне (shelf index) первой секции / legacy."""
    peers = list(
        VisualContainer.objects.filter(
            cabinet=cab, shelf=shelf, parent__isnull=True
        ).select_related("level", "level__section")
    )
    _resync_peers(cab, peers, move_tools=move_tools)


def resync_level_place_addresses(
    cab: VisualCabinet, level: VisualCabinetLevel, *, move_tools=None
) -> None:
    peers = list(
        VisualContainer.objects.filter(
            cabinet=cab, level=level, parent__isnull=True
        ).select_related("level", "level__section")
    )
    _resync_peers(cab, peers, move_tools=move_tools)


def _resync_peers(cab: VisualCabinet, peers: list, *, move_tools=None) -> None:
    for i, cont in enumerate(ordered_shelf_containers(peers), start=1):
        new_addr = normalize_address(
            suggested_address_for_container(cont, cab=cab, peers=peers)
        )
        # place_num already in suggested; recompute with explicit place for safety
        level = getattr(cont, "level", None)
        section_index = None
        levels_in_section = None
        shelf_top1 = int(cont.shelf or 1)
        if level is not None:
            shelf_top1 = int(level.index or shelf_top1)
            section = getattr(level, "section", None)
            if section is not None:
                section_index = int(section.index or 1)
                levels_in_section = level_total_in_section(level, section)
        new_addr = normalize_address(
            suggested_address(
                cab,
                shelf=shelf_top1,
                column=cont.column,
                place_num=i,
                section_index=section_index,
                levels_in_section=levels_in_section,
            )
        )
        old = normalize_address(cont.address or "")
        if not new_addr or new_addr == old:
            continue
        if old and not _is_stale_auto_address(old, cab):
            continue
        if old and old != new_addr and callable(move_tools):
            move_tools(old, new_addr)
        VisualContainer.objects.filter(pk=cont.pk).update(address=new_addr)
        cont.address = new_addr


def ensure_cabinet_layout(
    cab: VisualCabinet,
    *,
    sections: int | None = None,
    shelves_per_section: int | None = None,
    columns: int | None = None,
    level_kind: str = VisualCabinetLevel.KIND_SHELF,
) -> list[VisualCabinetSection]:
    """Создать секции/уровни если их нет; синхронизировать cab.shelves/columns."""
    cols = max(1, int(columns if columns is not None else cab.columns or 1))
    shelf_n = max(
        1, int(shelves_per_section if shelves_per_section is not None else cab.shelves or 1)
    )
    sec_n = max(1, int(sections if sections is not None else 1))
    existing = list(cab.sections.order_by("index"))
    if not existing:
        for si in range(1, sec_n + 1):
            section = VisualCabinetSection.objects.create(
                cabinet=cab, index=si, name="", sort_order=si - 1
            )
            for li in range(1, shelf_n + 1):
                VisualCabinetLevel.objects.create(
                    section=section,
                    index=li,
                    kind=level_kind,
                    columns=cols,
                )
        existing = list(cab.sections.order_by("index"))
    sync_cabinet_grid_from_layout(cab)
    return list(cab.sections.order_by("index"))


def sync_cabinet_grid_from_layout(cab: VisualCabinet) -> None:
    """Обновить legacy shelves/columns по раскладке секций."""
    sections = list(cab.sections.prefetch_related("levels").order_by("index"))
    if not sections:
        return
    max_levels = 1
    max_cols = 1
    for sec in sections:
        levels = list(sec.levels.all())
        max_levels = max(max_levels, len(levels) or 1)
        for lvl in levels:
            max_cols = max(max_cols, int(lvl.columns or 1))
    if cab.shelves == max_levels and cab.columns == max_cols:
        return
    cab.shelves = max_levels
    cab.columns = max_cols
    cab.save(update_fields=["shelves", "columns", "updated_at"])


def apply_cabinet_sections_layout(
    cab: VisualCabinet,
    sections_payload: list,
    *,
    default_columns: int | None = None,
) -> tuple[list[VisualCabinetSection], str | None]:
    """
    Применить раскладку секций/уровней из API.
    sections_payload: [{"id"?, "name"?, "levels": [{"id"?, "kind", "columns"}]}]
    Возвращает (sections, error_message|None).
    """
    if not isinstance(sections_payload, list) or not sections_payload:
        return list(cab.sections.order_by("index")), "Укажите хотя бы одну секцию"

    default_cols = max(1, int(default_columns if default_columns is not None else cab.columns or 3))
    existing_sections = {s.id: s for s in cab.sections.prefetch_related("levels").all()}
    keep_section_ids: set[int] = set()
    keep_level_ids: set[int] = set()
    created_sections: list[VisualCabinetSection] = []

    for si, sec_raw in enumerate(sections_payload, start=1):
        if not isinstance(sec_raw, dict):
            return [], "Некорректная секция"
        levels_raw = sec_raw.get("levels")
        if not isinstance(levels_raw, list) or not levels_raw:
            return [], f"В секции {si} нужен хотя бы один уровень"
        sec_id = sec_raw.get("id")
        section = None
        if sec_id:
            try:
                section = existing_sections.get(int(sec_id))
            except (TypeError, ValueError):
                section = None
            if section is None:
                return [], f"Секция id={sec_id} не найдена"
        if section is None:
            section = VisualCabinetSection.objects.create(
                cabinet=cab,
                index=si,
                name=str(sec_raw.get("name") or "").strip()[:80],
                sort_order=si - 1,
            )
        else:
            section.index = si
            section.name = str(sec_raw.get("name") or "").strip()[:80]
            section.sort_order = si - 1
            section.save(update_fields=["index", "name", "sort_order"])
        keep_section_ids.add(section.id)
        created_sections.append(section)

        existing_levels = {lv.id: lv for lv in section.levels.all()}
        for li, lvl_raw in enumerate(levels_raw, start=1):
            if not isinstance(lvl_raw, dict):
                return [], "Некорректный уровень"
            kind = str(lvl_raw.get("kind") or VisualCabinetLevel.KIND_SHELF).strip().lower()
            if kind not in (VisualCabinetLevel.KIND_SHELF, VisualCabinetLevel.KIND_DRAWER):
                kind = VisualCabinetLevel.KIND_SHELF
            try:
                cols = int(lvl_raw.get("columns", default_cols))
            except (TypeError, ValueError):
                cols = default_cols
            cols = max(1, min(12, cols))
            lvl_id = lvl_raw.get("id")
            level = None
            if lvl_id:
                try:
                    level = existing_levels.get(int(lvl_id))
                except (TypeError, ValueError):
                    level = None
                if level is None:
                    return [], f"Уровень id={lvl_id} не найден"
            if level is None:
                level = VisualCabinetLevel.objects.create(
                    section=section,
                    index=li,
                    kind=kind,
                    columns=cols,
                )
            else:
                # нельзя сузить так, что контейнеры не влезут
                for cont in level.containers.filter(parent__isnull=True):
                    cs = max(1, int(cont.col_span or 1))
                    if cont.column + cs - 1 > cols:
                        return [], (
                            f"Уровень {li} секции {si}: нельзя уменьшить места — "
                            "контейнеры не помещаются"
                        )
                level.index = li
                level.kind = kind
                level.columns = cols
                level.save(update_fields=["index", "kind", "columns"])
            keep_level_ids.add(level.id)
            # зеркалим shelf у контейнеров уровня
            VisualContainer.objects.filter(level=level).update(shelf=li)

    # удалить лишние уровни/секции без контейнеров
    for sec in cab.sections.all():
        for lvl in sec.levels.all():
            if lvl.id in keep_level_ids:
                continue
            if lvl.containers.filter(parent__isnull=True).exists():
                return [], "Нельзя удалить уровень: на нём есть контейнеры"
            lvl.delete()
        if sec.id in keep_section_ids:
            continue
        if VisualContainer.objects.filter(level__section=sec, parent__isnull=True).exists():
            return [], "Нельзя удалить секцию: в ней есть контейнеры"
        sec.delete()

    sync_cabinet_grid_from_layout(cab)
    return list(cab.sections.order_by("index").prefetch_related("levels")), None


_KIND_LABELS = {
    "bin": "Контейнер",
    "shelf_slot": "На полке",
    "drawer_cell": "Ячейка",
    "organizer": "Органайзер",
    "empty": "Место",
}


def build_location_catalog() -> dict:
    """Мебель / полки / места для выбора адреса на складе."""
    furniture = []
    places: list[dict] = []

    cabinets = VisualCabinet.objects.prefetch_related(
        "containers",
        "sections",
        "sections__levels",
        "containers__level",
        "containers__level__section",
    ).order_by("sort_order", "code", "name", "id")
    for cab in cabinets:
        fcode = cabinet_code_of(cab)
        furniture.append(
            {
                "id": cab.id,
                "code": fcode if fcode != "?" else "",
                "name": cab.name,
                "shelves": int(cab.shelves or 1),
                "columns": int(cab.columns or 1),
                "sections_count": cabinet_section_count(cab),
                "sort_order": int(cab.sort_order or 0),
            }
        )
        tops = [c for c in cab.containers.all() if not getattr(c, "parent_id", None)]
        place_labels = place_labels_by_container_id(tops)
        for cont in tops:
            level = getattr(cont, "level", None)
            section = getattr(level, "section", None) if level else None
            levels_total = (
                level_total_in_section(level, section)
                if level
                else max(1, int(cab.shelves or 1))
            )
            shelf_top1 = int(level.index if level else cont.shelf)
            shelf_lab = shelf_display_num(shelves=levels_total, shelf_top1=shelf_top1)
            place_lab = place_labels.get(cont.id) or place_display_num(
                place_index_on_shelf(cont, peers=tops)
            )
            addr = repair_container_address_if_stale(cont) or normalize_address(
                suggested_address_for_container(cont, cab=cab, peers=tops)
            )
            kind = cont.kind or "bin"
            label = (cont.label or "").strip() or _KIND_LABELS.get(kind, "Место")
            sec_idx = int(section.index) if section is not None else 1
            places.append(
                {
                    "address": addr,
                    "furniture_id": cab.id,
                    "furniture_code": fcode,
                    "furniture_name": cab.name,
                    "section_index": sec_idx,
                    "section_label": str(sec_idx),
                    "shelf": shelf_top1,
                    "shelf_label": shelf_lab,
                    "level_id": level.id if level else None,
                    "level_kind": level.kind if level else "shelf",
                    "column": int(cont.column),
                    "place_label": place_lab,
                    "container_id": cont.id,
                    "label": label,
                    "kind": kind,
                    "kind_label": _KIND_LABELS.get(kind, "Место"),
                }
            )

    places.sort(
        key=lambda p: (
            p.get("furniture_code") or "",
            p.get("section_index") or 0,
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


def address_container_titles() -> dict[str, str]:
    """Адрес → название контейнера (для title в таблице склада)."""
    out: dict[str, str] = {}
    for p in build_location_catalog().get("places") or []:
        addr = normalize_address(p.get("address") or "")
        if not addr:
            continue
        label = (p.get("label") or "").strip() or (p.get("kind_label") or "").strip()
        if label:
            out[addr] = label
    return out
