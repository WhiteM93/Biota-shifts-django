"""Расчёты смен, табель, статистика, агрегация для главной."""
import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from biota_shifts.constants import (
    HOURS_GRID_NO_PUNCH,
    HOURS_GRID_SUFFIX_OUTSIDE_GRAPH,
    MSK,
    MSK_TZ,
    SCHEDULE_CODES,
    SCHEDULE_REMARK_RU,
    STATS_REMARK_OUTSIDE_GRAPH,
    VERIFY_TYPE_RU,
)
from biota_shifts import db
from biota_shifts.emp_codes import normalize_emp_code, normalize_emp_codes_list as _normalize_emp_codes_list
from biota_shifts.schedule import sanitize_schedule_cell


def _fmt_hours_cell(wh) -> str:
    """Часы из Biota (дробное число часов) → компактно «H:MM» для ячейки."""
    if wh is None or pd.isna(wh):
        return ""
    try:
        h = float(wh)
    except (TypeError, ValueError):
        return ""
    im = int(round(h * 60))
    return f"{im // 60:d}:{im % 60:02d}"


def _fmt_duration_between_marks(start_dt: datetime | None, end_dt: datetime | None) -> str:
    """Интервал между первой и последней отметкой в формате H:MM."""
    if start_dt is None or end_dt is None:
        return ""
    total_min = int(round((end_dt - start_dt).total_seconds() / 60.0))
    if total_min <= 0:
        return ""
    return f"{total_min // 60:d}:{total_min % 60:02d}"


def _has_positive_biota_hours(wh) -> bool:
    if wh is None or pd.isna(wh):
        return False
    try:
        return float(wh) > 0
    except (TypeError, ValueError):
        return False


def build_hours_grid_from_schedule(schedule_df: pd.DataFrame, hours_long: pd.DataFrame) -> pd.DataFrame:
    """Сетка как график; в днях — факт часов из Biota или пояснение по графику/отметкам."""
    grid = schedule_df.copy()
    day_cols = [c for c in grid.columns if str(c).isdigit()]
    lookup: dict[tuple[str, str], float] = {}
    if not hours_long.empty:
        hl = hours_long.copy()
        hl["emp_code"] = hl["emp_code"].map(normalize_emp_code)
        hl["day_key"] = pd.to_datetime(hl["shift_date"]).dt.day.astype(str)
        hl = hl.sort_values("shift_date").drop_duplicates(["emp_code", "day_key"], keep="last")
        for _, r in hl.iterrows():
            lookup[(str(r["emp_code"]), str(r["day_key"]))] = r["worked_hours"]
    for i in grid.index:
        ec = normalize_emp_code(grid.at[i, "Код"])
        for c in day_cols:
            code = sanitize_schedule_cell(grid.at[i, c])
            wh = lookup.get((ec, str(c)))
            if code in ("д", "н"):
                if _has_positive_biota_hours(wh):
                    grid.at[i, c] = _fmt_hours_cell(wh)
                else:
                    grid.at[i, c] = HOURS_GRID_NO_PUNCH
            elif not code:
                if _has_positive_biota_hours(wh):
                    grid.at[i, c] = _fmt_hours_cell(wh) + HOURS_GRID_SUFFIX_OUTSIDE_GRAPH
                else:
                    grid.at[i, c] = ""
            else:
                if _has_positive_biota_hours(wh):
                    grid.at[i, c] = _fmt_hours_cell(wh) + HOURS_GRID_SUFFIX_OUTSIDE_GRAPH
                else:
                    grid.at[i, c] = code
    return grid


def _schedule_row_for_emp(schedule_df: pd.DataFrame, emp_code: str) -> pd.Series | None:
    if schedule_df.empty or "Код" not in schedule_df.columns:
        return None
    want = normalize_emp_code(emp_code)
    if not want:
        return None
    m = schedule_df["Код"].map(normalize_emp_code) == want
    if not m.any():
        return None
    return schedule_df.loc[m].iloc[0]


def _punch_series_msk(punches_df: pd.DataFrame) -> pd.Series:
    if punches_df.empty:
        return pd.Series(pd.DatetimeIndex([], tz=MSK_TZ))
    return pd.to_datetime(punches_df["punch_time"], utc=True).dt.tz_convert(MSK_TZ)


def _schedule_code_for_day(row: pd.Series | None, d: date) -> str:
    if row is None:
        return ""
    col = str(d.day)
    if col not in row.index:
        return ""
    raw = row[col]
    code = str(raw).strip().lower() if raw is not None and str(raw).strip() != "" else ""
    return code if code in SCHEDULE_CODES else ""


def _pick_last_mark(
    sub: pd.Series,
    expected_end: datetime | None = None,
) -> datetime | None:
    if sub.empty:
        return None
    if expected_end is None:
        return sub.max().to_pydatetime()
    vals = [ts.to_pydatetime() for ts in sub.to_list()]
    vals.sort(key=lambda dt: (abs((dt - expected_end).total_seconds()), -dt.timestamp()))
    return vals[0]


def first_last_for_day_shift(
    punch_times_msk: pd.Series,
    d: date,
    expected_end: datetime | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    day_start = window_start or datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=MSK)
    day_end = window_end or (datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=MSK) + timedelta(days=1))
    mask = (punch_times_msk >= day_start) & (punch_times_msk < day_end)
    sub = punch_times_msk[mask]
    if sub.empty:
        return None, None
    tmin = sub.min()
    tmax = _pick_last_mark(sub, expected_end=expected_end)
    return tmin.to_pydatetime(), tmax


def first_last_for_night_shift(
    punch_times_msk: pd.Series,
    d: date,
    expected_end: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Ночная смена «на дату d»: интервал с полудня d до полудня d+1 (МСК)."""
    win_start = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=MSK)
    win_end = win_start + timedelta(days=1)
    mask = (punch_times_msk >= win_start) & (punch_times_msk < win_end)
    sub = punch_times_msk[mask]
    if sub.empty:
        return None, None
    return sub.min().to_pydatetime(), _pick_last_mark(sub, expected_end=expected_end)


def expected_shift_times(code: str, d: date) -> tuple[datetime | None, datetime | None]:
    """Ожидаемое начало/конец смены по графику (МСК)."""
    code = (code or "").strip().lower()
    if code == "д":
        start = datetime(d.year, d.month, d.day, 8, 0, 0, tzinfo=MSK)
        end = datetime(d.year, d.month, d.day, 20, 0, 0, tzinfo=MSK)
        return start, end
    if code == "н":
        start = datetime(d.year, d.month, d.day, 20, 0, 0, tzinfo=MSK)
        end = datetime(d.year, d.month, d.day, 8, 0, 0, tzinfo=MSK) + timedelta(days=1)
        return start, end
    return None, None


def shift_ended_msk_for_stats(code: str, d: date, now_msk: datetime) -> bool:
    """Для д/н: смена по графику уже завершилась (можно показывать пометку про неполные отметки)."""
    code = (code or "").strip().lower()
    if code == "д":
        end = datetime(d.year, d.month, d.day, 20, 0, 0, tzinfo=MSK)
        return now_msk >= end
    if code == "н":
        end = datetime(d.year, d.month, d.day, 8, 0, 0, tzinfo=MSK) + timedelta(days=1)
        return now_msk >= end
    return False


def minutes_diff(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return int(round((a - b).total_seconds() / 60.0))


def build_employee_stats_month(
    df_biota: pd.DataFrame,
    schedule_df: pd.DataFrame,
    emp_code: str,
    punches_df: pd.DataFrame,
) -> pd.DataFrame:
    """Статистика по сотруднику за месяц: первая/последняя отметка, опоздание и т.п."""
    row = _schedule_row_for_emp(schedule_df, emp_code)
    pts_msk = _punch_series_msk(punches_df)
    now_msk = datetime.now(MSK)

    out_rows: list[dict] = []
    for _, br in df_biota.iterrows():
        d = pd.Timestamp(br["shift_date"]).date()
        code = _schedule_code_for_day(row, d)

        exp_start, exp_end = expected_shift_times(code, d)
        if code == "д":
            first_dt, last_dt = first_last_for_day_shift(pts_msk, d, expected_end=exp_end)
        elif code == "н":
            first_dt, last_dt = first_last_for_night_shift(pts_msk, d, expected_end=exp_end)
        else:
            # Без смены в графике: отметки за календарный день (как в табеле)
            prev_code = _schedule_code_for_day(row, d - timedelta(days=1))
            if prev_code == "н":
                # Утренние отметки после ночной смены относим к предыдущей ночи, не к «вне графика».
                no_shift_start = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=MSK)
                no_shift_end = no_shift_start + timedelta(hours=12)
                first_dt, last_dt = first_last_for_day_shift(
                    pts_msk,
                    d,
                    window_start=no_shift_start,
                    window_end=no_shift_end,
                )
            else:
                first_dt, last_dt = first_last_for_day_shift(pts_msk, d)
        late_min = None
        leave_early_min = None
        if code in ("д", "н"):
            if exp_start is not None and first_dt is not None:
                late_min = max(0, minutes_diff(first_dt, exp_start) or 0)
            if exp_end is not None and last_dt is not None:
                leave_early_min = max(0, minutes_diff(exp_end, last_dt) or 0)

        wh = br.get("worked_hours")
        # Для статистики показываем фактический интервал по отметкам (как «Пришел/Ушел»),
        # а часы из Biota используем только как резерв.
        worked_shift = _fmt_duration_between_marks(first_dt, last_dt)
        if not worked_shift and wh is not None and pd.notna(wh):
            worked_shift = _fmt_hours_cell(wh)
        has_activity = (first_dt is not None or last_dt is not None) or _has_positive_biota_hours(wh)

        remark = ""
        if code in ("д", "н"):
            if (first_dt is None or last_dt is None) and shift_ended_msk_for_stats(code, d, now_msk):
                remark = "Нет одной из отметок по смене"
        elif code == "":
            if has_activity:
                remark = STATS_REMARK_OUTSIDE_GRAPH
            else:
                remark = SCHEDULE_REMARK_RU.get(code, "")
        elif code in ("от", "б", "п", "кп"):
            if has_activity:
                remark = (
                    f"{SCHEDULE_REMARK_RU.get(code, '')} "
                    f"Есть отметки или часы — укажите д или н в «График»."
                )
            else:
                remark = SCHEDULE_REMARK_RU.get(code, "")

        out_rows.append(
            {
                "Дата": d.strftime("%Y-%m-%d"),
                "График": code or "—",
                "Пометка": remark,
                "Пришел": first_dt.strftime("%H:%M") if first_dt else "",
                "Ушел": last_dt.strftime("%H:%M") if last_dt else "",
                "Отработано за смену": worked_shift,
                "Опоздал (мин)": late_min if late_min is not None else "",
                "Ранний уход (мин)": leave_early_min if leave_early_min is not None else "",
            }
        )

    return pd.DataFrame(out_rows)


def _stat_minutes_cell_to_int(v) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)) and not pd.isna(v):
        return max(0, int(round(float(v))))
    s = str(v).strip()
    if not s:
        return 0
    try:
        return max(0, int(float(s.replace(",", "."))))
    except ValueError:
        return 0


def _stats_row_date_in_month(row: dict, y: int, m: int, last_d: int) -> int | None:
    """День месяца из строки статистики или None, если дата вне месяца."""
    raw_d = row.get("Дата")
    if raw_d is None or (isinstance(raw_d, float) and pd.isna(raw_d)):
        return None
    try:
        d = pd.Timestamp(raw_d).date()
    except (ValueError, TypeError):
        try:
            d = datetime.strptime(str(raw_d)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    if d.year != y or d.month != m:
        return None
    di = d.day
    if di < 1 or di > last_d:
        return None
    return di


def aggregate_late_early_minutes_by_day(
    cfg: dict,
    emp_codes: list[str],
    schedule_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> tuple[int, int, pd.DataFrame]:
    """Суммы минут опозданий и ранних уходов по календарным дням месяца (все выбранные сотрудники)."""
    y, m = start_date.year, start_date.month
    last_d = calendar.monthrange(y, m)[1]
    sums_late = [0] * (last_d + 1)
    sums_early = [0] * (last_d + 1)
    p_from = start_date - timedelta(days=1)
    p_to = end_date + timedelta(days=1)

    emp_codes = _normalize_emp_codes_list(emp_codes)
    if not emp_codes:
        chart = pd.DataFrame(
            {
                "День": list(range(1, last_d + 1)),
                "Опоздания (мин)": [0] * last_d,
                "Ранний уход (мин)": [0] * last_d,
            }
        )
        return 0, 0, chart

    df_shifts_all = db.load_shifts_batch(cfg, emp_codes, start_date, end_date)
    p_df_all = db.load_iclock_punches_batch(cfg, emp_codes, p_from, p_to)
    _ec_shift = df_shifts_all["emp_code"].map(normalize_emp_code)
    _ec_punch = p_df_all["emp_code"].map(normalize_emp_code)

    for ec in emp_codes:
        ecs = ec
        df_b = df_shifts_all[_ec_shift == ecs].drop(columns=["emp_code"], errors="ignore")
        if df_b.empty:
            continue
        p_df = p_df_all[_ec_punch == ecs].drop(columns=["emp_code"], errors="ignore")
        stats = build_employee_stats_month(df_b, schedule_df, ecs, p_df)
        if stats.empty:
            continue
        for _, row in stats.iterrows():
            di = _stats_row_date_in_month(row.to_dict(), y, m, last_d)
            if di is None:
                continue
            sums_late[di] += _stat_minutes_cell_to_int(row.get("Опоздал (мин)"))
            sums_early[di] += _stat_minutes_cell_to_int(row.get("Ранний уход (мин)"))

    chart = pd.DataFrame(
        {
            "День": list(range(1, last_d + 1)),
            "Опоздания (мин)": [sums_late[d] for d in range(1, last_d + 1)],
            "Ранний уход (мин)": [sums_early[d] for d in range(1, last_d + 1)],
        }
    )
    return sum(sums_late), sum(sums_early), chart


def primary_area_label(area_name: str) -> str:
    """Первый участок из списка (как в БД) или «Без участка»."""
    s = str(area_name or "").strip()
    if not s:
        return "Без участка"
    return (s.split(",")[0] or "").strip() or "Без участка"


def late_early_minutes_per_employee_month(
    cfg: dict,
    emp_codes: list[str],
    schedule_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Суммы минут опозданий и раннего ухода по сотрудникам за месяц (как в статистике СКУД)."""
    emp_codes = _normalize_emp_codes_list(emp_codes)
    y, m = start_date.year, start_date.month
    last_d = calendar.monthrange(y, m)[1]
    tot_late = {c: 0 for c in emp_codes}
    tot_early = {c: 0 for c in emp_codes}
    if not emp_codes:
        return pd.DataFrame(columns=["emp_code", "Опоздания (мин)", "Ранний уход (мин)"])
    p_from = start_date - timedelta(days=1)
    p_to = end_date + timedelta(days=1)
    df_shifts_all = db.load_shifts_batch(cfg, emp_codes, start_date, end_date)
    p_df_all = db.load_iclock_punches_batch(cfg, emp_codes, p_from, p_to)
    _ec_shift = df_shifts_all["emp_code"].map(normalize_emp_code)
    _ec_punch = p_df_all["emp_code"].map(normalize_emp_code)
    for ec in emp_codes:
        ecs = ec
        df_b = df_shifts_all[_ec_shift == ecs].drop(columns=["emp_code"], errors="ignore")
        if df_b.empty:
            continue
        p_df = p_df_all[_ec_punch == ecs].drop(columns=["emp_code"], errors="ignore")
        stats = build_employee_stats_month(df_b, schedule_df, ecs, p_df)
        if stats.empty:
            continue
        for _, row in stats.iterrows():
            di = _stats_row_date_in_month(row.to_dict(), y, m, last_d)
            if di is None:
                continue
            tot_late[ecs] += _stat_minutes_cell_to_int(row.get("Опоздал (мин)"))
            tot_early[ecs] += _stat_minutes_cell_to_int(row.get("Ранний уход (мин)"))
    rows = [
        {"emp_code": k, "Опоздания (мин)": tot_late[k], "Ранний уход (мин)": tot_early[k]}
        for k in emp_codes
    ]
    return pd.DataFrame(rows)


def build_timesheet_view(
    df_biota: pd.DataFrame,
    schedule_df: pd.DataFrame,
    emp_code: str,
    punches_df: pd.DataFrame,
) -> pd.DataFrame:
    """Строки табеля: график, пометка, первая/последняя отметка по правилам смены + колонки Biota."""
    row = _schedule_row_for_emp(schedule_df, emp_code)
    pts_msk = _punch_series_msk(punches_df)

    rows: list[dict] = []
    for _, br in df_biota.iterrows():
        d = pd.Timestamp(br["shift_date"]).date()
        code = _schedule_code_for_day(row, d)

        remark = ""
        first_s = ""
        last_s = ""
        shift_human = ""

        if code in ("от", "б", "п", "кп", ""):
            if code == "" and _schedule_code_for_day(row, d - timedelta(days=1)) == "н":
                no_shift_start = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=MSK)
                no_shift_end = no_shift_start + timedelta(hours=12)
                t1, t2 = first_last_for_day_shift(
                    pts_msk,
                    d,
                    window_start=no_shift_start,
                    window_end=no_shift_end,
                )
            else:
                t1, t2 = first_last_for_day_shift(pts_msk, d)
            wh = br.get("worked_hours")
            has_activity = (t1 is not None or t2 is not None) or _has_positive_biota_hours(wh)
            shift_human = {"от": "отпуск", "б": "больничный", "п": "прогул", "кп": "компенсация"}.get(code, "—")
            if has_activity:
                if t1:
                    first_s = t1.strftime("%H:%M")
                if t2:
                    last_s = t2.strftime("%H:%M")
                if code == "":
                    remark = STATS_REMARK_OUTSIDE_GRAPH
                else:
                    remark = (
                        f"{SCHEDULE_REMARK_RU.get(code, '')} "
                        f"Есть отметки или часы — укажите д или н в «График»."
                    )
            else:
                remark = SCHEDULE_REMARK_RU.get(code, SCHEDULE_REMARK_RU[""])
        elif code == "д":
            shift_human = "дневная"
            _, exp_end = expected_shift_times("д", d)
            t1, t2 = first_last_for_day_shift(pts_msk, d, expected_end=exp_end)
            if t1:
                first_s = t1.strftime("%H:%M")
            if t2:
                last_s = t2.strftime("%H:%M")
            if not t1 and not t2:
                remark = "В графике дневная смена, отметок за этот день нет"
        elif code == "н":
            shift_human = "ночная"
            _, exp_end = expected_shift_times("н", d)
            t1, t2 = first_last_for_night_shift(pts_msk, d, expected_end=exp_end)
            if t1:
                first_s = t1.strftime("%H:%M (%d.%m)")
            if t2:
                last_s = t2.strftime("%H:%M (%d.%m)")
            if not t1 and not t2:
                remark = "В графике ночная смена (12:00–12:00+1), отметок в окне нет"

        planned_in = planned_out = actual_in = actual_out = ""
        interval_s = hours_s = ""
        ps = pd.to_datetime(br.get("planned_start"), utc=True, errors="coerce")
        pe = pd.to_datetime(br.get("planned_end"), utc=True, errors="coerce")
        ai = pd.to_datetime(br.get("actual_in"), utc=True, errors="coerce")
        ao = pd.to_datetime(br.get("actual_out"), utc=True, errors="coerce")
        if pd.notna(ps):
            planned_in = ps.tz_convert(MSK_TZ).strftime("%H:%M")
        if pd.notna(pe):
            planned_out = pe.tz_convert(MSK_TZ).strftime("%H:%M")
        if pd.notna(ai):
            actual_in = ai.tz_convert(MSK_TZ).strftime("%H:%M")
        if pd.notna(ao):
            actual_out = ao.tz_convert(MSK_TZ).strftime("%H:%M")
        if pd.notna(ai) and pd.notna(ao):
            delta = (ao - ai).total_seconds() / 60.0
            im = int(round(delta))
            interval_s = f"{im // 60:02d}:{im % 60:02d}"
            hours_s = f"{im // 60:02d} ч {im % 60:02d} м"

        rows.append(
            {
                "Дата": d.strftime("%Y-%m-%d"),
                "График": code or "—",
                "Смена (график)": shift_human,
                "Пометка": remark,
                "Первая отметка": first_s,
                "Последняя отметка": last_s,
                "План Biota (с)": planned_in,
                "План Biota (по)": planned_out,
                "Biota приход": actual_in,
                "Biota уход": actual_out,
                "Интервал (Biota)": interval_s,
                "Часы (Biota)": hours_s,
            }
        )

    return pd.DataFrame(rows)


def punches_list_for_month(punches_df: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if punches_df.empty:
        return pd.DataFrame(
            columns=["Дата и время (МСК)", "Терминал", "Тип", "Состояние", "SN"]
        )
    df = punches_df.copy()
    msk = pd.to_datetime(df["punch_time"], utc=True).dt.tz_convert(MSK_TZ)
    df["Дата и время (МСК)"] = msk.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["Терминал"] = df["terminal_alias"].fillna("")
    def _vt_label(x) -> str:
        if pd.isna(x):
            return ""
        try:
            xi = int(float(x))
        except (TypeError, ValueError):
            return str(x)
        return VERIFY_TYPE_RU.get(xi, f"код {xi}")

    df["Тип"] = df["verify_type"].map(_vt_label)

    df["Состояние"] = df["punch_state"].fillna("").astype(str)
    df["SN"] = df["terminal_sn"].fillna("").astype(str)
    dmsk = msk.dt.date
    mask = (dmsk >= start_date) & (dmsk <= end_date)
    out = df.loc[mask, ["Дата и время (МСК)", "Терминал", "Тип", "Состояние", "SN"]].reset_index(drop=True)
    return out
