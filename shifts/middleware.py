from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse

from biota_shifts.auth import user_is_executor


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
REGISTER_PATH_PREFIX = "/accounts/register"


def _rate_limit_response(message: str, retry_after: int) -> HttpResponse:
    return HttpResponse(
        message,
        status=429,
        content_type="text/plain; charset=utf-8",
        headers={"Retry-After": str(retry_after)},
    )


class AuthRateLimitMiddleware:
    """Rate limit по IP для /accounts/register/* и POST на вход (/accounts/login/, /)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from shifts.rate_limit import get_client_ip, is_login_post_request, login_rate_limits, registration_rate_limits

        client_id = get_client_ip(request)
        path = request.path or ""

        if getattr(settings, "BIOTA_REGISTER_RATELIMIT_ENABLED", True) and path.startswith(REGISTER_PATH_PREFIX):
            result = registration_rate_limits(
                client_id=client_id,
                method=request.method or "GET",
                burst_max=getattr(settings, "BIOTA_REGISTER_RATELIMIT_BURST", 30),
                burst_window=getattr(settings, "BIOTA_REGISTER_RATELIMIT_BURST_WINDOW", 300),
                post_max=getattr(settings, "BIOTA_REGISTER_RATELIMIT_POST", 5),
                post_window=getattr(settings, "BIOTA_REGISTER_RATELIMIT_POST_WINDOW", 3600),
            )
            if result.exceeded:
                return _rate_limit_response(
                    "Слишком много запросов к странице регистрации. Попробуйте позже.",
                    result.retry_after,
                )

        if getattr(settings, "BIOTA_LOGIN_RATELIMIT_ENABLED", True) and is_login_post_request(request):
            result = login_rate_limits(
                client_id=client_id,
                post_max=getattr(settings, "BIOTA_LOGIN_RATELIMIT_MAX", 10),
                post_window=getattr(settings, "BIOTA_LOGIN_RATELIMIT_WINDOW", 900),
            )
            if result.exceeded:
                return _rate_limit_response(
                    "Слишком много попыток входа. Попробуйте позже.",
                    result.retry_after,
                )

        return self.get_response(request)


class RegistrationRateLimitMiddleware(AuthRateLimitMiddleware):
    """Обратная совместимость (алиас AuthRateLimitMiddleware)."""

    pass


class ExecutorReadOnlyMiddleware:
    """For executor role allow only read/download requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        method = (request.method or "").upper()
        if method in SAFE_METHODS:
            return self.get_response(request)

        username = (request.session.get("biota_username") or "").strip()
        if username and user_is_executor(username):
            action = (request.POST.get("action") or "").strip()
            if action in {"refresh_google", "inline_toggle_setup_in_work"}:
                return self.get_response(request)
            is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
            if is_ajax:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "read_only",
                        "message": "Роль «исполнитель»: доступны только просмотр и скачивание.",
                    },
                    status=403,
                )
            return HttpResponseForbidden("Роль «исполнитель»: доступны только просмотр и скачивание.")

        return self.get_response(request)


class PerfDiagnosticMiddleware:
    """Заголовок X-Biota-Response-Ms и запись медленных HTML-ответов (если BIOTA_PERF_DIAGNOSTICS)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        if not getattr(settings, "BIOTA_PERF_DIAGNOSTICS", False):
            return self.get_response(request)

        import time

        from shifts.perf_diagnostic import record_server_diagnostic

        start = time.perf_counter()
        response = self.get_response(request)
        server_ms = int((time.perf_counter() - start) * 1000)
        response["X-Biota-Response-Ms"] = str(server_ms)

        if request.method == "GET":
            content_type = (response.get("Content-Type") or "").lower()
            if "text/html" in content_type and getattr(response, "status_code", 200) < 400:
                try:
                    record_server_diagnostic(request, server_ms)
                except Exception:
                    pass
        return response
