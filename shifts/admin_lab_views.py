"""Служебные страницы только для администратора (без проверки nav-разделов)."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import _is_admin

from .auth_utils import biota_login_required, biota_user, post_login_redirect


@biota_login_required
@require_http_methods(["GET", "HEAD"])
def admin_test_lab(request):
    """Песочница для проверки фич и вёрстки. Доступ только у учётной записи администратора."""
    u = biota_user(request)
    if not _is_admin(u or ""):
        messages.warning(request, "Эта страница доступна только администратору.")
        return redirect(post_login_redirect(u))
    return render(request, "shifts/admin_test_lab.html")
