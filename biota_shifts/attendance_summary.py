"""Сводка: кто по графику ещё не отметился в СКУД (утро / вечер)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from biota_shifts import db as biota_db
from biota_shifts.constants import MSK
from biota_shifts.emp_codes import normalize_emp_code
from biota_shifts.logic import (
    _punch_series_msk,
    _schedule_code_for_day,
    _schedule_row_for_emp,
    first_last_for_day_shift,
    first_last_for_night_shift,
)
from biota_shifts.notification_settings import blacklist_set, load_notification_settings
from biota_shifts.schedule import employee_label_row

SLOT_MORNING = "morning"
SLOT_EVENING = "evening"


@dataclass
class AbsentEmployee:
    emp_code: str
    label: str
    department_name: str
    shift_code: str
    first_punch_at: datetime | None


@dataclass
class AttendanceSummary:
    slot: str
    shift_date: date
    check_at: datetime
    shift_label: str
    absent: list[AbsentEmployee]

    @property
    def absent_count(self) -> int:
        return len(self.absent)


def _parse_hm_on_day(d: date, hm: str) -> datetime:
    parts = (hm or "00:00").strip().split(":")
    h = int(parts[0]) if parts else 0
    m = int(parts[1]) if len(parts) > 1 else 0
    return datetime(d.year, d.month, d.day, h, m, 0, tzinfo=MSK)


def _punches_until(pts_msk: pd.Series, cutoff: datetime) -> pd.Series:
    if pts_msk.empty:
        return pts_msk
    return pts_msk[pts_msk <= cutoff]


def _is_not_marked_day(pts_msk: pd.Series, d: date, cutoff: datetime) -> tuple[bool, datetime | None]:
    pts_cutoff = _punches_until(pts_msk, cutoff)
    first_dt, _ = first_last_for_day_shift(pts_cutoff, d)
    first_all, _ = first_last_for_day_shift(pts_msk, d)
    if first_dt is None:
        return True, first_all
    if first_dt > cutoff:
        return True, first_dt
    return False, first_dt


def _is_not_marked_night(pts_msk: pd.Series, d: date, cutoff: datetime) -> tuple[bool, datetime | None]:
    pts_cutoff = _punches_until(pts_msk, cutoff)
    first_dt, _ = first_last_for_night_shift(pts_cutoff, d)
    first_all, _ = first_last_for_night_shift(pts_msk, d)
    if first_dt is None:
        return True, first_all
    if first_dt > cutoff:
        return True, first_dt
    return False, first_dt


def build_attendance_summary(
    slot: str,
    *,
    employees_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    punches_df: pd.DataFrame,
    shift_date: date | None = None,
    check_at: datetime | None = None,
    settings: dict | None = None,
) -> AttendanceSummary:
    """slot: morning (д к 08:20) или evening (н к 20:20)."""
    slot = (slot or "").strip().lower()
    if slot not in (SLOT_MORNING, SLOT_EVENING):
        raise ValueError(f"Неизвестный слот: {slot}")

    cfg = load_notification_settings() if settings is None else settings
    bl = blacklist_set(cfg)
    d = shift_date or datetime.now(MSK).date()

    if slot == SLOT_MORNING:
        want_code = "д"
        hm = str(cfg.get("morning_time") or "08:20")
        shift_label = "дневная смена (д)"
    else:
        want_code = "н"
        hm = str(cfg.get("evening_time") or "20:20")
        shift_label = "ночная смена (н)"

    cutoff = check_at or _parse_hm_on_day(d, hm)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=MSK)

    absent: list[AbsentEmployee] = []
    if employees_df.empty:
        return AttendanceSummary(slot=slot, shift_date=d, check_at=cutoff, shift_label=shift_label, absent=absent)

    punches_by_code: dict[str, pd.DataFrame] = {}
    if not punches_df.empty and "emp_code" in punches_df.columns:
        for code, grp in punches_df.groupby(punches_df["emp_code"].map(normalize_emp_code)):
            if code:
                punches_by_code[code] = grp

    for _, emp in employees_df.iterrows():
        code = normalize_emp_code(emp.get("emp_code"))
        if not code or code in bl:
            continue
        row = _schedule_row_for_emp(schedule_df, code)
        day_code = _schedule_code_for_day(row, d)
        if day_code != want_code:
            continue

        p_df = punches_by_code.get(code, pd.DataFrame())
        pts_msk = _punch_series_msk(p_df)

        if slot == SLOT_MORNING:
            missing, first_dt = _is_not_marked_day(pts_msk, d, cutoff)
        else:
            missing, first_dt = _is_not_marked_night(pts_msk, d, cutoff)

        if not missing:
            continue

        absent.append(
            AbsentEmployee(
                emp_code=code,
                label=employee_label_row(emp),
                department_name=str(emp.get("department_name") or "").strip() or "—",
                shift_code=want_code,
                first_punch_at=first_dt,
            )
        )

    absent.sort(key=lambda x: (x.department_name.lower(), x.label.lower(), x.emp_code))
    return AttendanceSummary(
        slot=slot,
        shift_date=d,
        check_at=cutoff,
        shift_label=shift_label,
        absent=absent,
    )


def load_attendance_summary_from_db(
    slot: str,
    *,
    shift_date: date | None = None,
    check_at: datetime | None = None,
    settings: dict | None = None,
) -> AttendanceSummary:
    cfg_db = biota_db.db_config()
    employees_df = biota_db.load_employees(cfg_db)
    d = shift_date or datetime.now(MSK).date()
    y, m = d.year, d.month

    from shifts.graph_schedule_source import get_skud_schedule_source, load_schedule_table_resolved

    schedule_df = load_schedule_table_resolved(employees_df, y, m, source=get_skud_schedule_source())

    day_from = d - timedelta(days=1)
    day_to = d + timedelta(days=1)
    codes = [normalize_emp_code(c) for c in employees_df["emp_code"].tolist() if normalize_emp_code(c)]
    punches_df = biota_db.load_iclock_punches_batch(cfg_db, codes, day_from, day_to)

    return build_attendance_summary(
        slot,
        employees_df=employees_df,
        schedule_df=schedule_df,
        punches_df=punches_df,
        shift_date=d,
        check_at=check_at,
        settings=settings,
    )


def format_summary_text(summary: AttendanceSummary) -> str:
    d_str = summary.shift_date.strftime("%d.%m.%Y")
    t_str = summary.check_at.strftime("%H:%M")
    slot_title = "Утренняя сводка" if summary.slot == SLOT_MORNING else "Вечерняя сводка"
    lines = [
        f"{slot_title} — {d_str}, проверка к {t_str} МСК",
        f"Смена: {summary.shift_label}",
        "",
    ]
    if not summary.absent:
        lines.append("Все отметились в СКУД — замечаний нет.")
    else:
        lines.append(f"Не отметились ({summary.absent_count}):")
        cur_dep = None
        for item in summary.absent:
            if item.department_name != cur_dep:
                cur_dep = item.department_name
                lines.append("")
                lines.append(f"[{cur_dep}]")
            extra = ""
            if item.first_punch_at is not None:
                extra = f" (первая отметка позже: {item.first_punch_at.strftime('%H:%M')})"
            lines.append(f"  • {item.label} — таб. {item.emp_code}{extra}")
    lines.append("")
    lines.append("— Biota / MetaBase")
    return "\n".join(lines)


def format_summary_html(summary: AttendanceSummary) -> str:
    text = format_summary_text(summary)
    return "<pre style=\"font-family:monospace;font-size:13px;white-space:pre-wrap;\">" + (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ) + "</pre>"


def send_summary_telegram(summary: AttendanceSummary, settings: dict | None = None) -> int:
    from biota_shifts.notification_settings import load_notification_settings
    from biota_shifts.telegram_notify import resolve_telegram_bot_token, send_telegram_broadcast

    cfg = load_notification_settings() if settings is None else settings
    token = resolve_telegram_bot_token(cfg)
    chat_ids = cfg.get("telegram_chat_ids") or []
    if not token or not chat_ids:
        return 0
    body = format_summary_text(summary)
    return send_telegram_broadcast(token, chat_ids, body)
