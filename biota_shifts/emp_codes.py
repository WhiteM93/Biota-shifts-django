"""Нормализация emp_code для сопоставления с PostgreSQL (123 vs «123.0» из Excel/pandas)."""
import pandas as pd


def normalize_emp_code(x) -> str:
    """Единый вид кода сотрудника для SQL и merge."""
    if x is None or isinstance(x, bool):
        return ""
    try:
        if pd.isna(x):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(x, float) and pd.isna(x):
        return ""
    if isinstance(x, (int, float)):
        try:
            if float(x) == int(float(x)):
                return str(int(float(x)))
        except (TypeError, ValueError, OverflowError):
            pass
    s = str(x).strip()
    if not s or s.lower() in ("nan", "<na>", "nat"):
        return ""
    try:
        f = float(s.replace(",", "."))
        if f == int(f):
            return str(int(f))
    except ValueError:
        pass
    return s


def normalize_emp_codes_list(emp_codes: list) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in emp_codes:
        n = normalize_emp_code(c)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def sql_emp_code(emp_code: str) -> str:
    """Код для параметров SQL (не пустая строка)."""
    n = normalize_emp_code(emp_code)
    if n:
        return n
    return str(emp_code).strip() if emp_code is not None else ""
