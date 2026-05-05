"""Подгрузка .env из корня репозитория (рядом с manage.py), без зависимости от Django."""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def load_repo_env() -> None:
    """Заполняет os.environ из `<repo>/.env` и `<repo>/.env.secrets` (как в Django)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env", override=True)
    load_dotenv(_REPO_ROOT / ".env.secrets", override=True)


def repo_root() -> Path:
    return _REPO_ROOT
