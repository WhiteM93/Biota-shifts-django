"""Smoke-проверка страниц склада для отчёта."""
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "biota_site.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.db.models import Count
from django.test import Client

from shifts.models import ToolItem

PREFIX = "ОТЧЁТ"
c = Client()
session = c.session
session["biota_username"] = "admin"
session.save()

cats = ["end_mill", "tap", "center_drill", "countersink", "drill", "insert"]
print("=== Smoke: страницы склада ===")
for cat in cats:
    r = c.get(f"/inventory/?panel=stock&category={cat}")
    n = ToolItem.objects.filter(category=cat, name__startswith=PREFIX).count()
    ok = r.status_code == 200 and b"wm-badge" in r.content
    print(f"  {cat}: HTTP {r.status_code}, items={n}, wm-badge={ok}")

r = c.get("/inventory/?panel=arrival")
print(
    f"arrival: HTTP {r.status_code}, "
    f"multi-picker={b'arrival-wm-multi-picker' in r.content}, "
    f"grades={b'insert_chipbreaker_grades' in r.content}"
)

r = c.get("/inventory/?panel=stock&category=drill&work_material=P")
ids = list(
    ToolItem.objects.filter(name__startswith=PREFIX, category="drill")
    .exclude(work_material="")
    .values_list("id", "work_material")
)
body = r.content.decode("utf-8", errors="replace")
with_p = [i for i, wm in ids if "P" in (wm or "").split(",")]
found = sum(1 for i in with_p if f'value="{i}"' in body)
print(f"filter P: drill with P in WM={len(with_p)}, shown in table={found}")
