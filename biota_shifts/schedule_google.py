"""Загрузка и сохранение графика в Google Sheets (формат «График МВ»)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from biota_shifts.config import APP_DIR
from biota_shifts.constants import MONTH_NAMES_RU, SCHEDULE_CODES
from biota_shifts.emp_codes import normalize_emp_code
from biota_shifts.schedule import PREV_MONTH_KEYS, _schedule_day_cols, sanitize_schedule_cell

SCHEDULE_SOURCE_LOCAL = "local"
SCHEDULE_SOURCE_GOOGLE = "google"

DEFAULT_WORKSHEET_FALLBACK = "График"
# Листы вида «Июль 2026» в таблице https://docs.google.com/spreadsheets/d/1h7rJYYK6GMtPAh3BT0PWHufGnk2PeeDKRlULX5fglm4
DEFAULT_SPREADSHEET_ID = "1h7rJYYK6GMtPAh3BT0PWHufGnk2PeeDKRlULX5fglm4"

# Строка с номерами дней (1-based в Google Sheets)
MV_DAY_HEADER_ROW = 2
# Первая строка с сотрудником: A — табельный номер, B — ФИО, C+ — смены
MV_DATA_START_ROW = 3
MV_CODE_COL = 0
MV_NAME_COL = 1
MV_FIRST_DAY_COL = 2

# Синонимы кодов в Google-таблице → внутренние коды графика
_GOOGLE_SHIFT_ALIASES: dict[str, str] = {
    "д": "д",
    "дн": "д",
    "день": "д",
    "н": "н",
    "ноч": "н",
    "ночь": "н",
    "от": "от",
    "б": "б",
    "бл": "б",
    "п": "п",
    "кп": "кп",
}

# Обратное отображение при записи в Google (дневная — «Д»)
_TO_GOOGLE_DISPLAY = {
    "д": "Д",
    "н": "Н",
    "от": "от",
    "б": "б",
    "п": "п",
    "кп": "кп",
    "": "",
}


class GoogleScheduleError(Exception):
    """Ошибка чтения/записи графика в Google Sheets."""


def _config_str(key: str, default: str = "") -> str:
    from biota_shifts.config import _config_str as cfg

    return cfg(key, default)


def google_schedule_spreadsheet_id() -> str:
    return _config_str("BIOTA_GOOGLE_SCHEDULE_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID)


def google_schedule_sheet_template() -> str:
    return _config_str("BIOTA_GOOGLE_SCHEDULE_SHEET", "")


def google_schedule_credentials_path() -> Path | None:
    raw = _config_str("BIOTA_GOOGLE_SCHEDULE_CREDENTIALS", "")
    candidates: list[Path] = []
    if raw:
        p = Path(raw)
        candidates.append(p if p.is_absolute() else APP_DIR / raw)
    candidates.append(APP_DIR / "secrets" / "google-service-account.json")
    for p in candidates:
        if p.is_file():
            return p
    return None


def google_schedule_read_only() -> bool:
    return _config_str("BIOTA_GOOGLE_SCHEDULE_READONLY", "").lower() in ("1", "true", "yes")


def google_schedule_configured() -> bool:
    creds = google_schedule_credentials_path()
    return bool(google_schedule_spreadsheet_id()) and creds is not None and creds.is_file()


def month_sheet_title(year: int, month: int, *, capitalize: bool = True) -> str:
    name = MONTH_NAMES_RU[month]
    if capitalize:
        name = name.capitalize()
    return f"{name} {year}"


def worksheet_name_candidates(year: int, month: int) -> list[str]:
    """Имена листов в порядке приоритета (основной — «Июль 2026»)."""
    names: list[str] = []
    template = google_schedule_sheet_template()
    if template:
        try:
            names.append(
                template.format(
                    year=year,
                    month=month,
                    month02d=f"{month:02d}",
                    ym=f"{year}_{month:02d}",
                    month_ru=MONTH_NAMES_RU[month],
                    month_title=month_sheet_title(year, month),
                )
            )
        except (KeyError, IndexError, ValueError):
            names.append(template)
    names.append(month_sheet_title(year, month))
    names.append(month_sheet_title(year, month, capitalize=False))
    names.append(f"{year}_{month:02d}")
    names.append(DEFAULT_WORKSHEET_FALLBACK)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        n = str(n).strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _prefer_ipv4_dns() -> None:
    """
    urllib3/requests ходят по адресам по порядку DNS.
    На многих VPS IPv6 к Google «чёрная дыра» (curl при этом ок — Happy Eyeballs).
    Форсируем IPv4, чтобы OAuth/Sheets не зависали бесконечно.
    """
    import socket

    if getattr(socket, "_biota_google_ipv4_patched", False):
        return
    _orig = socket.getaddrinfo

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        if family in (0, socket.AF_UNSPEC):
            try:
                return _orig(host, port, socket.AF_INET, type, proto, flags)
            except OSError:
                pass
        return _orig(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo  # type: ignore[method-assign]
    socket._biota_google_ipv4_patched = True  # type: ignore[attr-defined]


def _google_http_timeout_sec() -> float:
    raw = _config_str("BIOTA_GOOGLE_HTTP_TIMEOUT", "25").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 25.0


def _ensure_google_network() -> None:
    """IPv4 + таймаут сокета, чтобы API Google не вешал gunicorn."""
    import socket

    _prefer_ipv4_dns()
    if socket.getdefaulttimeout() is None:
        socket.setdefaulttimeout(_google_http_timeout_sec())


def _get_gspread_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise GoogleScheduleError(
            "Установите пакеты gspread и google-auth (см. requirements-google.txt)."
        ) from exc

    creds_path = google_schedule_credentials_path()
    if creds_path is None or not creds_path.is_file():
        raise GoogleScheduleError("Не задан файл учётных данных BIOTA_GOOGLE_SCHEDULE_CREDENTIALS.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    _ensure_google_network()
    credentials = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
    return gspread.authorize(credentials)


def _open_spreadsheet(client):
    sheet_id = google_schedule_spreadsheet_id()
    if not sheet_id:
        raise GoogleScheduleError("Не задан BIOTA_GOOGLE_SCHEDULE_SPREADSHEET_ID.")
    try:
        return client.open_by_key(sheet_id)
    except Exception as exc:
        raise GoogleScheduleError(f"Не удалось открыть таблицу Google: {exc}") from exc


def _resolve_worksheet(spreadsheet, year: int, month: int):
    worksheets = spreadsheet.worksheets()
    by_lower = {ws.title.strip().lower(): ws for ws in worksheets}
    for name in worksheet_name_candidates(year, month):
        key = name.strip().lower()
        if key in by_lower:
            return by_lower[key]
    month_ru = MONTH_NAMES_RU[month].lower()
    year_s = str(year)
    for ws in worksheets:
        title = ws.title.strip().lower()
        if month_ru in title and year_s in title and " - " not in title:
            return ws
    if worksheets:
        raise GoogleScheduleError(
            f"Лист за {month_sheet_title(year, month)} не найден. "
            f"Доступные: {', '.join(ws.title for ws in worksheets[:8])}…"
        )
    raise GoogleScheduleError("В Google-таблице нет листов.")


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - timedelta(days=1)).day


def _day_key_from_header(cell) -> str | None:
    s = str(cell).strip()
    if not s:
        return None
    if s.isdigit():
        d = int(s)
        if 1 <= d <= 31:
            return str(d)
    return None


def _find_day_header_row(values: list[list], year: int, month: int) -> int:
    """Индекс строки (0-based) с номерами дней 01…31."""
    limit = _days_in_month(year, month)
    best_idx = MV_DAY_HEADER_ROW - 1
    best_score = 0
    scan_rows = min(8, len(values))
    for ri in range(scan_rows):
        row = values[ri]
        score = 0
        for ci in range(MV_FIRST_DAY_COL, len(row)):
            key = _day_key_from_header(row[ci])
            if key and int(key) <= limit:
                score += 1
        if score > best_score:
            best_score = score
            best_idx = ri
    if best_score < 5:
        return MV_DAY_HEADER_ROW - 1
    return best_idx


def _day_col_map_from_header(header_row: list, year: int, month: int) -> dict[str, int]:
    """День «1»…«N» → индекс колонки (0-based)."""
    limit = _days_in_month(year, month)
    out: dict[str, int] = {}
    for ci in range(MV_FIRST_DAY_COL, len(header_row)):
        key = _day_key_from_header(header_row[ci])
        if key and int(key) <= limit and key not in out:
            out[key] = ci
    return out


def google_cell_to_schedule_code(v) -> str:
    """Код ячейки Google → внутренний код графика."""
    if pd.isna(v):
        return ""
    s = str(v).strip().lower()
    if not s:
        return ""
    mapped = _GOOGLE_SHIFT_ALIASES.get(s, s)
    return sanitize_schedule_cell(mapped)


def schedule_code_to_google_cell(code: str) -> str:
    c = sanitize_schedule_cell(code)
    return _TO_GOOGLE_DISPLAY.get(c, c)


def google_mv_values_to_schedule_df(values: list[list], year: int, month: int) -> pd.DataFrame:
    """
    Парсит лист «График МВ»:
    - строка 2 (или ближайшая с днями): 01, 02, … с колонки C;
    - с строки 3: A — табельный номер (emp_code / СКУД), B — ФИО, C+ — смены.
    """
    day_cols = _schedule_day_cols(year, month)
    if not values:
        return pd.DataFrame(columns=["Порядок", "Код", "Сотрудник"] + day_cols)

    header_idx = _find_day_header_row(values, year, month)
    day_col_map = _day_col_map_from_header(values[header_idx], year, month)
    rows: list[dict] = []
    order = 1

    for ri in range(header_idx + 1, len(values)):
        row = values[ri]
        if len(row) <= MV_NAME_COL:
            continue
        code = normalize_emp_code(row[MV_CODE_COL] if len(row) > MV_CODE_COL else "")
        name = str(row[MV_NAME_COL] if len(row) > MV_NAME_COL else "").strip()
        if not code and not name:
            continue
        if not code:
            continue
        rec: dict = {"Порядок": order, "Код": code, "Сотрудник": name or code}
        for col in day_cols:
            rec[col] = ""
        for day_key, ci in day_col_map.items():
            if day_key in rec:
                cell_val = row[ci] if ci < len(row) else ""
                rec[day_key] = google_cell_to_schedule_code(cell_val)
        rows.append(rec)
        order += 1

    if not rows:
        return pd.DataFrame(columns=["Порядок", "Код", "Сотрудник"] + day_cols)
    return pd.DataFrame(rows)[["Порядок", "Код", "Сотрудник"] + day_cols]


def _col_index_to_a1(col_idx: int) -> str:
    """0-based column index → буква колонки A, B, …, AA."""
    n = col_idx + 1
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _fetch_schedule_dataframe_from_api(year: int, month: int) -> tuple[pd.DataFrame, str]:
    """Прямое чтение листа Google (без кэша)."""
    client = _get_gspread_client()
    spreadsheet = _open_spreadsheet(client)
    worksheet = _resolve_worksheet(spreadsheet, year, month)
    try:
        values = worksheet.get_all_values()
    except Exception as exc:
        raise GoogleScheduleError(f"Не удалось прочитать лист «{worksheet.title}»: {exc}") from exc
    return google_mv_values_to_schedule_df(values, year, month), worksheet.title


def fetch_schedule_dataframe(
    year: int,
    month: int,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """График с листа Google в формате для normalize_schedule_excel (через локальный кэш)."""
    from biota_shifts.schedule_google_cache import load_google_schedule_cached

    return load_google_schedule_cached(year, month, force_refresh=force_refresh)


def save_schedule_dataframe_to_google(df: pd.DataFrame, year: int, month: int) -> str:
    """
    Обновляет ячейки смен на листе Google (без перезаписи всего листа).
    Нужен доступ «Редактор» для service account; при READONLY=1 запись пропускается.
    """
    if google_schedule_read_only():
        raise GoogleScheduleError(
            "Запись в Google отключена (BIOTA_GOOGLE_SCHEDULE_READONLY=1). Сохранён только локальный Excel."
        )

    client = _get_gspread_client()
    spreadsheet = _open_spreadsheet(client)
    worksheet = _resolve_worksheet(spreadsheet, year, month)
    try:
        values = worksheet.get_all_values()
    except Exception as exc:
        raise GoogleScheduleError(f"Не удалось прочитать лист «{worksheet.title}»: {exc}") from exc

    header_idx = _find_day_header_row(values, year, month)
    day_col_map = _day_col_map_from_header(values[header_idx], year, month)
    code_to_row: dict[str, int] = {}
    for ri in range(header_idx + 1, len(values)):
        row = values[ri]
        code = normalize_emp_code(row[MV_CODE_COL] if len(row) > MV_CODE_COL else "")
        if code:
            code_to_row[code] = ri

    updates: list[dict] = []
    for _, rec in df.iterrows():
        code = normalize_emp_code(rec.get("Код"))
        if not code or code not in code_to_row:
            continue
        sheet_row = code_to_row[code] + 1  # 1-based for A1
        for day_key, col_idx in day_col_map.items():
            if day_key in PREV_MONTH_KEYS:
                continue
            if day_key not in df.columns:
                continue
            display = schedule_code_to_google_cell(rec.get(day_key, ""))
            col_letter = _col_index_to_a1(col_idx)
            cell = f"{col_letter}{sheet_row}"
            updates.append({"range": cell, "values": [[display]]})

    if not updates:
        return worksheet.title

    try:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
    except Exception as exc:
        msg = str(exc).lower()
        if "permission" in msg or "403" in msg or "denied" in msg:
            raise GoogleScheduleError(
                "Нет прав на запись в Google Таблицу. Дайте service account роль «Редактор» "
                "или включите BIOTA_GOOGLE_SCHEDULE_READONLY=1 (только чтение + локальный Excel)."
            ) from exc
        raise GoogleScheduleError(f"Не удалось записать лист «{worksheet.title}»: {exc}") from exc
    return worksheet.title


def parse_schedule_source(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in (SCHEDULE_SOURCE_GOOGLE, "google_sheets", "sheets"):
        return SCHEDULE_SOURCE_GOOGLE
    return SCHEDULE_SOURCE_LOCAL
