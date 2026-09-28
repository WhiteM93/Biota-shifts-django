from unittest.mock import patch
import json

from django.test import Client, TestCase
from django.urls import reverse

from shifts.forms_ai import extract_json_object
from shifts.models import PrintForm


class FormsAiLayoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.form = PrintForm.objects.create(
            name="Черновик",
            created_by="admin",
            elements=[{"id": "el-old", "type": "text", "text": "старое", "page": 0, "height_px": 0}],
        )

    def test_extract_json_from_fence(self):
        raw = '```json\n{"elements":[{"type":"heading","text":"Регламент"}]}\n```'
        data = extract_json_object(raw)
        self.assertEqual(data["elements"][0]["text"], "Регламент")

    def test_layout_replaces_elements(self):
        payload = {
            "elements": [
                {"type": "heading", "text": "Обход", "align": "center", "font_size": 18},
                {"type": "checkbox", "label": "Проверить уровень", "checked": False},
            ]
        }
        with patch("shifts.forms_ai.yandex_gpt_configured", return_value=True), patch(
            "shifts.forms_ai.complete", return_value=json.dumps(payload, ensure_ascii=False)
        ):
            res = self.client.post(
                reverse("forms_api_layout", args=[self.form.pk]),
                data='{"source":"чек лист: проверить уровень","instruction":"галочки"}',
                content_type="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        types = [el["type"] for el in body["form"]["elements"]]
        self.assertEqual(types, ["heading", "checkbox"])
        self.assertEqual(body["form"]["elements"][0]["text"], "Обход")
        self.form.refresh_from_db()
        self.assertEqual(len(self.form.elements), 2)

    def test_layout_requires_source(self):
        with patch("shifts.forms_ai.yandex_gpt_configured", return_value=True):
            res = self.client.post(
                reverse("forms_api_layout", args=[self.form.pk]),
                data='{"source":"  "}',
                content_type="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(res.status_code, 400)
