"""Пути, secrets, каталог графиков."""
import os
import re
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
APP_DIR = PACKAGE_DIR.parent

from .env_manual import load_env_file

load_env_file(APP_DIR / ".env")
load_env_file(APP_DIR / ".env.secrets")
try:
    from dotenv import load_dotenv

    load_dotenv(APP_DIR / ".env", override=True)
    load_dotenv(APP_DIR / ".env.secrets", override=True)
except ImportError:
    pass


def _config_str(key: str, default: str = "") -> str:
    """Переменные из окружения или Django settings (без Streamlit)."""
    env_v = (os.getenv(key) or "").strip()
    if env_v:
        return env_v
    try:
        from django.conf import settings

        v = getattr(settings, key, None)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    except Exception:
        pass
    return (default or "").strip()


def _profile_env(prefix: str, key: str, default: str = "") -> str:
    """Вернуть значение с учётом активного профиля (например BIOTA_DB_PROD_HOST)."""
    profile = (os.getenv(f"{prefix}_PROFILE") or "").strip().upper()
    if profile:
        profile_key = f"{prefix}_{profile}_{key}"
        profile_val = (os.getenv(profile_key) or "").strip()
        if profile_val:
            return profile_val
    return _config_str(f"{prefix}_{key}", default)


def biota_db_env(key: str, default: str = "") -> str:
    """Переменные подключения к Biota DB с optional profile switch."""
    return _profile_env("BIOTA_DB", key, default)


def _schedule_dir() -> Path:
    """Папка с Excel графиками: env BIOTA_SCHEDULE_DIR или ./schedules рядом с app.py."""
    override = (os.getenv("BIOTA_SCHEDULE_DIR") or "").strip()
    p = Path(override) if override else (APP_DIR / "schedules")
    p.mkdir(parents=True, exist_ok=True)
    return p


SCHEDULE_DIR = _schedule_dir()

ADMIN_USERNAME = _config_str("BIOTA_ADMIN_USERNAME", "admin") or "admin"
_users_env = (os.getenv("BIOTA_USERS_STORE") or "").strip()
USERS_STORE_PATH = Path(_users_env) if _users_env else (APP_DIR / ".biota_users.json")
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def _admin_password() -> str:
    return _config_str("BIOTA_ADMIN_PASSWORD", "")
