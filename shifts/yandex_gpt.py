"""Клиент Yandex Cloud Foundation Models (YandexGPT)."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

YANDEX_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexGptError(Exception):
    """Ошибка конфигурации или вызова YandexGPT."""


def yandex_gpt_configured() -> bool:
    return bool(
        (getattr(settings, "YANDEX_GPT_API_KEY", "") or "").strip()
        and (getattr(settings, "YANDEX_GPT_FOLDER_ID", "") or "").strip()
    )


def yandex_gpt_model_uri() -> str:
    folder = (getattr(settings, "YANDEX_GPT_FOLDER_ID", "") or "").strip()
    model = (getattr(settings, "YANDEX_GPT_MODEL", "") or "yandexgpt-lite").strip() or "yandexgpt-lite"
    if model.startswith("gpt://"):
        return model
    return f"gpt://{folder}/{model}/latest"


def complete(
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> str:
    """Синхронный completion. messages: [{role, text}, ...]."""
    if not yandex_gpt_configured():
        raise YandexGptError("Чат не настроен: задайте YANDEX_GPT_API_KEY и YANDEX_GPT_FOLDER_ID.")

    api_key = (settings.YANDEX_GPT_API_KEY or "").strip()
    folder_id = (settings.YANDEX_GPT_FOLDER_ID or "").strip()
    temp = temperature if temperature is not None else float(getattr(settings, "YANDEX_GPT_TEMPERATURE", 0.1))
    tokens = max_tokens if max_tokens is not None else int(getattr(settings, "YANDEX_GPT_MAX_TOKENS", 1200) or 1200)
    wait = timeout if timeout is not None else float(getattr(settings, "YANDEX_GPT_TIMEOUT", 45) or 45)

    body: dict[str, Any] = {
        "modelUri": yandex_gpt_model_uri(),
        "completionOptions": {
            "stream": False,
            "temperature": temp,
            "maxTokens": str(tokens),
        },
        "messages": [{"role": m["role"], "text": m["text"]} for m in messages],
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        YANDEX_COMPLETION_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=wait) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        logger.warning("YandexGPT HTTP %s: %s", exc.code, detail)
        msg = f"YandexGPT вернул ошибку {exc.code}."
        try:
            err_obj = json.loads(detail) if detail else {}
            api_msg = (err_obj.get("error") or {}).get("message") or ""
            if api_msg:
                msg = f"YandexGPT: {api_msg}"
        except Exception:
            pass
        raise YandexGptError(msg) from exc
    except urllib.error.URLError as exc:
        logger.warning("YandexGPT network error: %s", exc)
        raise YandexGptError("Не удалось связаться с YandexGPT.") from exc
    except TimeoutError as exc:
        raise YandexGptError("Таймаут запроса к YandexGPT.") from exc

    try:
        alts = payload["result"]["alternatives"]
        text = (alts[0]["message"]["text"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("YandexGPT unexpected payload: %s", payload)
        raise YandexGptError("Неожиданный ответ YandexGPT.") from exc
    if not text:
        raise YandexGptError("Пустой ответ YandexGPT.")
    return text
