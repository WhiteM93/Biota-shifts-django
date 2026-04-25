"""Аутентификация, пользователи, права, личный кабинет."""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta

import pandas as pd

try:
    import streamlit as st
    import streamlit.components.v1 as components
except ImportError:
    st = None  # type: ignore[assignment]
    components = None  # type: ignore[assignment]

from biota_shifts.config import (
    ADMIN_USERNAME,
    USERS_STORE_PATH,
    _USERNAME_RE,
    _admin_password,
    _config_str,
)
from biota_shifts.constants import MSK

_AUTH_COOKIE_NAME = "biota_auth"
_AUTH_COOKIE_TTL_DAYS = 30


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _auth_cookie_signing_key() -> bytes:
    # 1) явный секрет (предпочтительно)
    env_secret = (os.environ.get("BIOTA_AUTH_COOKIE_SECRET") or "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    sec_secret = (_config_str("BIOTA_AUTH_COOKIE_SECRET", "") or "").strip()
    if sec_secret:
        return sec_secret.encode("utf-8")
    # 2) fallback: admin password (лучше чем hardcode)
    ap = (_admin_password() or "").strip()
    if ap:
        return ap.encode("utf-8")
    # 3) крайний fallback для локального запуска
    return b"biota-local-dev-cookie-key"


def _mint_auth_cookie(username: str, *, ttl_days: int = _AUTH_COOKIE_TTL_DAYS) -> str:
    exp = int((datetime.now(MSK) + timedelta(days=ttl_days)).timestamp())
    payload = {"u": username, "exp": exp}
    payload_b64 = _b64url_encode(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(_auth_cookie_signing_key(), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify_auth_cookie(token: str) -> str | None:
    if not token or "." not in token:
        return None
    payload_b64, sig_hex = token.rsplit(".", 1)
    exp_sig = hmac.new(_auth_cookie_signing_key(), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(exp_sig, sig_hex):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    username = str(payload.get("u", "")).strip()
    exp = int(payload.get("exp", 0))
    if not username or exp <= int(datetime.now(MSK).timestamp()):
        return None
    if _is_admin(username):
        return ADMIN_USERNAME
    rec = _resolve_registered_user(username)
    if rec:
        if not rec.get("approved", True):
            return None
        return username
    return None


def _set_auth_cookie(username: str) -> None:
    if components is None:
        return
    token = _mint_auth_cookie(username)
    components.html(
        f"""
        <script>
        document.cookie = "{_AUTH_COOKIE_NAME}={token}; path=/; max-age={_AUTH_COOKIE_TTL_DAYS * 24 * 60 * 60}; samesite=lax";
        </script>
        """,
        height=0,
    )


def _clear_auth_cookie() -> None:
    if components is None:
        return
    components.html(
        f"""
        <script>
        document.cookie = "{_AUTH_COOKIE_NAME}=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; samesite=lax";
        </script>
        """,
        height=0,
    )


def _restore_auth_from_cookie() -> bool:
    """Восстановить авторизацию из подписанной cookie при перезагрузке страницы."""
    if st is None:
        return False
    if st.session_state.get("authenticated") and st.session_state.get("auth_username"):
        return False
    token = st.context.cookies.get(_AUTH_COOKIE_NAME)
    username = _verify_auth_cookie(token or "")
    if not username:
        return False
    st.session_state["authenticated"] = True
    st.session_state["auth_username"] = username
    return True

def _const_eq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _is_admin(username: str) -> bool:
    u = (username or "").strip()
    return bool(u) and u.lower() == ADMIN_USERNAME.lower()


def _pbkdf2_hash(password: str) -> tuple[str, str]:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return salt.hex(), dk.hex()


def _pbkdf2_verify(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(dk.hex(), hash_hex)


def _load_users_store() -> dict[str, dict]:
    if not USERS_STORE_PATH.exists():
        return {}
    try:
        # utf-8-sig: иначе BOM в начале файла ломает первый ключ в JSON → get("111") не находит запись
        raw = json.loads(USERS_STORE_PATH.read_text(encoding="utf-8-sig"))
        return dict(raw.get("users", {}))
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def _resolve_registered_user(username: str):
    """Одна точка поиска записи пользователя в store (строка, без лишнего «всех сотрудников» при сбое ключа)."""
    u = str(username).strip()
    if not u:
        return None
    store = _load_users_store()
    if u in store:
        return store[u]
    ul = u.lower()
    for k, v in store.items():
        if str(k).strip().lower() == ul:
            return v
    return None


def _save_users_store(users: dict[str, dict]) -> None:
    USERS_STORE_PATH.write_text(
        json.dumps({"users": users}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _credentials_match(user: str, password: str) -> bool:
    u = user.strip()
    if not u or not password:
        return False
    if u.lower() == ADMIN_USERNAME.lower():
        ap = _admin_password()
        if ap and _const_eq(password, ap):
            return True
        return False
    rec = _resolve_registered_user(u)
    if not rec:
        return False
    return _pbkdf2_verify(password, rec.get("salt_hex", ""), rec.get("hash_hex", ""))


def _register_user(username: str, password: str) -> tuple[bool, str]:
    u = username.strip()
    if not _USERNAME_RE.match(u):
        return False, "Логин: 3–32 символа, только латиница, цифры и _"
    if u.lower() == ADMIN_USERNAME.lower():
        return False, "Логин «admin» зарезервирован"
    if len(password) < 8:
        return False, "Пароль не короче 8 символов"
    store = _load_users_store()
    if u in store:
        return False, "Такой логин уже занят"
    salt_hex, hash_hex = _pbkdf2_hash(password)
    store[u] = {
        "salt_hex": salt_hex,
        "hash_hex": hash_hex,
        "created_at": datetime.now(MSK).strftime("%Y-%m-%d %H:%M"),
        "approved": False,
        "display_name": "",
        "email": "",
        "access_scope": "none",
        "allowed_department": "",
        "allowed_area": "",
        "allowed_departments": [],
        "allowed_areas": [],
        "nav_dep_filters": {},
    }
    _save_users_store(store)
    return True, ""


def _approve_registration(username: str) -> tuple[bool, str]:
    """Подтверждение регистрации в ЛК админа: можно входить в приложение."""
    u = (username or "").strip()
    if not u:
        return False, "Пустой логин"
    store = _load_users_store()
    key = None
    if u in store:
        key = u
    else:
        ul = u.lower()
        for k in store:
            if str(k).strip().lower() == ul:
                key = str(k)
                break
    if not key:
        return False, "Пользователь не найден"
    rec = store[key]
    rec["approved"] = True
    rec["approved_at"] = datetime.now(MSK).strftime("%Y-%m-%d %H:%M")
    store[key] = rec
    _save_users_store(store)
    return True, ""


def _update_registered_profile(username: str, display_name: str, email: str) -> tuple[bool, str]:
    store = _load_users_store()
    if username not in store:
        return False, "Профиль не найден"
    rec = store[username]
    rec["display_name"] = display_name.strip()[:200]
    rec["email"] = email.strip()[:200]
    store[username] = rec
    _save_users_store(store)
    return True, ""


def _change_password_registered(username: str, old_pw: str, new_pw: str) -> tuple[bool, str]:
    if len(new_pw) < 8:
        return False, "Новый пароль не короче 8 символов"
    store = _load_users_store()
    if username not in store:
        return False, "Пользователь не найден"
    rec = store[username]
    if not _pbkdf2_verify(old_pw, rec.get("salt_hex", ""), rec.get("hash_hex", "")):
        return False, "Неверный текущий пароль"
    salt_hex, hash_hex = _pbkdf2_hash(new_pw)
    rec["salt_hex"] = salt_hex
    rec["hash_hex"] = hash_hex
    store[username] = rec
    _save_users_store(store)
    return True, ""


def _user_access_scope_value(rec: dict) -> str:
    """Пустая запись или не найден пользователь — нет доступа. Старые записи без access_scope — вся организация."""
    if not rec:
        return "none"
    if "access_scope" not in rec:
        return "all"
    return (rec.get("access_scope") or "none").strip().lower()


def _norm_label(s: object) -> str:
    """Единообразная строка для сравнения (пробелы, неразрывный пробел)."""
    t = str(s if s is not None else "").replace("\u00a0", " ").strip()
    return t


def _cmp_str(s: object) -> str:
    """Сравнение подписей отдела/участка: пробелы, NBSP, регистр (как в БД и в JSON могут отличаться)."""
    t = str(s if s is not None else "").replace("\u00a0", " ").strip()
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def _area_token_set(cell: object) -> set[str]:
    """Токены участка для сравнения по правам и фильтрам СКУД."""
    if pd.isna(cell):
        return set()
    out: set[str] = set()
    for p in str(cell).split(","):
        t = _cmp_str(p)
        if t:
            out.add(t)
    return out


def _area_tokens_from_cell(cell: object) -> set[str]:
    """Участки из ячейки: одно значение или несколько через запятую (как в string_agg из БД)."""
    if pd.isna(cell):
        return set()
    parts: set[str] = set()
    for p in str(cell).split(","):
        t = _norm_label(p)
        if t:
            parts.add(t)
    return parts


def _distinct_area_tokens(series: pd.Series) -> list[str]:
    seen: set[str] = set()
    for v in series:
        for t in _area_tokens_from_cell(v):
            if t not in seen:
                seen.add(t)
    return sorted(seen, key=lambda x: x.lower())


def _allowed_departments_list(rec: dict) -> list[str]:
    """Список разрешённых цехов: новый формат (массив) или старый (одна строка / через запятую)."""
    v = rec.get("allowed_departments")
    if isinstance(v, list):
        return [_norm_label(x) for x in v if _norm_label(x)]
    if isinstance(v, str) and v.strip():
        return [_norm_label(p) for p in v.split(",") if _norm_label(p)]
    s = (rec.get("allowed_department") or "").strip()
    if not s:
        return []
    return [_norm_label(p) for p in s.split(",") if _norm_label(p)]


def _allowed_areas_list(rec: dict) -> list[str]:
    """Список разрешённых участков: массив или старая одна строка."""
    v = rec.get("allowed_areas")
    if isinstance(v, list):
        return [_norm_label(x) for x in v if _norm_label(x)]
    if isinstance(v, str) and v.strip():
        return [_norm_label(p) for p in v.split(",") if _norm_label(p)]
    s = (rec.get("allowed_area") or "").strip()
    if not s:
        return []
    return [_norm_label(p) for p in s.split(",") if _norm_label(p)]


def _mask_rows_by_area_tokens(df: pd.DataFrame, selected_tokens: set[str]) -> pd.Series:
    """Строка подходит, если множество участков сотрудника пересекается с выбранными чекбоксами."""
    if not selected_tokens:
        return pd.Series(False, index=df.index)

    sel_cf = {_cmp_str(x) for x in selected_tokens}

    def _hit(cell: object) -> bool:
        return bool(_area_token_set(cell) & sel_cf)

    return df["area_name"].map(_hit)


def _filter_employees_for_user(full_df: pd.DataFrame, username: str) -> pd.DataFrame:
    """Ограничение списка сотрудников по правам (цех = отдел, участок). Админ — без ограничений."""
    if not username or _is_admin(username):
        return full_df
    rec = _resolve_registered_user(username)
    if rec is None:
        return full_df.iloc[0:0].copy()
    scope = _user_access_scope_value(rec)
    if scope in ("", "none"):
        return full_df.iloc[0:0].copy()
    if scope == "all":
        return full_df
    if scope == "department":
        deps_cf = {_cmp_str(x) for x in _allowed_departments_list(rec)}
        if not deps_cf:
            return full_df.iloc[0:0].copy()
        mask = full_df["department_name"].map(_cmp_str).isin(deps_cf)
        return full_df[mask].copy()
    if scope == "area":
        allowed_cf = {_cmp_str(x) for x in _allowed_areas_list(rec)}
        if not allowed_cf:
            return full_df.iloc[0:0].copy()
        mask = full_df["area_name"].map(lambda c: bool(_area_token_set(c) & allowed_cf))
        return full_df[mask].copy()
    return full_df.iloc[0:0].copy()


# Разделы меню Django (кроме личного кабинета): права в JSON users.*.nav
NAV_KEYS = ("home", "graph", "hours", "skud", "inventory", "defects", "regulations", "products")
NAV_LABELS_RU = {
    "home": "Главная (сводка)",
    "graph": "График",
    "hours": "Часы по дням",
    "skud": "СКУД",
    "inventory": "Склад",
    "defects": "Учёт брака",
    "regulations": "Регламенты",
    "products": "Изделия",
}


def nav_permissions_for_user(username: str | None) -> dict[str, bool]:
    """Какие пункты меню доступны. Админ — всё. Если в store нет nav — все разделы разрешены (обратная совместимость)."""
    defaults = {k: True for k in NAV_KEYS}
    u = (username or "").strip()
    if not u:
        return defaults.copy()
    if _is_admin(u):
        return defaults.copy()
    rec = _resolve_registered_user(u) or {}
    nav = rec.get("nav")
    if not isinstance(nav, dict):
        return defaults.copy()
    out = defaults.copy()
    for k in NAV_KEYS:
        if k in nav:
            out[k] = bool(nav[k])
    return out


def _nav_department_filters_map(rec: dict | None) -> dict[str, list[str]]:
    """Пер-разделные ограничения по отделам: users.*.nav_dep_filters {graph:[...], ...}.

    Пустой список для ключа раздела означает «ни один отдел не разрешён» (пустой список сотрудников).
    Если ключа раздела в JSON нет — фильтр не задан (обратная совместимость: все отделы).
    """
    if not rec or not isinstance(rec.get("nav_dep_filters"), dict):
        return {}
    raw = rec.get("nav_dep_filters") or {}
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        key = str(k or "").strip()
        if key not in NAV_KEYS:
            continue
        if isinstance(v, list):
            vals = [_norm_label(x) for x in v if _norm_label(x)]
        elif isinstance(v, str) and v.strip():
            vals = [_norm_label(p) for p in v.split(",") if _norm_label(p)]
        else:
            vals = []
        out[key] = vals
    return out


def employees_df_for_nav(username: str | None, nav_key: str, employees_df: pd.DataFrame) -> pd.DataFrame:
    """Список сотрудников для конкретного раздела: базовые права + (опционально) фильтр по отделам для раздела."""
    if employees_df is None or getattr(employees_df, "empty", True):
        return employees_df
    u = (username or "").strip()
    if not u or _is_admin(u):
        return employees_df
    rec = _resolve_registered_user(u)
    if rec is None:
        return employees_df.iloc[0:0].copy()
    # В Django-интерфейсе доступ к сотрудникам в разделах задаётся через nav_dep_filters.
    # Глобальный access_scope оставляем для Streamlit/обратной совместимости, но здесь не сужаем базу по нему.
    base = employees_df
    nk = (nav_key or "").strip()
    if nk == "products":
        return employees_df
    filt = _nav_department_filters_map(rec).get(nk)
    if filt is None:
        return base
    if not filt:
        return base.iloc[0:0].copy()
    if base.empty:
        return base
    allow = {_cmp_str(x) for x in filt}
    mask = base["department_name"].map(_cmp_str).isin(allow)
    return base[mask].copy()


def _access_scope_description(rec: dict) -> str:
    scope = _user_access_scope_value(rec)
    nd = _nav_department_filters_map(rec or {})
    if nd:
        keys = ", ".join(NAV_LABELS_RU.get(k, k) for k in sorted(nd.keys()))
        return f"Фильтр по отделам настроен для разделов: {keys}"
    if scope in ("none", ""):
        return "Нет доступа к данным — администратор ещё не назначил права"
    if scope == "department":
        parts = _allowed_departments_list(rec)
        d = ", ".join(parts) if parts else "—"
        return f"Только выбранные цехи (отделы): {d}"
    if scope == "area":
        parts = _allowed_areas_list(rec)
        a = ", ".join(parts) if parts else "—"
        return f"Только выбранные участки: {a}"
    return "Вся организация"


def _set_user_privileges(
    target_username: str,
    scope: str | None,
    allowed_departments,
    allowed_areas,
    *,
    nav: dict[str, bool] | None = None,
    nav_dep_filters: dict[str, list[str]] | None = None,
) -> tuple[bool, str]:
    if scope is not None and str(scope).strip() not in ("none", "all", "department", "area"):
        return False, "Неверный тип доступа"
    store = _load_users_store()
    if target_username not in store:
        return False, "Пользователь не найден"
    rec = store[target_username]
    if scope is not None:
        scope = str(scope).strip()
        rec["access_scope"] = scope
        deps = [_norm_label(x) for x in (allowed_departments or []) if _norm_label(x)]
        ars = [_norm_label(x) for x in (allowed_areas or []) if _norm_label(x)]
        rec["allowed_departments"] = deps if scope == "department" else []
        rec["allowed_areas"] = ars if scope == "area" else []
        rec["allowed_department"] = ""
        rec["allowed_area"] = ""
    if nav is not None:
        merged_nav = {k: bool(nav.get(k, True)) for k in NAV_KEYS}
        rec["nav"] = merged_nav
    if nav_dep_filters is not None:
        cleaned: dict[str, list[str]] = {}
        for k, vals in (nav_dep_filters or {}).items():
            key = str(k or "").strip()
            if key not in NAV_KEYS:
                continue
            if not isinstance(vals, list):
                continue
            uniq = []
            seen = set()
            for x in vals:
                t = _norm_label(x)
                if not t:
                    continue
                cf = _cmp_str(t)
                if cf in seen:
                    continue
                seen.add(cf)
                uniq.append(t)
            cleaned[key] = uniq
        current_nav = rec.get("nav")
        if not isinstance(current_nav, dict):
            current_nav = {nk: True for nk in NAV_KEYS}
        rec["nav_dep_filters"] = {
            k: v
            for k, v in cleaned.items()
            if k in NAV_KEYS and bool(current_nav.get(k, True))
        }
    store[target_username] = rec
    _save_users_store(store)
    return True, ""


def _cabinet_display_name(username: str) -> str:
    if not username:
        return "—"
    if _is_admin(username):
        if st is not None:
            return st.session_state.get("admin_display_name", "").strip() or username
        return username
    rec = _resolve_registered_user(username) or {}
    return (rec.get("display_name") or "").strip() or username


def _render_personal_cabinet_page(employees_full: pd.DataFrame) -> None:
    """Профиль и (для admin) права пользователей — отдельная страница."""
    if st is None:
        raise RuntimeError("Личный кабинет доступен только в Streamlit")
    _user = st.session_state.get("auth_username", "")
    if _is_admin(_user):
        st.write(f"**Логин:** `{ADMIN_USERNAME}`")
        st.caption("Роль: **администратор**")
        st.info("Пароль этой учётки задаётся в коде приложения.")
        _cur_adn = st.session_state.get("admin_display_name", "")
        adn = st.text_input(
            "Имя для отображения",
            value=_cur_adn,
            key="cabinet_lk_admin_display",
            help="Сохраняется в сессии до выхода.",
        )
        if st.button("Сохранить имя", key="cabinet_lk_btn_admin_dn"):
            st.session_state["admin_display_name"] = adn.strip()
            st.success("Имя обновлено")
            st.rerun()
        with st.expander("Права пользователей", expanded=False):
            st.caption(
                "Новые аккаунты по умолчанию **без доступа** к сотрудникам, пока администратор не назначит права."
            )
            _priv_store = _load_users_store()
            if not _priv_store:
                st.info("Пока нет зарегистрированных пользователей.")
            else:
                with st.form("cabinet_admin_privileges_form"):
                    _priv_user = st.selectbox(
                        "Пользователь",
                        options=sorted(_priv_store.keys()),
                        key="cabinet_admin_priv_user_select",
                    )
                    _pr = _priv_store.get(_priv_user, {})
                    _scope_options = ["none", "all", "department", "area"]
                    _psc = _user_access_scope_value(_pr)
                    if _psc not in _scope_options:
                        _psc = "none"
                    _scope_labels = {
                        "none": "Нет доступа",
                        "all": "Вся организация",
                        "department": "Только выбранные цехи (отделы)",
                        "area": "Только выбранные участки",
                    }
                    _priv_scope = st.selectbox(
                        "Видимость сотрудников",
                        options=_scope_options,
                        index=_scope_options.index(_psc),
                        format_func=lambda x: _scope_labels[x],
                        key="cabinet_admin_priv_scope_field",
                    )
                    _dep_opts = sorted(employees_full["department_name"].unique().tolist()) if not employees_full.empty else []
                    _area_opts = _distinct_area_tokens(employees_full["area_name"]) if not employees_full.empty else []
                    _default_deps = [x for x in _allowed_departments_list(_pr) if x in _dep_opts]
                    _default_areas = [x for x in _allowed_areas_list(_pr) if x in _area_opts]
                    st.caption(
                        "При ограничении по цеху или участку отметьте **один или несколько** пунктов (удерживайте Ctrl для множественного выбора)."
                    )
                    if _dep_opts:
                        _priv_dep = st.multiselect(
                            "Цехи (отделы)",
                            options=_dep_opts,
                            default=_default_deps,
                            key="cabinet_admin_priv_dep_ms",
                            disabled=_priv_scope != "department",
                            help="Видны сотрудники, чей цех входит в список.",
                        )
                    else:
                        st.caption("Нет цехов в справочнике.")
                        _priv_dep = []
                    if _area_opts:
                        _priv_area = st.multiselect(
                            "Участки",
                            options=_area_opts,
                            default=_default_areas,
                            key="cabinet_admin_priv_area_ms",
                            disabled=_priv_scope != "area",
                            help="Видны сотрудники, у которых есть хотя бы один из отмеченных участков.",
                        )
                    else:
                        st.caption("Нет участков в справочнике.")
                        _priv_area = []
                    if st.form_submit_button("Сохранить права", use_container_width=True):
                        _dep_list = list(_priv_dep) if _priv_scope == "department" else []
                        _area_list = list(_priv_area) if _priv_scope == "area" else []
                        _ok_p, _err_p = _set_user_privileges(
                            _priv_user, _priv_scope, _dep_list, _area_list
                        )
                        if _ok_p:
                            st.success("Права сохранены. Обновите страницу (F5).")
                        else:
                            st.error(_err_p)
    else:
        _rec = _resolve_registered_user(_user) or {}
        if not _rec:
            st.error("Данные профиля не найдены.")
        else:
            st.write(f"**Логин:** `{_user}`")
            st.caption("Роль: **пользователь**")
            _ca = _rec.get("created_at") or "—"
            st.caption(f"Регистрация: {_ca}")
            st.caption(f"**Доступ:** {_access_scope_description(_rec)}")
            with st.form("cabinet_lk_profile_form"):
                f_dn = st.text_input(
                    "Отображаемое имя",
                    value=_rec.get("display_name") or "",
                    max_chars=200,
                    key="cabinet_lk_dn",
                )
                f_em = st.text_input(
                    "Email",
                    value=_rec.get("email") or "",
                    max_chars=200,
                    key="cabinet_lk_em",
                )
                if st.form_submit_button("Сохранить профиль", use_container_width=True):
                    ok, err = _update_registered_profile(_user, f_dn, f_em)
                    if ok:
                        st.success("Профиль сохранён")
                        st.rerun()
                    else:
                        st.error(err)
            with st.form("cabinet_lk_password_form"):
                p_old = st.text_input("Текущий пароль", type="password", key="cabinet_lk_p_old")
                p_new = st.text_input("Новый пароль", type="password", key="cabinet_lk_p_new")
                p_new2 = st.text_input("Новый пароль ещё раз", type="password", key="cabinet_lk_p_new2")
                if st.form_submit_button("Сменить пароль", use_container_width=True):
                    if p_new != p_new2:
                        st.error("Новые пароли не совпадают")
                    else:
                        ok, err = _change_password_registered(_user, p_old, p_new)
                        if ok:
                            st.success("Пароль обновлён")
                            st.rerun()
                        else:
                            st.error(err)


def _render_auth_page() -> None:
    if st is None:
        raise RuntimeError("Страница входа доступна только в Streamlit")
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.title("Biota shifts")
        tab_in, tab_reg = st.tabs(["Вход", "Регистрация"])
        with tab_in:
            st.caption("Войдите под своим логином или учётной записью admin")
            if not _admin_password():
                st.info(
                    "Вход **admin** отключён, пока не задан пароль: переменная **BIOTA_ADMIN_PASSWORD** "
                    "или ключ **BIOTA_ADMIN_PASSWORD** в `.streamlit/secrets.toml` (см. `secrets.toml.example`). "
                    "Можно войти под зарегистрированным пользователем."
                )
            with st.form("biota_login_form", clear_on_submit=False):
                username = st.text_input("Логин", key="auth_login_user", autocomplete="username")
                pwd = st.text_input(
                    "Пароль", type="password", key="auth_login_pass", autocomplete="current-password"
                )
                submitted = st.form_submit_button("Войти", type="primary", use_container_width=True)
            if submitted:
                u_in = username.strip()
                if _credentials_match(username, pwd):
                    if not _is_admin(u_in):
                        rec = _resolve_registered_user(u_in)
                        if not rec or not rec.get("approved", True):
                            st.error(
                                "Учётная запись ожидает подтверждения администратором. "
                                "После подтверждения в веб-ЛК вы сможете войти."
                            )
                        else:
                            st.session_state["authenticated"] = True
                            st.session_state["auth_username"] = u_in
                            _set_auth_cookie(st.session_state["auth_username"])
                            st.rerun()
                    else:
                        st.session_state["authenticated"] = True
                        st.session_state["auth_username"] = ADMIN_USERNAME
                        _set_auth_cookie(st.session_state["auth_username"])
                        st.rerun()
                else:
                    st.error("Неверный логин или пароль")
        with tab_reg:
            st.caption("Создайте логин и пароль для доступа к приложению")
            with st.form("biota_register_form", clear_on_submit=False):
                reg_user = st.text_input("Новый логин", key="auth_reg_user", autocomplete="username")
                reg_p1 = st.text_input("Пароль", type="password", key="auth_reg_p1")
                reg_p2 = st.text_input("Пароль ещё раз", type="password", key="auth_reg_p2")
                reg_btn = st.form_submit_button("Зарегистрироваться", type="primary", use_container_width=True)
            if reg_btn:
                if reg_p1 != reg_p2:
                    st.error("Пароли не совпадают")
                else:
                    ok, err = _register_user(reg_user, reg_p1)
                    if ok:
                        st.success(
                            "Регистрация принята. Вход будет возможен после подтверждения администратором в веб-личном кабинете."
                        )
                    else:
                        st.error(err)

