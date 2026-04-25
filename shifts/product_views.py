"""Карточки изделий."""
import uuid

from django import forms
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required
from .models import Product, ProductSetup, ProductSetupPhoto

# Ограничение вывода ПП в карточке (страница)
MAX_PROGRAM_DISPLAY_BYTES = 800_000


def _cad_ext(name: str) -> str:
    if not name or "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def _read_program_file_for_display(program_file) -> tuple[str | None, bool]:
    if not program_file:
        return None, False
    try:
        path = program_file.path
    except Exception:
        return None, False
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_PROGRAM_DISPLAY_BYTES + 1)
    except OSError:
        return None, False
    if len(raw) > MAX_PROGRAM_DISPLAY_BYTES:
        return None, True
    return raw.decode("utf-8", errors="replace"), False


def _apply_setup_photo_changes(request, product: Product) -> None:
    for sid in request.POST.getlist("remove_setup_photo"):
        if sid.isdigit():
            ProductSetupPhoto.objects.filter(pk=int(sid), product=product).delete()
    nmax = product.setup_photos.aggregate(m=Max("sort_order"))["m"]
    n0 = nmax if nmax is not None else -1
    for i, f in enumerate(request.FILES.getlist("new_setup_photos"), start=1):
        if not f or not f.name:
            continue
        ProductSetupPhoto.objects.create(
            product=product,
            image=f,
            sort_order=n0 + i,
        )


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name",
            "description",
            "drawing_pdf",
            "cad_model",
            "preview_stl",
        )
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Например, Корпус А-12"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Опционально"}),
        }


class ProductSetupForm(forms.ModelForm):
    class Meta:
        model = ProductSetup
        fields = (
            "name",
            "sort_order",
            "binding_x",
            "binding_y",
            "binding_z",
            "workpiece",
            "material",
            "size",
            "tool_pdf",
            "setup_notes",
            "program_file",
        )
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Например, Установка 1"}),
            "binding_x": forms.TextInput(attrs={"placeholder": "Например, X0 или -12.5"}),
            "binding_y": forms.TextInput(attrs={"placeholder": "Например, Y0 или 34.2"}),
            "binding_z": forms.TextInput(attrs={"placeholder": "Например, Z0 или +3.0"}),
            "workpiece": forms.TextInput(attrs={"placeholder": "Например, круг D50 L120"}),
            "material": forms.TextInput(attrs={"placeholder": "Например, Сталь 45"}),
            "size": forms.TextInput(attrs={"placeholder": "Например, 50x120 мм"}),
            "setup_notes": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "Заготовка, привязка, инструмент, нюансы.",
                }
            ),
        }


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET", "HEAD"])
def products_list_view(request):
    q = (request.GET.get("q") or "").strip()
    qs = Product.objects.all().order_by("-updated_at", "-id")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    paginator = Paginator(qs, 24)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(
        request,
        "shifts/products_list.html",
        {
            "products_page": page,
            "search_q": q,
            "username": biota_user(request),
        },
    )


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET", "POST"])
def product_create_view(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            obj: Product = form.save()
            _apply_setup_photo_changes(request, obj)
            messages.success(request, "Изделие создано.")
            return redirect("product_detail", pk=obj.pk)
        messages.error(request, "Исправьте ошибки в форме.")
    else:
        form = ProductForm()
    return render(
        request,
        "shifts/product_form.html",
        {
            "form": form,
            "username": biota_user(request),
            "is_edit": False,
            "product": None,
        },
    )


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET", "POST"])
def product_edit_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            obj: Product = form.save()
            _apply_setup_photo_changes(request, obj)
            messages.success(request, "Изделие сохранено.")
            return redirect("product_detail", pk=obj.pk)
        messages.error(request, "Исправьте ошибки в форме.")
    else:
        form = ProductForm(instance=product)
    return render(
        request,
        "shifts/product_form.html",
        {
            "form": form,
            "username": biota_user(request),
            "is_edit": True,
            "product": product,
        },
    )


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET"])
def product_detail_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    setup_photos = list(product.setup_photos.all())
    setups = list(product.setups.all())
    for setup in setups:
        setup.tab_slug = f"setup-{setup.pk}"
        setup.program_text, setup.program_too_large = _read_program_file_for_display(setup.program_file)
    cad_name = (product.cad_model.name or "") if product.cad_model else ""
    cad_ext = _cad_ext(cad_name)
    cad_is_step = cad_ext in ("step", "stp")
    preview_stl_url = ""
    if product.preview_stl:
        preview_stl_url = product.preview_stl.url
    elif product.cad_model and cad_ext == "stl":
        preview_stl_url = product.cad_model.url
    cad_inline_preview = bool(preview_stl_url)
    program_text, program_too_large = _read_program_file_for_display(product.program_file)
    if product.drawing_pdf:
        tab_default = "drawing"
    elif setups:
        tab_default = setups[0].tab_slug
    elif (product.setup_notes or "").strip() or setup_photos:
        tab_default = "setup"
    elif product.program_file:
        tab_default = "program"
    else:
        tab_default = "drawing"
    return render(
        request,
        "shifts/product_detail.html",
        {
            "product": product,
            "setup_photos": setup_photos,
            "setups": setups,
            "cad_ext": cad_ext,
            "cad_is_stl": cad_ext == "stl",
            "cad_is_step": cad_is_step,
            "preview_stl_url": preview_stl_url,
            "cad_inline_preview": cad_inline_preview,
            "program_text": program_text,
            "program_too_large": program_too_large,
            "tab_default": tab_default,
            "username": biota_user(request),
        },
    )


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET", "POST"])
def product_setup_create_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductSetupForm(request.POST, request.FILES)
        if form.is_valid():
            setup: ProductSetup = form.save(commit=False)
            setup.product = product
            setup.save()
            messages.success(request, "Установка добавлена.")
            return redirect("product_detail", pk=product.pk)
        messages.error(request, "Исправьте ошибки в форме установки.")
    else:
        max_order = product.setups.aggregate(m=Max("sort_order"))["m"]
        form = ProductSetupForm(initial={"sort_order": (max_order + 1) if max_order is not None else 0})
    return render(
        request,
        "shifts/product_setup_form.html",
        {
            "form": form,
            "product": product,
            "is_edit": False,
            "username": biota_user(request),
        },
    )


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET", "POST"])
def product_setup_edit_view(request, pk: int, setup_pk: int):
    product = get_object_or_404(Product, pk=pk)
    setup = get_object_or_404(ProductSetup, pk=setup_pk, product=product)
    if request.method == "POST":
        form = ProductSetupForm(request.POST, request.FILES, instance=setup)
        if form.is_valid():
            form.save()
            messages.success(request, "Установка сохранена.")
            return redirect("product_detail", pk=product.pk)
        messages.error(request, "Исправьте ошибки в форме установки.")
    else:
        form = ProductSetupForm(instance=setup)
    return render(
        request,
        "shifts/product_setup_form.html",
        {
            "form": form,
            "product": product,
            "setup": setup,
            "is_edit": True,
            "username": biota_user(request),
        },
    )


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["POST"])
def product_save_list_preview_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    preview_file = request.FILES.get("preview_image")
    if not preview_file:
        return JsonResponse({"ok": False, "error": "Файл превью не передан."}, status=400)
    if preview_file.size > 8 * 1024 * 1024:
        return JsonResponse({"ok": False, "error": "Файл превью слишком большой."}, status=400)
    content_type = (preview_file.content_type or "").lower()
    if not content_type.startswith("image/"):
        return JsonResponse({"ok": False, "error": "Нужен файл изображения."}, status=400)

    ext = ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        ext = ".jpg"
    elif "webp" in content_type:
        ext = ".webp"

    filename = f"product_{product.pk}_{uuid.uuid4().hex}{ext}"
    product.list_preview_image.save(filename, ContentFile(preview_file.read()), save=True)
    return JsonResponse({"ok": True, "url": product.list_preview_image.url})
