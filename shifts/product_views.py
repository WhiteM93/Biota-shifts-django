"""Карточки изделий."""
import uuid
import re

from django import forms
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import Product, ProductSetup, ProductSetupPhoto

# Ограничение вывода ПП в карточке (страница)
MAX_PROGRAM_DISPLAY_BYTES = 800_000
NAME_SUGGESTION_STOP_WORDS = {
    "корпус",
    "изделие",
    "деталь",
    "сборка",
    "сб",
}


def _cad_ext(name: str) -> str:
    if not name or "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def _name_tokens(text: str) -> list[str]:
    src = (text or "").lower()
    tokens = re.findall(r"[0-9a-zа-яё]+", src, flags=re.IGNORECASE)
    return [t for t in tokens if t]


def _meaningful_tokens(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        if t in NAME_SUGGESTION_STOP_WORDS:
            continue
        if len(t) < 3:
            continue
        out.append(t)
    return out


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
            ProductSetupPhoto.objects.filter(pk=int(sid), product=product, setup__isnull=True).delete()
    nmax = product.setup_photos.filter(setup__isnull=True).aggregate(m=Max("sort_order"))["m"]
    n0 = nmax if nmax is not None else -1
    for i, f in enumerate(request.FILES.getlist("new_setup_photos"), start=1):
        if not f or not f.name:
            continue
        ProductSetupPhoto.objects.create(
            product=product,
            setup=None,
            image=f,
            sort_order=n0 + i,
        )


def _apply_setup_instance_photo_changes(request, product: Product, setup: ProductSetup) -> None:
    keys = []
    seen_keys = set()
    for key in request.POST.getlist("photo_block_keys"):
        key_norm = (key or "").strip()
        if key_norm and key_norm not in seen_keys:
            seen_keys.add(key_norm)
            keys.append(key_norm)

    existing_map = {f"existing-{photo.pk}": photo for photo in setup.photos.all()}
    nmax = setup.photos.aggregate(m=Max("sort_order"))["m"]
    next_sort = (nmax if nmax is not None else -1) + 1

    for key in keys:
        caption = (request.POST.get(f"photo_caption__{key}") or "").strip()
        remove_flag = request.POST.get(f"photo_remove__{key}") == "1"
        file_obj = request.FILES.get(f"photo_file__{key}")

        if key.startswith("existing-"):
            photo = existing_map.get(key)
            if not photo:
                continue
            if remove_flag:
                photo.delete()
                continue
            changed = []
            if caption != photo.caption:
                photo.caption = caption
                changed.append("caption")
            if file_obj and file_obj.name:
                photo.image = file_obj
                changed.append("image")
            if changed:
                photo.save(update_fields=changed)
            continue

        if remove_flag:
            continue
        if file_obj and file_obj.name:
            ProductSetupPhoto.objects.create(
                product=product,
                setup=setup,
                image=file_obj,
                sort_order=next_sort,
                caption=caption,
            )
            next_sort += 1


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
            "binding_x_photo",
            "binding_y_photo",
            "binding_z_photo",
            "workpiece_photo",
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
            "binding_x_photo": forms.FileInput(attrs={"accept": "image/*,.jpg,.jpeg,.png,.webp,.gif"}),
            "binding_y_photo": forms.FileInput(attrs={"accept": "image/*,.jpg,.jpeg,.png,.webp,.gif"}),
            "binding_z_photo": forms.FileInput(attrs={"accept": "image/*,.jpg,.jpeg,.png,.webp,.gif"}),
            "workpiece_photo": forms.FileInput(attrs={"accept": "image/*,.jpg,.jpeg,.png,.webp,.gif"}),
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
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_create_view(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            name_raw = (form.cleaned_data.get("name") or "").strip()
            if name_raw:
                exact_exists = Product.objects.filter(name__iexact=name_raw).exists()
                if exact_exists:
                    form.add_error("name", "Наладка с таким названием уже существует. Проверьте список похожих ниже.")
                    messages.error(request, "Найдено полное совпадение названия. Избегайте дублирования.")
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
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_edit_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            obj: Product = form.save()
            removable_file_fields = ("drawing_pdf", "cad_model", "preview_stl")
            for field_name in removable_file_fields:
                remove_flag = request.POST.get(f"remove_{field_name}") == "1"
                has_new_file = bool(request.FILES.get(field_name))
                if remove_flag and not has_new_file:
                    f = getattr(obj, field_name)
                    if f:
                        f.delete(save=False)
                    setattr(obj, field_name, "")
                    obj.save(update_fields=[field_name])
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
def product_name_suggestions_view(request):
    q = (request.GET.get("q") or "").strip()
    exclude_id_raw = (request.GET.get("exclude_id") or "").strip()
    exclude_id = int(exclude_id_raw) if exclude_id_raw.isdigit() else None
    if len(q) < 2:
        return JsonResponse({"ok": True, "items": []})

    qs = Product.objects.all()
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    q_tokens_all = _name_tokens(q)
    q_tokens = _meaningful_tokens(q_tokens_all)
    q_numeric_tokens = [t for t in q_tokens_all if any(ch.isdigit() for ch in t) and len(t) >= 4]

    cond = Q(name__icontains=q)
    for t in q_tokens[:3]:
        cond |= Q(name__icontains=t)

    candidates = list(
        qs.filter(cond)
        .order_by("-updated_at", "name")
        .values("id", "name")[:60]
    )
    scored = []
    for row in candidates:
        name = row.get("name") or ""
        name_tokens_all = _name_tokens(name)
        name_tokens = set(_meaningful_tokens(name_tokens_all))
        if q_numeric_tokens:
            name_numeric = set(t for t in name_tokens_all if any(ch.isdigit() for ch in t) and len(t) >= 4)
            if not any(t in name_numeric for t in q_numeric_tokens):
                continue
        if q_tokens:
            inter = len(set(q_tokens) & name_tokens)
            score = inter / max(len(set(q_tokens)), 1)
            if score < 0.6 and q.lower() not in name.lower():
                continue
        scored.append(row)
        if len(scored) >= 8:
            break

    return JsonResponse({"ok": True, "items": scored})


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET"])
def product_detail_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    setup_photos = list(product.setup_photos.filter(setup__isnull=True))
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
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_setup_create_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductSetupForm(request.POST, request.FILES)
        if form.is_valid():
            setup: ProductSetup = form.save(commit=False)
            setup.product = product
            setup.save()
            _apply_setup_instance_photo_changes(request, product, setup)
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
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_setup_edit_view(request, pk: int, setup_pk: int):
    product = get_object_or_404(Product, pk=pk)
    setup = get_object_or_404(ProductSetup, pk=setup_pk, product=product)
    if request.method == "POST":
        form = ProductSetupForm(request.POST, request.FILES, instance=setup)
        if form.is_valid():
            saved_setup: ProductSetup = form.save()
            remove_tool_pdf = request.POST.get("remove_tool_pdf") == "1"
            if remove_tool_pdf and not request.FILES.get("tool_pdf"):
                if saved_setup.tool_pdf:
                    saved_setup.tool_pdf.delete(save=False)
                saved_setup.tool_pdf = ""
                saved_setup.save(update_fields=["tool_pdf"])
            remove_program_file = request.POST.get("remove_program_file") == "1"
            if remove_program_file and not request.FILES.get("program_file"):
                if saved_setup.program_file:
                    saved_setup.program_file.delete(save=False)
                saved_setup.program_file = ""
                saved_setup.save(update_fields=["program_file"])
            for field_name in ("binding_x_photo", "binding_y_photo", "binding_z_photo", "workpiece_photo"):
                remove_flag = request.POST.get(f"remove_{field_name}") == "1"
                if remove_flag and not request.FILES.get(field_name):
                    f = getattr(saved_setup, field_name)
                    if f:
                        f.delete(save=False)
                    setattr(saved_setup, field_name, "")
                    saved_setup.save(update_fields=[field_name])
            _apply_setup_instance_photo_changes(request, product, setup)
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
@write_permission_required
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
