#!/bin/bash
set -euo pipefail

NGINX_CONF=/etc/nginx/nginx.conf
SITE_CONF=/etc/nginx/sites-available/biota
TS=$(date +%Y%m%d_%H%M%S)

cp -a "$NGINX_CONF" "${NGINX_CONF}.bak.${TS}"
cp -a "$SITE_CONF" "${SITE_CONF}.bak.${TS}"

python3 - <<'PY'
from pathlib import Path
import re

nginx = Path("/etc/nginx/nginx.conf")
text = nginx.read_text(encoding="utf-8")

new_gzip = """
        ##
        # Gzip Settings
        ##

        gzip on;
        gzip_vary on;
        gzip_proxied any;
        gzip_comp_level 5;
        gzip_min_length 256;
        gzip_types
            text/plain
            text/css
            text/xml
            text/javascript
            application/javascript
            application/x-javascript
            application/json
            application/xml
            application/xml+rss
            application/xhtml+xml
            application/vnd.ms-fontobject
            font/woff
            font/woff2
            image/svg+xml;
"""

pattern = re.compile(
    r"\n[ \t]*##\n[ \t]*# Gzip Settings\n[ \t]*##\n(?:[ \t]*.*\n)*?(?=\n[ \t]*##\n[ \t]*# Virtual Host Configs)",
    re.M,
)
if not pattern.search(text):
    raise SystemExit("gzip section not found in nginx.conf")
text2 = pattern.sub("\n" + new_gzip.rstrip() + "\n", text, count=1)
nginx.write_text(text2, encoding="utf-8")

site = Path("/etc/nginx/sites-available/biota")
st = site.read_text(encoding="utf-8")
old = """    location /static/ {
        alias /home/admin/Biota-shifts-django/staticfiles/;
    }"""
new = """    location /static/ {
        alias /home/admin/Biota-shifts-django/staticfiles/;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
        try_files $uri =404;
    }"""
count = st.count(old)
if count < 1:
    alt = re.compile(
        r"location /static/\s*\{\s*alias /home/admin/Biota-shifts-django/staticfiles/;\s*\}",
        re.M,
    )
    st2, n = alt.subn(
        'location /static/ {\n'
        '        alias /home/admin/Biota-shifts-django/staticfiles/;\n'
        '        access_log off;\n'
        '        expires 30d;\n'
        '        add_header Cache-Control "public, max-age=2592000";\n'
        '        try_files $uri =404;\n'
        '    }',
        st,
    )
    if n < 1:
        raise SystemExit("location /static/ not found/unrecognized in biota site config")
else:
    st2 = st.replace(old, new)
    n = count
print(f"updated static locations: {n}")
site.write_text(st2, encoding="utf-8")
print("configs patched")
PY

nginx -t
systemctl reload nginx
echo "OK: nginx reloaded"
