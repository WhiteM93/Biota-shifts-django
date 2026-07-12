"""Страница контроля размеров по установке."""
from __future__ import annotations

import json

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import _is_admin, user_is_executor

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import Product, ProductInspectionDimension, ProductInspectionSession, ProductSetup
from .product_inspection import (
    applicable_dimensions,
    create_inspection_session,
    dimension_to_dict,
    inspection_context_payload,
    parse_json_list,
    save_inspection_plan,
    session_to_dict,
)
from .product_views import _post_bool, _product_detail_url, _product_drawing_files_qs


def _setup_inspection_url(product: Product, setup: ProductSetup) -> str:
    return reverse(
        "product_setup_inspection",
        kwargs={"pk": product.pk, "setup_pk": setup.pk},
    )


def _product_setup_tab_url(product: Product, setup: ProductSetup) -> str:
    base = _product_detail_url(product)
    return f"{base}?tab=setup-{setup.pk}"


def _inspection_bootstrap_json(product: Product, setup: ProductSetup, username: str | None) -> str:
    who = (username or "").strip()
    can_edit = bool(who) and (_is_admin(who) or not user_is_executor(who))
    ctx = inspection_context_payload(product, setup, username)
    return json.dumps(
        {
            "canEdit": can_edit,
            "productId": product.pk,
            "setupId": setup.pk,
            "productName": (product.name or "").strip(),
            "setupName": (setup.name or "").strip() or f"Установка {setup.pk}",
            "productUrl": _product_setup_tab_url(product, setup),
            "criticalityChoices": [
                {"value": v, "label": lbl} for v, lbl in ProductInspectionDimension.CRITICALITY_CHOICES
            ],
            "frequencyChoices": [
                {"value": v, "label": lbl} for v, lbl in ProductInspectionDimension.FREQUENCY_CHOICES
            ],
            "inspection": ctx,
        },
        ensure_ascii=False,
    )


@biota_login_required
@nav_permission_required("products")
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_setup_inspection_view(request, pk: int, setup_pk: int):
    product = get_object_or_404(Product.objects.prefetch_related("drawing_files"), pk=pk)
    if product.is_osnastka:
        raise Http404("Контроль размеров доступен только для наладок.")
    setup = get_object_or_404(ProductSetup, pk=setup_pk, product=product)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "save_inspection_plan":
            rows = parse_json_list(request.POST.get("dimensions_json") or "[]")
            if rows is None:
                return JsonResponse({"ok": False, "error": "Некорректный JSON карты контроля."}, status=400)
            plan_err = save_inspection_plan(product, setup, rows)
            if plan_err:
                return JsonResponse({"ok": False, "error": plan_err}, status=400)
            payload = inspection_context_payload(product, setup, biota_user(request))
            return JsonResponse({"ok": True, "inspection": payload})

        if action == "create_inspection_session":
            measurements = parse_json_list(request.POST.get("measurements_json") or "[]")
            if measurements is None:
                return JsonResponse({"ok": False, "error": "Некорректный JSON замеров."}, status=400)
            session, sess_err = create_inspection_session(
                product,
                setup,
                author_username=(biota_user(request) or "?").strip(),
                inspector_emp_code=(request.POST.get("inspector_emp_code") or "").strip(),
                inspector_label=(request.POST.get("inspector_label") or "").strip(),
                part_label=(request.POST.get("part_label") or "").strip(),
                first_piece=_post_bool(request.POST.get("first_piece")),
                notes=(request.POST.get("notes") or "").strip(),
                measurements=measurements,
            )
            if sess_err:
                return JsonResponse({"ok": False, "error": sess_err}, status=400)
            payload = inspection_context_payload(product, setup, biota_user(request))
            return JsonResponse(
                {
                    "ok": True,
                    "session": session_to_dict(session),
                    "inspection": payload,
                }
            )

        if action == "delete_inspection_session":
            sid_raw = (request.POST.get("session_id") or "").strip()
            sid = int(sid_raw) if sid_raw.isdigit() else 0
            if sid <= 0:
                return JsonResponse({"ok": False, "error": "Не указан акт."}, status=400)
            session = ProductInspectionSession.objects.filter(pk=sid, product=product, setup=setup).first()
            if not session:
                return JsonResponse({"ok": False, "error": "Акт не найден."}, status=404)
            session.delete()
            payload = inspection_context_payload(product, setup, biota_user(request))
            return JsonResponse({"ok": True, "inspection": payload})

        if action == "get_inspection_applicable":
            first_piece = _post_bool(request.POST.get("first_piece"))
            dims = applicable_dimensions(product, setup, first_piece=first_piece)
            return JsonResponse({"ok": True, "dimensions": [dimension_to_dict(d) for d in dims]})

        return JsonResponse({"ok": False, "error": "Неизвестное действие."}, status=400)

    product.drawing_file_list = list(_product_drawing_files_qs(product))
    username = biota_user(request)
    who = (username or "").strip()
    can_edit = bool(who) and (_is_admin(who) or not user_is_executor(who))
    setup_label = (setup.name or "").strip() or f"Установка {setup.pk}"
    return render(
        request,
        "shifts/product_inspection.html",
        {
            "product": product,
            "setup": setup,
            "setup_label": setup_label,
            "product_url": _product_setup_tab_url(product, setup),
            "inspection_ctx": inspection_context_payload(product, setup, username),
            "inspection_bootstrap_json": _inspection_bootstrap_json(product, setup, username),
            "biota_can_edit": can_edit,
        },
    )
