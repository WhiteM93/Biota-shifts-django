# FastAPI-слой (опционально)

Отдельный сервис, **не подключён** к `biota_site` и не меняет Django. Если не понравится — удалите каталог или откатите ветку.

## Запуск локально

Из **корня репозитория** (`Biota-shifts-django/`):

```bash
python -m venv .venv-api
.venv-api\Scripts\activate
pip install -r api_fastapi/requirements.txt
uvicorn api_fastapi.main:app --reload --port 8001
```

Подхватываются те же **`../.env`** и **`../.env.secrets`**, что и у Django (`BIOTA_DB_*`, профиль `BIOTA_DB_PROFILE`).

## Endpoints

| Метод | Путь | Описание |
|--------|------|----------|
| GET | `/health` | Liveness без БД |
| GET | `/biota/ping` | `SELECT 1` в PostgreSQL Biota |
| GET | `/biota/employees/sample?limit=5` | Пример read-only выборки |

Документация Swagger: `http://127.0.0.1:8001/docs`

## CORS (по желанию)

Переменная `API_CORS_ORIGINS` — список через запятую, например:

`API_CORS_ORIGINS=http://localhost:3000,https://app.example.com`

## Git

Удобно держать изменения в отдельной ветке, например `feature/fastapi-sidecar`.
