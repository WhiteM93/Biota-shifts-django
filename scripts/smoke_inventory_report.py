"""Smoke-проверка страниц склада для отчёта."""
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "biota_site.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

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
    ok = r.status_code == 200
    print(f"  {cat}: HTTP {r.status_code}, items={n}, ok={ok}")

r = c.get("/inventory/?panel=arrival")
print(
    f"arrival: HTTP {r.status_code}, "
    f"grades={b'insert_chipbreaker_grades' in r.content}, "
    f"no_wm_types={b'work_material_types' not in r.content}"
)
