"""
Экспериментальный API рядом с Django. Запуск из корня репозитория:

    pip install -r api_fastapi/requirements.txt
    uvicorn api_fastapi.main:app --reload --port 8001

Удаление: папка `api_fastapi/` + ветка Git — основной проект не трогался.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_fastapi.env_load import load_repo_env
from api_fastapi.routers import biota, health

load_repo_env()

app = FastAPI(
    title="Biota API (FastAPI)",
    version="0.1.0",
    description="Опциональный REST-слой. Не используется основным Django-приложением.",
)

_origins = [o.strip() for o in (os.getenv("API_CORS_ORIGINS") or "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(biota.router)
