"""Фото содержимого контейнеров визуального склада."""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from shifts.models import VisualCabinet, VisualContainer, VisualContainerPhoto


class VisualWarehouseContainerPhotoTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["biota_username"] = "admin"
        session.save()
        self.cab = VisualCabinet.objects.create(name="Шкаф", shelves=2, columns=2)
        self.cont = VisualContainer.objects.create(
            cabinet=self.cab,
            shelf=1,
            stack=1,
            column=1,
            label="Ящик 1",
        )
        self.photos_url = reverse("visual_warehouse_api_container_photos", kwargs={"pk": self.cont.pk})

    def _tiny_png(self, name="box.png"):
        data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return SimpleUploadedFile(name, data, content_type="image/png")

    def test_upload_sets_today_date(self):
        today = timezone.localdate()
        res = self.client.post(self.photos_url, {"image": self._tiny_png()})
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        photo = VisualContainerPhoto.objects.get(container=self.cont)
        self.assertEqual(photo.photo_date, today)
        cont = body.get("container") or {}
        self.assertEqual(cont.get("photos_count"), 1)
        self.assertEqual(len(body.get("photos") or []), 1)

    def test_second_upload_replaces_first(self):
        first = self.client.post(self.photos_url, {"image": self._tiny_png("first.png")})
        self.assertEqual(first.status_code, 200, first.content[:500])
        first_id = first.json()["photo"]["id"]
        second = self.client.post(self.photos_url, {"image": self._tiny_png("second.png")})
        self.assertEqual(second.status_code, 200, second.content[:500])
        self.assertEqual(VisualContainerPhoto.objects.filter(container=self.cont).count(), 1)
        self.assertFalse(VisualContainerPhoto.objects.filter(pk=first_id).exists())
        self.assertEqual(len(second.json().get("photos") or []), 1)

    def test_list_photos(self):
        VisualContainerPhoto.objects.create(
            container=self.cont,
            image=self._tiny_png(),
            photo_date=date(2026, 8, 1),
            uploaded_by="admin",
        )
        res = self.client.get(self.photos_url)
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(len(body.get("photos") or []), 1)
        self.assertEqual(body["container"]["content_photo_date"], "01.08.2026")

    def test_delete_photo_updates_summary(self):
        photo = VisualContainerPhoto.objects.create(
            container=self.cont,
            image=self._tiny_png(),
            photo_date=date(2026, 8, 1),
        )
        del_url = reverse("visual_warehouse_api_container_photo_delete", kwargs={"pk": photo.pk})
        res = self.client.delete(del_url)
        self.assertEqual(res.status_code, 200, res.content[:500])
        body = res.json()
        self.assertTrue(body.get("ok"), body)
        self.assertFalse(VisualContainerPhoto.objects.filter(pk=photo.pk).exists())
        self.assertEqual(body["container"]["photos_count"], 0)
        self.assertEqual(body["container"]["content_photo_date"], "")
