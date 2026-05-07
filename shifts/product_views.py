"""Карточки изделий."""
import json
import os
import uuid
import re

from django import forms
from django.forms import inlineformset_factory
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import Product, ProductSetup, ProductSetupPhoto, ProductSetupProgramFile, ProductSetupToolRow
from .product_plan_sync import (
    apply_product_plan_post,
    plan_card_summary,
    plan_form_context,
    plan_inline_state_payload,
    plan_piece_for_naladki_card,
    validate_product_plan_post,
)

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


def _setup_program_files_qs(setup: ProductSetup):
    return setup.program_files.order_by("sort_order", "id")


def _setup_primary_program_field(setup: ProductSetup):
    """Первый файл программы (для просмотра G/M и ссылки «скачать»)."""
    row = _setup_program_files_qs(setup).first()
    if row and row.file:
        return row.file
    if setup.program_file:
        return setup.program_file
    return None


def _append_setup_program_file(setup: ProductSetup, uploaded_file) -> ProductSetupProgramFile:
    """Добавляет ещё один файл программы к установке."""
    if not uploaded_file:
        raise ValueError("empty file")
    last = _setup_program_files_qs(setup).aggregate(m=Max("sort_order"))["m"]
    n = (last if last is not None else -1) + 1
    base = (getattr(uploaded_file, "name", "") or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not base:
        base = f"program_{uuid.uuid4().hex[:10]}.nc"
    row = ProductSetupProgramFile(setup=setup, sort_order=n)
    row.save()
    row.file.save(base, uploaded_file, save=True)
    setup.save(update_fields=["updated_at"])
    return row


def _clear_setup_program_files(setup: ProductSetup) -> None:
    for row in list(_setup_program_files_qs(setup)):
        if row.file:
            try:
                row.file.delete(save=False)
            except Exception:
                pass
        row.delete()
    if setup.program_file:
        try:
            setup.program_file.delete(save=False)
        except Exception:
            pass
        setup.program_file = ""
        setup.save(update_fields=["program_file", "updated_at"])


def _program_files_payload(setup: ProductSetup) -> dict:
    prim = _setup_primary_program_field(setup)
    files_out = []
    for row in _setup_program_files_qs(setup):
        if not row.file:
            continue
        files_out.append(
            {
                "id": row.pk,
                "url": row.file.url,
                "name": row.display_name,
            }
        )
    return {
        "program_files": files_out,
        "program_url": prim.url if prim else "",
        "program_filename": os.path.basename(prim.name) if prim else "",
    }


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
            "gcode_system",
            "binding_x_photo",
            "binding_y_photo",
            "binding_z_photo",
            "workpiece_photo",
            "workpiece",
            "material",
            "size",
            "setup_notes",
            "preview_stl",
        )
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Например, Установка 1"}),
            "binding_x": forms.TextInput(attrs={"placeholder": "Например, X0 или -12.5"}),
            "binding_y": forms.TextInput(attrs={"placeholder": "Например, Y0 или 34.2"}),
            "binding_z": forms.TextInput(attrs={"placeholder": "Например, Z0 или +3.0"}),
            "gcode_system": forms.Select(
                choices=[("G54", "G54"), ("G55", "G55"), ("G56", "G56"), ("G57", "G57"), ("G58", "G58"), ("G59", "G59")]
            ),
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
            "preview_stl": forms.FileInput(attrs={"accept": ".stl"}),
        }


class ProductSetupToolRowForm(forms.ModelForm):
    class Meta:
        model = ProductSetupToolRow
        fields = (
            "tool_number",
            "kor_n",
            "kor_d",
            "tool_type",
            "tap_hole_type",
            "name",
            "diameter",
            "overhang",
        )
        widgets = {
            "tool_number": forms.TextInput(attrs={"placeholder": "1", "inputmode": "numeric"}),
            "kor_n": forms.TextInput(attrs={"placeholder": "H1"}),
            "kor_d": forms.TextInput(attrs={"placeholder": "D1"}),
            "tool_type": forms.Select(
                choices=[
                    ("", "—"),
                    ("Метчик", "Метчик"),
                    ("Раскатник", "Раскатник"),
                    ("Резьбофреза", "Резьбофреза"),
                    ("Центровка", "Центровка"),
                    ("Зенкер", "Зенкер"),
                    ("Развертка", "Развертка"),
                    ("Сверло", "Сверло"),
                    ("Сверло твердосплавное", "Сверло твердосплавное"),
                    ("Т-образная фреза", "Т-образная фреза"),
                    ("Радиусная", "Радиусная"),
                    ("Сферическая", "Сферическая"),
                    ("Фреза обдирочная", "Фреза обдирочная"),
                    ("Фреза черновая", "Фреза черновая"),
                    ("Фреза чистовая", "Фреза чистовая"),
                    ("Фреза профильная", "Фреза профильная"),
                    ("Фреза фасочная", "Фреза фасочная"),
                    ("Фреза с СМП", "Фреза с СМП"),
                    ("Датчик привязки", "Датчик привязки"),
                    ("Другое", "Другое"),
                ]
            ),
            "tap_hole_type": forms.Select(
                choices=[
                    ("", "—"),
                    ("Сквозной", "Сквозной"),
                    ("Глухой", "Глухой"),
                ]
            ),
            "name": forms.TextInput(attrs={"placeholder": "MILL_50_KVL"}),
            "diameter": forms.TextInput(attrs={"placeholder": "Ø50.0"}),
            "overhang": forms.TextInput(attrs={"placeholder": "50 мм"}),
        }


ProductSetupToolRowFormSet = inlineformset_factory(
    ProductSetup,
    ProductSetupToolRow,
    form=ProductSetupToolRowForm,
    extra=26,
    can_delete=False,
)

SETUP_TOOL_TYPE_CHOICES = [
    ("", "—"),
    ("Метчик", "Метчик"),
    ("Раскатник", "Раскатник"),
    ("Резьбофреза", "Резьбофреза"),
    ("Центровка", "Центровка"),
    ("Зенкер", "Зенкер"),
    ("Развертка", "Развертка"),
    ("Сверло", "Сверло"),
    ("Сверло твердосплавное", "Сверло твердосплавное"),
    ("Т-образная фреза", "Т-образная фреза"),
    ("Радиусная", "Радиусная"),
    ("Сферическая", "Сферическая"),
    ("Фреза обдирочная", "Фреза обдирочная"),
    ("Фреза черновая", "Фреза черновая"),
    ("Фреза чистовая", "Фреза чистовая"),
    ("Фреза профильная", "Фреза профильная"),
    ("Фреза фасочная", "Фреза фасочная"),
    ("Фреза с СМП", "Фреза с СМП"),
    ("Датчик привязки", "Датчик привязки"),
    ("Другое", "Другое"),
]

SETUP_TAP_HOLE_CHOICES = [
    ("", "—"),
    ("Сквозной", "Сквозной"),
    ("Глухой", "Глухой"),
]


def _normalize_tool_number(raw: str) -> str:
    src = (raw or "").strip().upper()
    if not src:
        return ""
    m = re.match(r"^(?:T\s*)?(\d{1,2})$", src)
    if not m:
        return src
    return f"T{int(m.group(1)):02d}"


def _default_tool_number_list() -> list[str]:
    return [f"T{n:02d}" for n in range(25)] + ["T99"]


def _expected_correctors(tool_no: str) -> tuple[str, str]:
    norm = _normalize_tool_number(tool_no)
    if not norm.startswith("T") or len(norm) < 3:
        return "", ""
    suffix = norm[1:].zfill(2)
    return f"H{suffix}", f"D{suffix}"


def _build_default_tool_rows(existing_rows: list[ProductSetupToolRow] | None = None) -> list[dict]:
    existing_rows = existing_rows or []
    mapped: dict[str, ProductSetupToolRow] = {}
    for row in existing_rows:
        key = _normalize_tool_number(row.tool_number)
        if key:
            mapped[key] = row

    out = []
    for tool_no in _default_tool_number_list():
        row = mapped.get(tool_no)
        if row:
            out.append(
                {
                    "tool_number": str(int(tool_no[1:])),
                    "correction_enabled": bool(row.correction_enabled),
                    "kor_n": row.kor_n or "",
                    "kor_d": row.kor_d or "",
                    "tool_type": row.tool_type or "",
                    "tap_hole_type": row.tap_hole_type or "",
                    "name": row.name or "",
                    "diameter": row.diameter or "",
                    "overhang": row.overhang or "",
                }
            )
            continue

        default_row = {
            "tool_number": str(int(tool_no[1:])),
            "correction_enabled": False,
            "kor_n": "",
            "kor_d": "",
            "tool_type": "",
            "tap_hole_type": "",
            "name": "",
            "diameter": "",
            "overhang": "",
        }
        if tool_no == "T20":
            default_row["tool_type"] = "Датчик привязки"
            default_row["kor_n"] = "H20"
            default_row["kor_d"] = "D20"
            default_row["diameter"] = "Шарик ⌀6 мм"
        out.append(default_row)
    return out


def _build_display_tool_rows(existing_rows: list[ProductSetupToolRow] | None = None) -> list[dict]:
    existing_rows = existing_rows or []
    mapped: dict[str, ProductSetupToolRow] = {}
    for row in existing_rows:
        key = _normalize_tool_number(row.tool_number)
        if key:
            mapped[key] = row

    out = []
    for tool_no in _default_tool_number_list():
        row = mapped.get(tool_no)
        if row:
            exp_h, exp_d = _expected_correctors(tool_no)
            cur_h = (row.kor_n or "").strip().upper()
            cur_d = (row.kor_d or "").strip().upper()
            out.append(
                {
                    "tool_number": tool_no,
                    "correction_enabled": bool(row.correction_enabled),
                    "kor_n": row.kor_n or "",
                    "kor_d": row.kor_d or "",
                    "tool_type": row.tool_type or "",
                    "tap_hole_type": row.tap_hole_type or "",
                    "diameter": row.diameter or "",
                    "overhang": row.overhang or "",
                    "note": row.name or "",
                    "kor_n_override": bool(exp_h and cur_h and cur_h != exp_h),
                    "kor_d_override": bool(exp_d and cur_d and cur_d != exp_d),
                }
            )
            continue
        default_row = {
            "tool_number": tool_no,
            "correction_enabled": False,
            "kor_n": "",
            "kor_d": "",
            "tool_type": "",
            "tap_hole_type": "",
            "diameter": "",
            "overhang": "",
            "note": "",
            "kor_n_override": False,
            "kor_d_override": False,
        }
        if tool_no == "T20":
            default_row["tool_type"] = "Датчик привязки"
            default_row["kor_n"] = "H20"
            default_row["kor_d"] = "D20"
            default_row["diameter"] = "Шарик ⌀6 мм"
        out.append(default_row)
    return out


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
@require_http_methods(["GET"])
def product_setup_pdf_export_view(request, pk: int, setup_pk: int, mode: str):
    product = get_object_or_404(Product, pk=pk)
    setup = get_object_or_404(
        ProductSetup.objects.prefetch_related("photos", "tools", "program_files"),
        pk=setup_pk,
        product=product,
    )
    export_mode = (mode or "").strip().lower()
    if export_mode not in {"specs", "photos"}:
        export_mode = "specs"
    tool_rows = _build_display_tool_rows(list(setup.tools.all()))
    pfs = list(setup.program_files.order_by("sort_order", "id"))
    if pfs:
        setup_program_line = ", ".join(p.display_name for p in pfs if p.display_name)
    else:
        setup_program_line = setup.program_filename or "—"
    photos = list(setup.photos.all())
    photo_slots: list[ProductSetupPhoto | None] = photos[:15]
    if len(photo_slots) < 15:
        photo_slots.extend([None] * (15 - len(photo_slots)))
    return render(
        request,
        "shifts/product_setup_pdf_export.html",
        {
            "product": product,
            "setup": setup,
            "tool_rows": tool_rows,
            "photos": photos,
            "photo_slots": photo_slots,
            "mode": export_mode,
            "setup_program_line": setup_program_line,
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
            plan_err = validate_product_plan_post(request.POST)
            if plan_err:
                messages.error(request, plan_err)
                return render(
                    request,
                    "shifts/product_form.html",
                    {
                        "form": form,
                        "username": biota_user(request),
                        "is_edit": False,
                        "product": None,
                        **plan_form_context(None),
                    },
                )
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
                            **plan_form_context(None),
                        },
                    )
            with transaction.atomic():
                obj: Product = form.save()
                _apply_setup_photo_changes(request, obj)
            pe = apply_product_plan_post(obj, request.POST)
            if pe:
                messages.warning(request, pe)
            messages.success(request, "Изделие создано.")
            return redirect("product_detail", pk=obj.pk)
        messages.error(request, "Исправьте ошибки в форме.")
        return render(
            request,
            "shifts/product_form.html",
            {
                "form": form,
                "username": biota_user(request),
                "is_edit": False,
                "product": None,
                **plan_form_context(None),
            },
        )
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
            **plan_form_context(None),
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
            plan_err = validate_product_plan_post(request.POST)
            if plan_err:
                messages.error(request, plan_err)
                return render(
                    request,
                    "shifts/product_form.html",
                    {
                        "form": form,
                        "username": biota_user(request),
                        "is_edit": True,
                        "product": product,
                        **plan_form_context(product),
                    },
                )
            with transaction.atomic():
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
            pe = apply_product_plan_post(obj, request.POST)
            if pe:
                messages.warning(request, pe)
            messages.success(request, "Изделие сохранено.")
            return redirect("product_detail", pk=obj.pk)
        messages.error(request, "Исправьте ошибки в форме.")
        return render(
            request,
            "shifts/product_form.html",
            {
                "form": form,
                "username": biota_user(request),
                "is_edit": True,
                "product": product,
                **plan_form_context(product),
            },
        )
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
            **plan_form_context(product),
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
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_detail_view(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "inline_save_product_plan":
            plan_err = validate_product_plan_post(request.POST)
            if plan_err:
                return JsonResponse({"ok": False, "error": plan_err}, status=400)
            err = apply_product_plan_post(product, request.POST)
            if err:
                return JsonResponse({"ok": False, "error": err}, status=400)
            pp = plan_piece_for_naladki_card(product)
            return JsonResponse(
                {
                    "ok": True,
                    "plan_summary": plan_card_summary(pp),
                    "plan_pk": pp.pk if pp else None,
                    "plan_inline_state": plan_inline_state_payload(product),
                }
            )
        if action == "inline_update_setup_photo_caption":
            photo_id_raw = (request.POST.get("photo_id") or "").strip()
            photo_id = int(photo_id_raw) if photo_id_raw.isdigit() else 0
            photo = ProductSetupPhoto.objects.filter(
                pk=photo_id,
                product=product,
                setup__isnull=False,
            ).first()
            if not photo:
                return JsonResponse({"ok": False, "error": "Фото не найдено."}, status=404)
            photo.caption = (request.POST.get("caption") or "").strip()
            photo.save(update_fields=["caption"])
            return JsonResponse({"ok": True, "photo": {"id": photo.pk, "caption": photo.caption}})

        if action == "inline_delete_setup_photo":
            photo_id_raw = (request.POST.get("photo_id") or "").strip()
            photo_id = int(photo_id_raw) if photo_id_raw.isdigit() else 0
            photo = ProductSetupPhoto.objects.filter(
                pk=photo_id,
                product=product,
                setup__isnull=False,
            ).first()
            if not photo:
                return JsonResponse({"ok": False, "error": "Фото не найдено."}, status=404)
            photo.delete()
            return JsonResponse({"ok": True})

        if action == "inline_create_setup_photo":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            image_file = request.FILES.get("image")
            if not image_file:
                return JsonResponse({"ok": False, "error": "Добавьте фото."}, status=400)
            caption = (request.POST.get("caption") or "").strip()
            nmax = setup.photos.aggregate(m=Max("sort_order"))["m"]
            sort_order = (nmax if nmax is not None else -1) + 1
            photo = ProductSetupPhoto.objects.create(
                product=product,
                setup=setup,
                image=image_file,
                caption=caption,
                sort_order=sort_order,
            )
            return JsonResponse(
                {
                    "ok": True,
                    "photo": {
                        "id": photo.pk,
                        "image_url": photo.image.url,
                        "caption": photo.caption,
                    },
                }
            )

        if action == "inline_reorder_setup_photos":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            raw_ids = (request.POST.get("photo_ids") or "").strip()
            if not raw_ids:
                return JsonResponse({"ok": False, "error": "Порядок фото не передан."}, status=400)
            try:
                ordered_ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]
            except Exception:
                return JsonResponse({"ok": False, "error": "Некорректный список фото."}, status=400)
            if not ordered_ids:
                return JsonResponse({"ok": False, "error": "Некорректный список фото."}, status=400)
            photos_qs = ProductSetupPhoto.objects.filter(
                product=product,
                setup=setup,
                pk__in=ordered_ids,
            )
            photos_map = {p.pk: p for p in photos_qs}
            if len(photos_map) != len(ordered_ids):
                return JsonResponse({"ok": False, "error": "Часть фото не найдена."}, status=400)
            for idx, photo_id in enumerate(ordered_ids):
                photo = photos_map.get(photo_id)
                if photo is None:
                    continue
                if photo.sort_order != idx:
                    photo.sort_order = idx
                    photo.save(update_fields=["sort_order"])
            return JsonResponse({"ok": True})

        if action == "inline_replace_binding_photo":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            field_name = (request.POST.get("field_name") or "").strip()
            allowed_fields = {"binding_x_photo", "binding_y_photo", "binding_z_photo", "workpiece_photo"}
            if field_name not in allowed_fields:
                return JsonResponse({"ok": False, "error": "Некорректное поле фото."}, status=400)
            image_file = request.FILES.get("image")
            if not image_file:
                return JsonResponse({"ok": False, "error": "Выберите фото."}, status=400)
            old_file = getattr(setup, field_name)
            if old_file:
                try:
                    old_file.delete(save=False)
                except Exception:
                    pass
            setattr(setup, field_name, image_file)
            setup.save(update_fields=[field_name, "updated_at"])
            new_file = getattr(setup, field_name)
            return JsonResponse({"ok": True, "url": new_file.url if new_file else ""})

        if action == "inline_replace_setup_stl":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            stl_file = request.FILES.get("stl_file")
            if not stl_file:
                return JsonResponse({"ok": False, "error": "Выберите STL файл."}, status=400)
            fname = (stl_file.name or "").lower()
            if not fname.endswith(".stl"):
                return JsonResponse({"ok": False, "error": "Разрешены только STL файлы."}, status=400)
            if setup.preview_stl:
                try:
                    setup.preview_stl.delete(save=False)
                except Exception:
                    pass
            setup.preview_stl = stl_file
            setup.save(update_fields=["preview_stl", "updated_at"])
            return JsonResponse({"ok": True, "url": setup.preview_stl.url if setup.preview_stl else ""})

        if action == "inline_replace_setup_program":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            program_file = request.FILES.get("program_file")
            if not program_file:
                return JsonResponse({"ok": False, "error": "Выберите файл программы."}, status=400)
            try:
                _append_setup_program_file(setup, program_file)
            except Exception:
                return JsonResponse({"ok": False, "error": "Не удалось сохранить файл программы."}, status=400)
            out = _program_files_payload(setup)
            out["ok"] = True
            return JsonResponse(out)

        if action == "inline_delete_setup_program_file":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            fid_raw = (request.POST.get("program_file_id") or "").strip()
            fid = int(fid_raw) if fid_raw.isdigit() else 0
            row = ProductSetupProgramFile.objects.filter(pk=fid, setup=setup).first()
            if not row:
                return JsonResponse({"ok": False, "error": "Файл не найден."}, status=404)
            if row.file:
                try:
                    row.file.delete(save=False)
                except Exception:
                    pass
            row.delete()
            setup.save(update_fields=["updated_at"])
            out = _program_files_payload(setup)
            out["ok"] = True
            return JsonResponse(out)

        if action == "inline_update_setup":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            editable_fields = (
                "name",
                "binding_x",
                "binding_y",
                "binding_z",
                "gcode_system",
                "workpiece",
                "material",
                "size",
                "setup_notes",
            )
            for field in editable_fields:
                setattr(setup, field, (request.POST.get(field) or "").strip())
            setup.save(update_fields=list(editable_fields) + ["updated_at"])
            rows_json = (request.POST.get("rows_json") or "").strip()
            if rows_json:
                try:
                    rows = json.loads(rows_json)
                except Exception:
                    return JsonResponse({"ok": False, "error": "Некорректные данные таблицы инструмента."}, status=400)
                if not isinstance(rows, list):
                    return JsonResponse({"ok": False, "error": "Некорректный формат таблицы инструмента."}, status=400)
                ProductSetupToolRow.objects.filter(setup=setup).delete()
                for idx, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    row_tool_number = str((row.get("tool_number") or "")).strip()
                    row_correction_enabled = bool(row.get("correction_enabled"))
                    row_kor_n = str((row.get("kor_n") or "")).strip()
                    row_kor_d = str((row.get("kor_d") or "")).strip()
                    row_tool_type = str((row.get("tool_type") or "")).strip()
                    row_diameter = str((row.get("diameter") or "")).strip()
                    row_overhang = str((row.get("overhang") or "")).strip()
                    row_note = str((row.get("note") or "")).strip()
                    row_vals = (row_tool_number, row_kor_n, row_kor_d, row_tool_type, row_diameter, row_overhang, row_note)
                    if all(v == "" for v in row_vals) and not row_correction_enabled:
                        continue
                    ProductSetupToolRow.objects.create(
                        setup=setup,
                        sort_order=idx,
                        tool_number=row_tool_number,
                        correction_enabled=row_correction_enabled,
                        kor_n=row_kor_n,
                        kor_d=row_kor_d,
                        tool_type=row_tool_type,
                        diameter=row_diameter,
                        overhang=row_overhang,
                        tap_hole_type="",
                        name=row_note,
                    )
            out: dict = {
                "ok": True,
                "setup": {
                    "id": setup.pk,
                    "name": setup.name or "",
                    "binding_x": setup.binding_x or "—",
                    "binding_y": setup.binding_y or "—",
                    "binding_z": setup.binding_z or "—",
                    "gcode_system": setup.gcode_system or "G54",
                    "workpiece": setup.workpiece or "—",
                    "material": setup.material or "—",
                    "size": setup.size or "—",
                    "setup_notes": (setup.setup_notes or "").strip(),
                },
            }
            if (request.POST.get("sync_plan_from_inline") or "").strip() == "1":
                plan_err = validate_product_plan_post(request.POST)
                if plan_err:
                    return JsonResponse({"ok": False, "error": plan_err}, status=400)
                perr = apply_product_plan_post(product, request.POST)
                if perr:
                    return JsonResponse({"ok": False, "error": perr}, status=400)
                pp = plan_piece_for_naladki_card(product)
                out["plan_summary"] = plan_card_summary(pp)
                out["plan_pk"] = pp.pk if pp else None
                out["plan_inline_state"] = plan_inline_state_payload(product)
            return JsonResponse(out)
        return JsonResponse({"ok": False, "error": "Неизвестное действие."}, status=400)
    setup_photos = list(product.setup_photos.filter(setup__isnull=True))
    setups = list(product.setups.prefetch_related("tools", "program_files"))
    for setup in setups:
        setup.tab_slug = f"setup-{setup.pk}"
        prim_pf = _setup_primary_program_field(setup)
        setup.program_text, setup.program_too_large = _read_program_file_for_display(prim_pf)
        setup.program_file_list = list(_setup_program_files_qs(setup))
        setup.has_any_program = bool(setup.program_file_list) or bool(setup.program_file)
        setup.primary_program_url = prim_pf.url if prim_pf else ""
        setup.primary_program_filename = os.path.basename(prim_pf.name) if prim_pf else ""
        setup.tool_rows = list(setup.tools.all())
        setup.tool_display_rows = _build_display_tool_rows(setup.tool_rows)
    has_setup_preview_stl = any(bool(getattr(s, "preview_stl", None)) for s in setups)
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
    tab_default = "drawing"
    active_setup = None
    if tab_default.startswith("setup-"):
        for setup in setups:
            if setup.tab_slug == tab_default:
                active_setup = setup
                break
    if active_setup is None and setups:
        active_setup = setups[0]
    return render(
        request,
        "shifts/product_detail.html",
        {
            "product": product,
            **plan_form_context(product),
            "setup_photos": setup_photos,
            "setups": setups,
            "cad_ext": cad_ext,
            "cad_is_stl": cad_ext == "stl",
            "cad_is_step": cad_is_step,
            "preview_stl_url": preview_stl_url,
            "cad_inline_preview": cad_inline_preview,
            "has_setup_preview_stl": has_setup_preview_stl,
            "program_text": program_text,
            "program_too_large": program_too_large,
            "tab_default": tab_default,
            "active_setup": active_setup,
            "tool_type_choices": SETUP_TOOL_TYPE_CHOICES,
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
            tools_formset = ProductSetupToolRowFormSet(
                request.POST,
                instance=setup,
                queryset=ProductSetupToolRow.objects.none(),
                prefix="tools",
            )
            if tools_formset.is_valid():
                uploaded_program = request.FILES.get("program_file")
                setup.save()
                if uploaded_program:
                    try:
                        _append_setup_program_file(setup, uploaded_program)
                    except Exception:
                        pass
                # Сначала удаляем (на всякий случай), затем пересоздаём строки.
                ProductSetupToolRow.objects.filter(setup=setup).delete()
                for idx, tform in enumerate(tools_formset.forms):
                    cd = tform.cleaned_data
                    row_vals = (
                        cd.get("tool_number"),
                        cd.get("kor_n"),
                        cd.get("kor_d"),
                        cd.get("tool_type"),
                        cd.get("tap_hole_type"),
                        cd.get("name"),
                        cd.get("diameter"),
                        cd.get("overhang"),
                    )
                    if all((v or "").strip() == "" for v in row_vals):
                        continue
                    ProductSetupToolRow.objects.create(
                        setup=setup,
                        sort_order=idx,
                        tool_number=cd.get("tool_number") or "",
                        kor_n=cd.get("kor_n") or "",
                        kor_d=cd.get("kor_d") or "",
                        tool_type=cd.get("tool_type") or "",
                        tap_hole_type=cd.get("tap_hole_type") or "",
                        name=cd.get("name") or "",
                        diameter=cd.get("diameter") or "",
                        overhang=cd.get("overhang") or "",
                    )
                _apply_setup_instance_photo_changes(request, product, setup)
                messages.success(request, "Установка добавлена.")
                return redirect("product_detail", pk=product.pk)
            tools_formset_bad = tools_formset
        else:
            tools_formset_bad = ProductSetupToolRowFormSet(
                request.POST,
                instance=ProductSetup(product=product),
                queryset=ProductSetupToolRow.objects.none(),
                prefix="tools",
            )
        messages.error(request, "Исправьте ошибки в форме установки.")
    else:
        max_order = product.setups.aggregate(m=Max("sort_order"))["m"]
        form = ProductSetupForm(initial={"sort_order": (max_order + 1) if max_order is not None else 0})
        tools_formset_bad = ProductSetupToolRowFormSet(
            instance=ProductSetup(product=product),
            queryset=ProductSetupToolRow.objects.none(),
            initial=_build_default_tool_rows(),
            prefix="tools",
        )
    return render(
        request,
        "shifts/product_setup_form.html",
        {
            "form": form,
            "product": product,
            "is_edit": False,
            "tools_formset": tools_formset_bad,
            "username": biota_user(request),
        },
    )


@biota_login_required
@nav_permission_required("products")
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_setup_edit_view(request, pk: int, setup_pk: int):
    product = get_object_or_404(Product, pk=pk)
    setup = get_object_or_404(
        ProductSetup.objects.prefetch_related("program_files", "photos", "tools"),
        pk=setup_pk,
        product=product,
    )
    if request.method == "POST":
        form = ProductSetupForm(request.POST, request.FILES, instance=setup)
        tools_formset = ProductSetupToolRowFormSet(
            request.POST,
            instance=setup,
            queryset=ProductSetupToolRow.objects.none(),
            prefix="tools",
        )
        if form.is_valid() and tools_formset.is_valid():
            uploaded_program = request.FILES.get("program_file")
            saved_setup: ProductSetup = form.save()
            if uploaded_program:
                try:
                    _append_setup_program_file(saved_setup, uploaded_program)
                except Exception:
                    pass
            ProductSetupToolRow.objects.filter(setup=saved_setup).delete()
            for idx, tform in enumerate(tools_formset.forms):
                cd = tform.cleaned_data
                row_vals = (
                    cd.get("tool_number"),
                    cd.get("kor_n"),
                    cd.get("kor_d"),
                    cd.get("tool_type"),
                    cd.get("tap_hole_type"),
                    cd.get("name"),
                    cd.get("diameter"),
                    cd.get("overhang"),
                )
                if all((v or "").strip() == "" for v in row_vals):
                    continue
                ProductSetupToolRow.objects.create(
                    setup=saved_setup,
                    sort_order=idx,
                    tool_number=cd.get("tool_number") or "",
                    kor_n=cd.get("kor_n") or "",
                    kor_d=cd.get("kor_d") or "",
                    tool_type=cd.get("tool_type") or "",
                    tap_hole_type=cd.get("tap_hole_type") or "",
                    name=cd.get("name") or "",
                    diameter=cd.get("diameter") or "",
                    overhang=cd.get("overhang") or "",
                )
            remove_program_file = request.POST.get("remove_program_file") == "1"
            if remove_program_file and not request.FILES.get("program_file"):
                _clear_setup_program_files(saved_setup)
            elif request.POST.getlist("remove_setup_program_file"):
                for rid in request.POST.getlist("remove_setup_program_file"):
                    if not rid.isdigit():
                        continue
                    row = ProductSetupProgramFile.objects.filter(pk=int(rid), setup=saved_setup).first()
                    if not row:
                        continue
                    if row.file:
                        try:
                            row.file.delete(save=False)
                        except Exception:
                            pass
                    row.delete()
                saved_setup.save(update_fields=["updated_at"])
            remove_preview_stl = request.POST.get("remove_preview_stl") == "1"
            if remove_preview_stl and not request.FILES.get("preview_stl"):
                if saved_setup.preview_stl:
                    saved_setup.preview_stl.delete(save=False)
                saved_setup.preview_stl = ""
                saved_setup.save(update_fields=["preview_stl"])
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
        tools_formset_bad = tools_formset
        messages.error(request, "Исправьте ошибки в форме установки.")
    else:
        form = ProductSetupForm(instance=setup)
        tools_formset_bad = ProductSetupToolRowFormSet(
            instance=setup,
            queryset=ProductSetupToolRow.objects.none(),
            initial=_build_default_tool_rows(list(setup.tools.all())),
            prefix="tools",
        )
    return render(
        request,
        "shifts/product_setup_form.html",
        {
            "form": form,
            "product": product,
            "setup": setup,
            "is_edit": True,
            "tools_formset": tools_formset_bad,
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
