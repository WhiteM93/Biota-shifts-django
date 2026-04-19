"""Загрузка данных из PostgreSQL (кэш выборок через functools; справочник сотрудников без кэша)."""
import functools
from datetime import date, datetime

import pandas as pd
import psycopg

from biota_shifts.config import _config_str


def employee_active_where_suffix() -> str:
    """Доп. AND для personnel_employee e: не подставлять уволенных в справочник.

    По умолчанию ZKBioTA / zkbiota: признак «уволен» — ``is_active = false`` в ``personnel_employee``.
    Переопределение: BIOTA_EMPLOYEE_ACTIVE_SQL или BIOTA_INCLUDE_DISMISSED_EMPLOYEES=1.
    """
    if (_config_str("BIOTA_INCLUDE_DISMISSED_EMPLOYEES") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return ""
    custom = (_config_str("BIOTA_EMPLOYEE_ACTIVE_SQL") or "").strip()
    if custom:
        if not custom.lower().startswith("and "):
            custom = "and " + custom
        return " " + custom
    # ZKBioTA (PostgreSQL zkbiota): сотрудник скрыт в UI при is_active = false
    return " and coalesce(e.is_active, true) = true"
from biota_shifts.emp_codes import normalize_emp_codes_list, sql_emp_code
from biota_shifts.schedule import available_schedule_years


def db_config() -> dict:
    """Подключение к PostgreSQL Biota. На каждом ПК: скопируйте `.streamlit/secrets.toml` из примера или задайте BIOTA_DB_* в окружении."""
    return {
        "host": _config_str("BIOTA_DB_HOST", "localhost"),
        "port": int(_config_str("BIOTA_DB_PORT", "5432") or "5432"),
        "dbname": _config_str("BIOTA_DB_NAME", "biota_db"),
        "user": _config_str("BIOTA_DB_USER", "biota_user"),
        "password": _config_str("BIOTA_DB_PASSWORD", ""),
        # Keep UI responsive when DB is unreachable.
        "connect_timeout": int(_config_str("BIOTA_DB_CONNECT_TIMEOUT", "3") or "3"),
    }


def _db_cache_key(cfg: dict) -> tuple:
    """Ключ для кэша выборок (хэшируемый)."""
    return (
        str(cfg["host"]),
        int(cfg["port"]),
        str(cfg["dbname"]),
        str(cfg["user"]),
        str(cfg["password"]),
        int(cfg.get("connect_timeout", 3) or 3),
    )


def _conn_from_key(db_key: tuple) -> dict:
    return {
        "host": db_key[0],
        "port": db_key[1],
        "dbname": db_key[2],
        "user": db_key[3],
        "password": db_key[4],
        "connect_timeout": db_key[5],
    }


def _load_employees_uncached(db_key: tuple) -> pd.DataFrame:
    """Без LRU: ФИО/отделы в справочнике должны подтягиваться сразу после правок в Biota."""
    cfg = _conn_from_key(db_key)
    sql = """
    select
        e.emp_code,
        coalesce(e.last_name, '') as last_name,
        coalesce(e.first_name, '') as first_name,
        coalesce(max(d.dept_name), '') as department_name,
        coalesce(p.position_name, '') as position_name,
        coalesce(string_agg(distinct a.area_name, ', '), '') as area_name
    from personnel_employee e
    left join personnel_department d on d.id = e.department_id
    left join personnel_position p on p.id = e.position_id
    left join personnel_employee_area ea on ea.employee_id = e.id
    left join personnel_area a on a.id = ea.area_id
    where coalesce(e.emp_code, '') <> ''
""" + employee_active_where_suffix() + """
    group by e.emp_code, e.last_name, e.first_name, e.department_id, p.position_name
    order by e.emp_code
    """
    with psycopg.connect(**cfg) as conn:
        return pd.read_sql(sql, conn)


def load_employees(cfg: dict) -> pd.DataFrame:
    return _load_employees_uncached(_db_cache_key(cfg))


@functools.lru_cache(maxsize=128)
def _load_shifts_cached(
    db_key: tuple, emp_code: str, month_start_s: str, month_end_s: str
) -> pd.DataFrame:
    cfg = _conn_from_key(db_key)
    month_start = date.fromisoformat(month_start_s)
    month_end = date.fromisoformat(month_end_s)
    sql = """
    with calendar_days as (
        select generate_series(%(month_start)s::date, %(month_end)s::date, interval '1 day')::date as shift_date
    ),
    emp_payload as (
        select
            tc.att_date,
            min(tc.check_in) as planned_start,
            max(tc.check_out) as planned_end,
            min(tc.clock_in) as actual_in,
            max(tc.clock_out) as actual_out
        from att_payloadtimecard tc
        join personnel_employee e on e.id = tc.emp_id
        where e.emp_code = %(emp_code)s
          and tc.att_date between %(month_start)s and %(month_end)s
        group by tc.att_date
    )
    select
        cd.shift_date,
        case
            when ep.planned_start is null then null
            when extract(hour from ep.planned_start) >= 20 then 'night'
            else 'day'
        end as shift_type,
        ep.planned_start,
        ep.planned_end,
        ep.actual_in,
        ep.actual_out,
        case
            when ep.actual_in is not null and ep.actual_out is not null
                then round(extract(epoch from (ep.actual_out - ep.actual_in)) / 3600.0, 2)
            else null
        end as worked_hours,
        coalesce(
            round(extract(epoch from (ep.actual_in - ep.planned_start)) / 60.0)::int,
            0
        ) as arrival_offset_minutes,
        coalesce(
            round(extract(epoch from (ep.actual_out - ep.planned_end)) / 60.0)::int,
            0
        ) as leave_offset_minutes,
        null::integer as punches_count
    from calendar_days cd
    left join emp_payload ep on ep.att_date = cd.shift_date
    order by cd.shift_date;
    """
    with psycopg.connect(**cfg) as conn:
        return pd.read_sql(
            sql,
            conn,
            params={
                "emp_code": emp_code,
                "month_start": month_start,
                "month_end": month_end,
            },
        )


def load_shifts(cfg: dict, emp_code: str, month_start: date, month_end: date) -> pd.DataFrame:
    ec = sql_emp_code(emp_code)
    if not ec:
        return pd.DataFrame()
    return _load_shifts_cached(
        _db_cache_key(cfg),
        ec,
        month_start.isoformat(),
        month_end.isoformat(),
    )


_SHIFTS_BATCH_COLS = [
    "emp_code",
    "shift_date",
    "shift_type",
    "planned_start",
    "planned_end",
    "actual_in",
    "actual_out",
    "worked_hours",
    "arrival_offset_minutes",
    "leave_offset_minutes",
    "punches_count",
]


@functools.lru_cache(maxsize=64)
def _load_shifts_batch_cached(
    db_key: tuple,
    emp_codes_tuple: tuple[str, ...],
    month_start_s: str,
    month_end_s: str,
) -> pd.DataFrame:
    """Табель Biota за месяц для списка сотрудников — один запрос."""
    if not emp_codes_tuple:
        return pd.DataFrame(columns=_SHIFTS_BATCH_COLS)
    cfg = _conn_from_key(db_key)
    month_start = date.fromisoformat(month_start_s)
    month_end = date.fromisoformat(month_end_s)
    sql = """
    with calendar_days as (
        select generate_series(%(month_start)s::date, %(month_end)s::date, interval '1 day')::date as shift_date
    ),
    emps as (
        select e.emp_code::text as emp_code, e.id
        from personnel_employee e
        where e.emp_code = any(%(emp_codes)s)
    ),
    emp_payload as (
        select
            e.emp_code::text as emp_code,
            tc.att_date,
            min(tc.check_in) as planned_start,
            max(tc.check_out) as planned_end,
            min(tc.clock_in) as actual_in,
            max(tc.clock_out) as actual_out
        from att_payloadtimecard tc
        join personnel_employee e on e.id = tc.emp_id
        where e.emp_code = any(%(emp_codes)s)
          and tc.att_date between %(month_start)s and %(month_end)s
        group by e.emp_code, tc.att_date
    )
    select
        em.emp_code,
        cd.shift_date,
        case
            when ep.planned_start is null then null
            when extract(hour from ep.planned_start) >= 20 then 'night'
            else 'day'
        end as shift_type,
        ep.planned_start,
        ep.planned_end,
        ep.actual_in,
        ep.actual_out,
        case
            when ep.actual_in is not null and ep.actual_out is not null
                then round(extract(epoch from (ep.actual_out - ep.actual_in)) / 3600.0, 2)
            else null
        end as worked_hours,
        coalesce(
            round(extract(epoch from (ep.actual_in - ep.planned_start)) / 60.0)::int,
            0
        ) as arrival_offset_minutes,
        coalesce(
            round(extract(epoch from (ep.actual_out - ep.planned_end)) / 60.0)::int,
            0
        ) as leave_offset_minutes,
        null::integer as punches_count
    from emps em
    cross join calendar_days cd
    left join emp_payload ep on ep.emp_code = em.emp_code and ep.att_date = cd.shift_date
    order by em.emp_code, cd.shift_date;
    """
    with psycopg.connect(**cfg) as conn:
        return pd.read_sql(
            sql,
            conn,
            params={
                "emp_codes": list(emp_codes_tuple),
                "month_start": month_start,
                "month_end": month_end,
            },
        )


def load_shifts_batch(
    cfg: dict, emp_codes: list[str], month_start: date, month_end: date
) -> pd.DataFrame:
    if not emp_codes:
        return pd.DataFrame(columns=_SHIFTS_BATCH_COLS)
    key_codes = tuple(sorted(normalize_emp_codes_list(emp_codes)))
    return _load_shifts_batch_cached(
        _db_cache_key(cfg),
        key_codes,
        month_start.isoformat(),
        month_end.isoformat(),
    )


@functools.lru_cache(maxsize=64)
def _load_shifts_hours_batch_cached(
    db_key: tuple,
    emp_codes_tuple: tuple[str, ...],
    month_start_s: str,
    month_end_s: str,
) -> pd.DataFrame:
    cfg = _conn_from_key(db_key)
    month_start = date.fromisoformat(month_start_s)
    month_end = date.fromisoformat(month_end_s)
    sql = """
    with emp_punches as (
        select
            t.emp_code::text as emp_code,
            (t.punch_time at time zone 'Europe/Moscow')::date as shift_date,
            min(t.punch_time) as first_punch,
            max(t.punch_time) as last_punch
        from iclock_transaction t
        where t.emp_code = any(%(emp_codes)s)
          and (t.punch_time at time zone 'Europe/Moscow')::date between %(month_start)s and %(month_end)s
        group by t.emp_code, (t.punch_time at time zone 'Europe/Moscow')::date
    )
    select
        ep.emp_code,
        ep.shift_date,
        case
            when ep.first_punch is not null and ep.last_punch is not null
                then round(extract(epoch from (ep.last_punch - ep.first_punch)) / 3600.0, 2)
            else null
        end as worked_hours
    from emp_punches ep
    order by ep.emp_code, ep.shift_date;
    """
    with psycopg.connect(**cfg) as conn:
        return pd.read_sql(
            sql,
            conn,
            params={
                "emp_codes": list(emp_codes_tuple),
                "month_start": month_start,
                "month_end": month_end,
            },
        )


def load_shifts_hours_batch(
    cfg: dict, emp_codes: list[str], month_start: date, month_end: date
) -> pd.DataFrame:
    """Факт часов по Biota (clock_in → clock_out) для списка сотрудников за месяц — одна строка на (код, день)."""
    if not emp_codes:
        return pd.DataFrame(columns=["emp_code", "shift_date", "worked_hours"])
    key_codes = tuple(sorted(normalize_emp_codes_list(emp_codes)))
    return _load_shifts_hours_batch_cached(
        _db_cache_key(cfg),
        key_codes,
        month_start.isoformat(),
        month_end.isoformat(),
    )


@functools.lru_cache(maxsize=256)
def _load_years_cached(db_key: tuple, emp_code: str) -> list[int]:
    cfg = _conn_from_key(db_key)
    sql = """
    select distinct extract(year from tc.att_date)::int as y
    from att_payloadtimecard tc
    join personnel_employee e on e.id = tc.emp_id
    where e.emp_code = %(emp_code)s
      and tc.att_date is not null
    order by y desc
    """
    with psycopg.connect(**cfg) as conn:
        df = pd.read_sql(sql, conn, params={"emp_code": emp_code})
    return df["y"].tolist()


def load_years(cfg: dict, emp_code: str) -> list[int]:
    ec = sql_emp_code(emp_code)
    if not ec:
        return []
    return _load_years_cached(_db_cache_key(cfg), ec)


@functools.lru_cache(maxsize=256)
def _load_punch_years_cached(db_key: tuple, emp_code: str) -> list[int]:
    cfg = _conn_from_key(db_key)
    sql = """
    select distinct extract(year from punch_time at time zone 'Europe/Moscow')::int as y
    from iclock_transaction
    where emp_code = %(emp_code)s
    order by y desc
    """
    with psycopg.connect(**cfg) as conn:
        df = pd.read_sql(sql, conn, params={"emp_code": emp_code})
    return df["y"].tolist() if not df.empty else []


def load_punch_years(cfg: dict, emp_code: str) -> list[int]:
    ec = sql_emp_code(emp_code)
    if not ec:
        return []
    return _load_punch_years_cached(_db_cache_key(cfg), ec)


@functools.lru_cache(maxsize=256)
def _load_iclock_punches_cached(
    db_key: tuple, emp_code: str, day_from_s: str, day_to_s: str
) -> pd.DataFrame:
    cfg = _conn_from_key(db_key)
    day_from = date.fromisoformat(day_from_s)
    day_to = date.fromisoformat(day_to_s)
    sql = """
    select
        punch_time,
        verify_type,
        punch_state,
        terminal_alias,
        terminal_sn
    from iclock_transaction
    where emp_code = %(emp_code)s
      and (punch_time at time zone 'Europe/Moscow')::date >= %(day_from)s
      and (punch_time at time zone 'Europe/Moscow')::date <= %(day_to)s
    order by punch_time
    """
    with psycopg.connect(**cfg) as conn:
        return pd.read_sql(
            sql,
            conn,
            params={"emp_code": emp_code, "day_from": day_from, "day_to": day_to},
        )


def load_iclock_punches(cfg: dict, emp_code: str, day_from: date, day_to: date) -> pd.DataFrame:
    """Отметки с терминалов за интервал календарных дней [day_from, day_to] по дате в МСК."""
    ec = sql_emp_code(emp_code)
    if not ec:
        return pd.DataFrame()
    return _load_iclock_punches_cached(
        _db_cache_key(cfg),
        ec,
        day_from.isoformat(),
        day_to.isoformat(),
    )


_ICLOCK_BATCH_COLS = [
    "emp_code",
    "punch_time",
    "verify_type",
    "punch_state",
    "terminal_alias",
    "terminal_sn",
]


@functools.lru_cache(maxsize=64)
def _load_iclock_punches_batch_cached(
    db_key: tuple,
    emp_codes_tuple: tuple[str, ...],
    day_from_s: str,
    day_to_s: str,
) -> pd.DataFrame:
    """Отметки СКУД за интервал для списка сотрудников — один запрос."""
    if not emp_codes_tuple:
        return pd.DataFrame(columns=_ICLOCK_BATCH_COLS)
    cfg = _conn_from_key(db_key)
    day_from = date.fromisoformat(day_from_s)
    day_to = date.fromisoformat(day_to_s)
    sql = """
    select
        emp_code::text as emp_code,
        punch_time,
        verify_type,
        punch_state,
        terminal_alias,
        terminal_sn
    from iclock_transaction
    where emp_code = any(%(emp_codes)s)
      and (punch_time at time zone 'Europe/Moscow')::date >= %(day_from)s
      and (punch_time at time zone 'Europe/Moscow')::date <= %(day_to)s
    order by emp_code, punch_time
    """
    with psycopg.connect(**cfg) as conn:
        return pd.read_sql(
            sql,
            conn,
            params={
                "emp_codes": list(emp_codes_tuple),
                "day_from": day_from,
                "day_to": day_to,
            },
        )


def load_iclock_punches_batch(
    cfg: dict, emp_codes: list[str], day_from: date, day_to: date
) -> pd.DataFrame:
    if not emp_codes:
        return pd.DataFrame(columns=_ICLOCK_BATCH_COLS)
    key_codes = tuple(sorted(normalize_emp_codes_list(emp_codes)))
    return _load_iclock_punches_batch_cached(
        _db_cache_key(cfg),
        key_codes,
        day_from.isoformat(),
        day_to.isoformat(),
    )


def clear_biota_db_cache() -> None:
    """Сбросить кэш всех выборок из PostgreSQL (повторно с БД — после кнопки «Обновить данные из БД»)."""
    _load_shifts_cached.cache_clear()
    _load_shifts_batch_cached.cache_clear()
    _load_shifts_hours_batch_cached.cache_clear()
    _load_years_cached.cache_clear()
    _load_punch_years_cached.cache_clear()
    _load_iclock_punches_cached.cache_clear()
    _load_iclock_punches_batch_cached.cache_clear()


def merged_year_options(cfg: dict, emp_code: str) -> list[int]:
    ys: set[int] = set(available_schedule_years())
    ys.update(load_years(cfg, emp_code))
    ys.update(load_punch_years(cfg, emp_code))
    if not ys:
        y = datetime.now().year
        ys = {y - 1, y, y + 1}
    return sorted(ys, reverse=True)
