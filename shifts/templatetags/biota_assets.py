"""{% asset 'path' %} — URL статики с версией по содержимому файла.

Версия меняется только у изменённых файлов, поэтому после выкладки браузер
не перекачивает остальную статику. Подключён как builtin (см. TEMPLATES).
"""

from __future__ import annotations

import hashlib
import os
import threading

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

_cache: dict[str, tuple[int, int, str]] = {}
_lock = threading.Lock()


def _source_path(path: str) -> str | None:
    root = getattr(settings, "STATIC_ROOT", None)
    collected = os.path.join(str(root), path) if root else None
    if not settings.DEBUG and collected and os.path.isfile(collected):
        return collected
    found = finders.find(path)
    if isinstance(found, (list, tuple)):
        found = found[0] if found else None
    if found:
        return found
    if collected and os.path.isfile(collected):
        return collected
    return None


def asset_version(path: str) -> str:
    fallback = str(getattr(settings, "STATIC_ASSET_VERSION", "1"))
    src = _source_path(path)
    if not src:
        return fallback
    try:
        st = os.stat(src)
    except OSError:
        return fallback
    cached = _cache.get(path)
    if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return cached[2]
    h = hashlib.md5(usedforsecurity=False)
    try:
        with open(src, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return fallback
    ver = h.hexdigest()[:10]
    with _lock:
        _cache[path] = (st.st_mtime_ns, st.st_size, ver)
    return ver


@register.simple_tag
def asset(path: str) -> str:
    return f"{static(path)}?v={asset_version(path)}"
