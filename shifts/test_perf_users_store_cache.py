"""Тесты кэша users store (пакет A)."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from biota_shifts.auth import _load_users_store, invalidate_users_store_cache


@override_settings(BIOTA_PERF_USERS_STORE_CACHE_SEC=60)
class UsersStoreCacheTests(SimpleTestCase):
    def setUp(self):
        invalidate_users_store_cache()

    def tearDown(self):
        invalidate_users_store_cache()

    def test_disk_read_cached_within_ttl(self):
        payload = {"u1": {"role": "user"}}
        with patch("biota_shifts.auth._read_users_store_from_disk", return_value=payload) as read_mock:
            self.assertEqual(_load_users_store(), payload)
            self.assertEqual(_load_users_store(), payload)
            self.assertEqual(read_mock.call_count, 1)

    def test_cache_returns_deep_copy(self):
        payload = {"u1": {"role": "user"}}
        with patch("biota_shifts.auth._read_users_store_from_disk", return_value=payload):
            first = _load_users_store()
            first["u1"]["role"] = "admin"
            second = _load_users_store()
            self.assertEqual(second["u1"]["role"], "user")

    @override_settings(BIOTA_PERF_USERS_STORE_CACHE_SEC=0)
    def test_cache_disabled_reads_each_time(self):
        payload = {"u1": {"role": "user"}}
        with patch("biota_shifts.auth._read_users_store_from_disk", return_value=payload) as read_mock:
            _load_users_store()
            _load_users_store()
            self.assertEqual(read_mock.call_count, 2)
