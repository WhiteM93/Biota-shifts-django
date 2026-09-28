"""API ИИ-анализа наладки."""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .gpt_rate_limit import gpt_rate_limit_allow
from .inventory_ai_log import record_ai_turn
from .models import InventoryAiTurn, Product, ProductSetup
from .setup_ai import analyze_setup
from .yandex_gpt import yandex_gpt_configured


@biota_login_required
@nav_permission_required("products")
@write_permission_required
@require_http_methods(["POST"])
def product_setup_ai_analyze(request, pk: int, setup_pk: int):
    username = biota_user(request) or ""
    ok_rl, retry = gpt_rate_limit_allow(username, scope="setup_ai", cooldown_sec=60)
    if not ok_rl:
        return JsonResponse(
            {
                "ok": False,
                "error": f"Не чаще 1 раза в минуту. Подождите ~{retry} сек.",
                "retry_after": retry,
            },
            status=429,
        )

    product = get_object_or_404(Product, pk=pk)
    setup = get_object_or_404(
        ProductSetup.objects.prefetch_related("tools"),
        pk=setup_pk,
        product=product,
    )
    result = analyze_setup(product=product, setup=setup)
    try:
        pname = (product.name or "").strip() or f"#{product.pk}"
        sname = (setup.name or "").strip() or f"#{setup.pk}"
        record_ai_turn(
            username=username,
            kind=InventoryAiTurn.KIND_SETUP_AI,
            question=f"ИИ-анализ наладки: {pname} / {sname}",
            result=result,
            extra={
                "product_id": product.pk,
                "setup_id": setup.pk,
                "product_name": pname,
                "setup_name": sname,
                "match_summary": result.get("match_summary") or {},
            },
        )
    except Exception:
        pass
    status = 200 if result.get("ok") else 400
    if not result.get("ok") and "не настроен" in (result.get("error") or "").lower():
        status = 503
    return JsonResponse(
        {
            "ok": bool(result.get("ok")),
            "reply": result.get("reply") or "",
            "error": result.get("error") or "",
            "match_summary": result.get("match_summary") or {},
            "configured": yandex_gpt_configured(),
        },
        status=status,
    )
