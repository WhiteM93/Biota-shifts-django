"""Заполнить grafik_2026_04.xlsx из «Апрель 2026 .html» (Google Sheets) по ФИО из шаблона grafik."""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
from bs4 import BeautifulSoup

from biota_shifts.schedule import _schedule_day_cols, sanitize_schedule_cell

HTML_PATH = Path(r"c:\Users\Макс\Downloads\Апрель 2026 .html")
GRAFIK_TEMPLATE = Path(r"c:\Users\Макс\Downloads\grafik_2026_04.xlsx")
OUT_PATH = Path(r"c:\Users\Макс\Downloads\grafik_2026_04.xlsx")

# Опечатки в шаблоне grafik относительно ФИО в HTML
PK_ALIASES = {
    "кудашина ю": "кудашкина ю",
}

_ALIASES = {
    "д": "д",
    "н": "н",
    "от": "от",
    "отпуск": "от",
    "бл": "б",
    "б": "б",
    "п": "п",
    "прогул": "п",
    "кп": "кп",
    "компенсация": "кп",
}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s.replace("ё", "е")


def person_key(name: str) -> str:
    """Иванов М. и Иванов М.С. → одно ключевое «иванов м»."""
    parts = _norm(name).split()
    if len(parts) >= 2 and parts[1]:
        return f"{parts[0]} {parts[1][0]}"
    return parts[0] if parts else ""


def _cell_to_code(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    key = t.lower()
    if key in _ALIASES:
        return _ALIASES[key]
    return sanitize_schedule_cell(t)


def _find_name_td(tr) -> object | None:
    """Имя сотрудника в разных стилях ячеек (s14, цветные s27–s34…)."""
    for td in tr.find_all("td", attrs={"dir": "ltr"}):
        if "freezebar" in (td.get("class") or []):
            continue
        t = td.get_text(strip=True)
        if not t or len(t) < 5 or len(t) > 70:
            continue
        if t.lower().startswith("сумма"):
            continue
        if re.fullmatch(r"[\d\s]+", t):
            continue
        if " " in t and re.search(r"[А-ЯЁA-Zа-яёa-z.\-]", t):
            return td
    return None


def parse_html_schedule(html: str) -> dict[str, list[str]]:
    """Ключ person_key() → 30 кодов дней."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, list[str]] = {}
    for tr in soup.select("tbody tr"):
        name_td = _find_name_td(tr)
        if not name_td:
            continue
        name = name_td.get_text(strip=True)
        cells = tr.find_all("td")
        try:
            ix = cells.index(name_td)
        except ValueError:
            continue
        j = ix + 1
        while j < len(cells):
            cls = " ".join(cells[j].get("class") or [])
            if "freezebar" in cls:
                j += 1
                continue
            break
        if j + 30 > len(cells):
            continue
        days_raw = [cells[j + k].get_text(strip=True) for k in range(30)]
        pk = person_key(name)
        if pk:
            out[pk] = [_cell_to_code(x) for x in days_raw]
    return out


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    by_key = parse_html_schedule(html)
    tpl = pd.read_excel(GRAFIK_TEMPLATE, sheet_name=0, header=0)
    day_cols = _schedule_day_cols(2026, 4)
    rows: list[dict] = []
    missing: list[str] = []
    for i, r in tpl.iterrows():
        code = str(r["Код"]).strip()
        name = str(r["Сотрудник"]).strip()
        pk = PK_ALIASES.get(person_key(name), person_key(name))
        days = by_key.get(pk)
        if days is None:
            for k, v in by_key.items():
                if k == pk:
                    continue
                if pk.startswith(k) or k.startswith(pk):
                    days = v
                    break
        if days is None and len(pk.split()) >= 1:
            sur = pk.split()[0]
            hits = [k for k in by_key if k.split()[0].startswith(sur) or sur.startswith(k.split()[0])]
            if len(hits) == 1:
                days = by_key[hits[0]]
        if days is None:
            missing.append(name)
            days = [""] * 30
        row = {"Порядок": i + 1, "Код": code, "Сотрудник": name}
        for d, v in zip(day_cols, days, strict=False):
            row[d] = v
        rows.append(row)
    out = pd.DataFrame(rows)
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as w:
        out.to_excel(w, index=False, sheet_name="График")
    rep = OUT_PATH.with_name("grafik_from_html_report.txt")
    rep.write_text(
        "Имён из HTML: %d\nСтрок в шаблоне grafik: %d\n"
        "Не сопоставлено (дни пустые — в HTML нет строки или другая фамилия): %s\n"
        % (len(by_key), len(rows), ", ".join(missing) if missing else "—"),
        encoding="utf-8",
    )
    print("OK", OUT_PATH)
    print(rep.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
