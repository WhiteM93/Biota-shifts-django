#!/bin/bash
# Включает HTTP/2 для HTTPS в конфиге сайта (nginx 1.24: параметр http2 в listen).
# Запуск на сервере: sudo bash scripts/apply_nginx_http2.sh
set -euo pipefail

SITE_CONF=/etc/nginx/sites-available/biota
TS=$(date +%Y%m%d_%H%M%S)
BACKUP="${SITE_CONF}.bak.${TS}"

cp -a "$SITE_CONF" "$BACKUP"
echo "backup: $BACKUP"

python3 - "$SITE_CONF" <<'PY'
import re
import sys
from pathlib import Path

site = Path(sys.argv[1])
text = site.read_text(encoding="utf-8")

listen_re = re.compile(r"^([ \t]*listen[ \t]+[^;\n]*\b443\b[^;\n]*?\bssl\b)([^;\n]*;)", re.M)
changed = 0


def add_http2(m: re.Match) -> str:
    global changed
    if re.search(r"\bhttp2\b", m.group(0)):
        return m.group(0)
    changed += 1
    return f"{m.group(1)} http2{m.group(2)}"


text2 = listen_re.sub(add_http2, text)
found = len(listen_re.findall(text))
if found == 0:
    raise SystemExit("listen 443 ssl not found in site config")
if changed == 0:
    print("http2 already enabled, nothing to change")
else:
    site.write_text(text2, encoding="utf-8")
    print(f"listen lines updated: {changed}")
PY

if ! nginx -t; then
    echo "nginx -t failed, restoring backup"
    cp -a "$BACKUP" "$SITE_CONF"
    nginx -t
    exit 1
fi

systemctl reload nginx
echo "OK: nginx reloaded"
grep -n "listen" "$SITE_CONF"
