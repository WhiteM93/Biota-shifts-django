"""Тесты rate limit на регистрации."""

from django.core.cache import caches
from django.test import RequestFactory, SimpleTestCase, override_settings

from shifts.middleware import AuthRateLimitMiddleware, RegistrationRateLimitMiddleware
from shifts.rate_limit import check_rate_limit, get_client_ip, is_login_post_request, login_rate_limits, registration_rate_limits


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-default",
        },
        "ratelimit": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-ratelimit",
        },
    }
)
class RateLimitTests(SimpleTestCase):
    def setUp(self):
        caches["ratelimit"].clear()

    def test_get_client_ip_from_x_forwarded_for(self):
        request = RequestFactory().get("/accounts/register/")
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5, 10.0.0.1"
        self.assertEqual(get_client_ip(request), "203.0.113.5")

    def test_burst_limit_blocks_after_max(self):
        for _ in range(3):
            result = check_rate_limit(
                scope="test_burst",
                client_id="1.2.3.4",
                max_requests=3,
                window_seconds=60,
            )
            self.assertFalse(result.exceeded)
        blocked = check_rate_limit(
            scope="test_burst",
            client_id="1.2.3.4",
            max_requests=3,
            window_seconds=60,
        )
        self.assertTrue(blocked.exceeded)
        self.assertGreater(blocked.retry_after, 0)

    def test_post_limit_separate_from_burst(self):
        burst = registration_rate_limits(
            client_id="9.9.9.9",
            method="GET",
            burst_max=100,
            burst_window=300,
            post_max=2,
            post_window=3600,
        )
        self.assertFalse(burst.exceeded)

        for _ in range(2):
            result = registration_rate_limits(
                client_id="9.9.9.9",
                method="POST",
                burst_max=100,
                burst_window=300,
                post_max=2,
                post_window=3600,
            )
            self.assertFalse(result.exceeded)

        blocked = registration_rate_limits(
            client_id="9.9.9.9",
            method="POST",
            burst_max=100,
            burst_window=300,
            post_max=2,
            post_window=3600,
        )
        self.assertTrue(blocked.exceeded)
        self.assertEqual(blocked.limit_key, "register_post")

    def test_login_post_limit(self):
        for _ in range(3):
            result = login_rate_limits(client_id="5.5.5.5", post_max=3, post_window=900)
            self.assertFalse(result.exceeded)
        blocked = login_rate_limits(client_id="5.5.5.5", post_max=3, post_window=900)
        self.assertTrue(blocked.exceeded)
        self.assertEqual(blocked.limit_key, "login_post")

    def test_is_login_post_request(self):
        login_post = RequestFactory().post("/accounts/login/")
        self.assertTrue(is_login_post_request(login_post))
        root_post = RequestFactory().post("/")
        self.assertTrue(is_login_post_request(root_post))
        login_get = RequestFactory().get("/accounts/login/")
        self.assertFalse(is_login_post_request(login_get))


@override_settings(
    BIOTA_REGISTER_RATELIMIT_ENABLED=True,
    BIOTA_REGISTER_RATELIMIT_BURST=2,
    BIOTA_REGISTER_RATELIMIT_BURST_WINDOW=300,
    BIOTA_REGISTER_RATELIMIT_POST=10,
    BIOTA_REGISTER_RATELIMIT_POST_WINDOW=3600,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-default-mw",
        },
        "ratelimit": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-ratelimit-mw",
        },
    },
)
class RegistrationRateLimitMiddlewareTests(SimpleTestCase):
    def setUp(self):
        caches["ratelimit"].clear()
        self.factory = RequestFactory()
        self.middleware = AuthRateLimitMiddleware(lambda request: self._ok_response(request))

    @staticmethod
    def _ok_response(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    def test_allows_normal_traffic(self):
        request = self.factory.get("/accounts/register/")
        request.META["REMOTE_ADDR"] = "10.0.0.2"
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_blocks_register_flood(self):
        request = self.factory.get("/accounts/register/")
        request.META["REMOTE_ADDR"] = "10.0.0.3"
        self.middleware(request)
        self.middleware(request)
        blocked = self.middleware(request)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked)

    def test_other_paths_not_limited(self):
        request = self.factory.get("/accounts/login/")
        request.META["REMOTE_ADDR"] = "10.0.0.4"
        for _ in range(10):
            response = self.middleware(request)
        self.assertEqual(response.status_code, 200)


@override_settings(
    BIOTA_LOGIN_RATELIMIT_ENABLED=True,
    BIOTA_LOGIN_RATELIMIT_MAX=2,
    BIOTA_LOGIN_RATELIMIT_WINDOW=900,
    BIOTA_REGISTER_RATELIMIT_ENABLED=False,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-default-login-mw",
        },
        "ratelimit": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-ratelimit-login-mw",
        },
    },
)
class LoginRateLimitMiddlewareTests(SimpleTestCase):
    def setUp(self):
        caches["ratelimit"].clear()
        self.factory = RequestFactory()
        self.middleware = AuthRateLimitMiddleware(lambda request: self._ok_response(request))

    @staticmethod
    def _ok_response(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    def test_blocks_login_post_flood(self):
        request = self.factory.post("/accounts/login/")
        request.META["REMOTE_ADDR"] = "10.0.0.5"
        self.middleware(request)
        self.middleware(request)
        blocked = self.middleware(request)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked)

    def test_login_get_not_limited(self):
        request = self.factory.get("/accounts/login/")
        request.META["REMOTE_ADDR"] = "10.0.0.6"
        for _ in range(20):
            response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
