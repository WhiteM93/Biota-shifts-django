from django.http import HttpResponseForbidden, JsonResponse

from biota_shifts.auth import user_is_executor


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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
