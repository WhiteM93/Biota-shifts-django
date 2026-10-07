"""Журнал подозрительных и успешных попыток регистрации для ЛК админа."""

from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from biota_shifts.config import APP_DIR
from biota_shifts.constants import MSK

LOG_PATH = APP_DIR / ".biota_register_security.jsonl"
_MAX_EVENTS = 3000
_lock = threading.Lock()

REASON_LABELS: dict[str, str] = {
    "closed": "Регистрация закрыта",
    "honeypot": "Honeypot (бот заполнил скрытое поле)",
    "timing": "Слишком быстро / устаревшая форма",
    "invite": "Неверный код приглашения",
    "disposable": "Одноразовый email",
    "password_mismatch": "Пароли не совпали",
    "register_fail": "Отказ регистрации (логин/email)",
    "success": "Учётка создана (ждёт одобрения)",
    "rate_limit": "Rate limit (слишком много запросов)",
    "rate_limit_burst": "Rate limit: частые запросы",
    "rate_limit_post": "Rate limit: много POST с IP",
    "rate_limit_global": "Rate limit: дневной потолок сайта",
}

BLOCKED_REASONS = frozenset(
    {
        "closed",
        "honeypot",
        "timing",
        "invite",
        "disposable",
        "rate_limit",
        "rate_limit_burst",
        "rate_limit_post",
        "rate_limit_global",
    }
)


def _now() -> datetime:
    return datetime.now(MSK)


def email_domain(email: str) -> str:
    em = (email or "").strip().casefold()
    if "@" not in em:
        return ""
    return em.rsplit("@", 1)[-1].strip()[:120]


def append_register_event(
    *,
    reason: str,
    ip: str = "",
    username: str = "",
    email: str = "",
    detail: str = "",
    user_agent: str = "",
    method: str = "POST",
) -> None:
    reason = (reason or "unknown").strip()[:64]
    event = {
        "ts": _now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": reason,
        "ip": (ip or "")[:80],
        "username": (username or "").strip()[:64],
        "email_domain": email_domain(email),
        "detail": (detail or "").strip()[:200],
        "ua": (user_agent or "").strip()[:160],
        "method": (method or "POST").upper()[:8],
    }
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with _lock:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line)
            _maybe_trim_unlocked()
        except OSError:
            pass


def _maybe_trim_unlocked() -> None:
    try:
        if not LOG_PATH.exists() or LOG_PATH.stat().st_size < 400_000:
            return
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _MAX_EVENTS:
            return
        LOG_PATH.write_text("\n".join(lines[-_MAX_EVENTS:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_register_events(*, limit: int = 500) -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    try:
        raw = LOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    if limit > 0:
        out = out[-limit:]
    out.reverse()  # newest first
    return out


def clear_register_security_log() -> bool:
    with _lock:
        try:
            if LOG_PATH.exists():
                LOG_PATH.unlink()
            return True
        except OSError:
            return False


def _parse_ts(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def build_register_attack_dashboard(
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = events if events is not None else load_register_events(limit=2000)
    now = _now().replace(tzinfo=None)
    windows = {
        "1h": now - timedelta(hours=1),
        "24h": now - timedelta(hours=24),
        "7d": now - timedelta(days=7),
    }
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in windows}

    for ev in rows:
        ts = _parse_ts(str(ev.get("ts") or ""))
        if ts is None:
            continue
        for key, start in windows.items():
            if ts >= start:
                buckets[key].append(ev)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        by_reason: Counter[str] = Counter()
        by_ip: Counter[str] = Counter()
        blocked = 0
        success = 0
        for ev in items:
            reason = str(ev.get("reason") or "unknown")
            by_reason[reason] += 1
            ip = str(ev.get("ip") or "").strip() or "—"
            if reason in BLOCKED_REASONS or reason.startswith("rate_limit"):
                blocked += 1
                by_ip[ip] += 1
            if reason == "success":
                success += 1
        reason_rows = [
            {
                "reason": r,
                "label": REASON_LABELS.get(r, r),
                "count": c,
            }
            for r, c in by_reason.most_common()
        ]
        top_ips = [{"ip": ip, "count": c} for ip, c in by_ip.most_common(8)]
        return {
            "total": len(items),
            "blocked": blocked,
            "success": success,
            "by_reason": reason_rows,
            "top_ips": top_ips,
        }

    recent = []
    for ev in rows[:40]:
        reason = str(ev.get("reason") or "")
        recent.append(
            {
                "ts": ev.get("ts") or "",
                "ip": ev.get("ip") or "—",
                "reason": reason,
                "label": REASON_LABELS.get(reason, reason),
                "username": ev.get("username") or "",
                "email_domain": ev.get("email_domain") or "",
                "detail": ev.get("detail") or "",
                "method": ev.get("method") or "",
                "is_blocked": reason in BLOCKED_REASONS or reason.startswith("rate_limit"),
            }
        )

    s1h = summarize(buckets["1h"])
    alert = s1h["blocked"] >= 10
    return {
        "alert": alert,
        "alert_text": (
            f"За последний час заблокировано попыток: {s1h['blocked']}. Возможна атака ботов."
            if alert
            else ""
        ),
        "stats_1h": s1h,
        "stats_24h": summarize(buckets["24h"]),
        "stats_7d": summarize(buckets["7d"]),
        "recent": recent,
        "log_exists": LOG_PATH.exists(),
    }
