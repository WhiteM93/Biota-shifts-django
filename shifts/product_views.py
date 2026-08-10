"""Карточки изделий."""
import json
import os
import re
import uuid
from urllib.parse import urlencode

from django import forms
from django.forms import inlineformset_factory
from django.contrib import messages
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.http import Http404, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from biota_shifts.auth import _is_admin

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import (
    Product,
    ProductFile,
    ProductNote,
    ProductOsnastkaUsage,
    ProductSetup,
    ProductSetupPhoto,
    ProductSetupPieceNorm,
    ProductDrawingFile,
    ProductSetupProgramFile,
    ProductSetupToolRow,
    normalize_product_setup_gcode_system,
    product_setup_gcode_inline_parts,
)
from .plan_naladki_bridge import ensure_plan_piece_for_naladki_product
from .machines_views import assign_product_setup_to_machine, list_machine_codes
from .product_plan_sync import (
    apply_product_plan_post,
    plan_card_summary,
    plan_form_context,
    plan_inline_state_payload,
    validate_product_plan_post,
)

SETUP_LIST_ORDER = ("-in_work", "sort_order", "id")


def _piece_norm_entry_dict(entry: ProductSetupPieceNorm) -> dict:
    prev = entry.previous_tsht_norm
    cur = entry.tsht_norm
    delta = None
    if prev is not None:
        delta = float(cur - prev)
    return {
        "id": entry.pk,
        "setup_id": entry.setup_id,
        "tsht_norm": float(cur),
        "tsht_min": float(entry.tsht_min),
        "previous_tsht_norm": float(prev) if prev is not None else None,
        "delta": delta,
        "comment": entry.comment or "",
        "author": entry.author or "",
        "created_at": entry.created_at.strftime("%d.%m.%Y %H:%M"),
        "t_auto": float(entry.t_auto) if entry.t_auto is not None else None,
        "k_parts": entry.k_parts,
        "a_pct": float(entry.a_pct) if entry.a_pct is not None else None,
        "t_ust": float(entry.t_ust) if entry.t_ust is not None else None,
        "t_izm": float(entry.t_izm) if entry.t_izm is not None else None,
    }


def _latest_piece_norms_by_setup(setup_ids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    if not setup_ids:
        return out
    for entry in ProductSetupPieceNorm.objects.filter(setup_id__in=setup_ids).order_by(
        "setup_id", "-created_at", "-id"
    ):
        if entry.setup_id in out:
            continue
        out[entry.setup_id] = _piece_norm_entry_dict(entry)
    return out


def _products_qs_for_catalog(catalog_section: str):
    return (
        Product.objects.filter(catalog_section=catalog_section)
        .annotate(in_work_count=Count("setups", filter=Q(setups__in_work=True)))
        .order_by("-in_work_count", "-updated_at", "-id")
    )


def _product_detail_url_name(product: Product) -> str:
    if product.is_osnastka:
        return "osnastka_detail"
    return "product_detail"


def _product_detail_url(product: Product) -> str:
    return reverse(_product_detail_url_name(product), kwargs={"pk": product.pk})


def _product_list_url_name(product: Product) -> str:
    if product.is_osnastka:
        return "osnastka_list"
    return "products_list"


def _resolve_product_setup_from_post(product: Product, post) -> ProductSetup | None:
    setup_id_raw = (post.get("setup_id") or "").strip()
    if not setup_id_raw.isdigit():
        return None
    return ProductSetup.objects.filter(pk=int(setup_id_raw), product=product).first()


def _inspection_setup_or_400(product: Product, post):
    setup_id_raw = (post.get("setup_id") or "").strip()
    if not setup_id_raw:
        return None, None
    if not setup_id_raw.isdigit():
        return None, JsonResponse({"ok": False, "error": "Некорректная установка."}, status=400)
    setup = ProductSetup.objects.filter(pk=int(setup_id_raw), product=product).first()
    if not setup:
        return None, JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
    return setup, None


def _product_setups_qs(product: Product):
    return product.setups.order_by(*SETUP_LIST_ORDER)

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


_MAX_BINDING_EXTRA_BLOCKS = 20
_BINDING_EXTRA_PHOTO_FIELDS = frozenset({"binding_x_photo", "binding_y_photo", "binding_z_photo"})
_BINDING_PHOTO_FILE_SUFFIX = {
    "binding_x_photo": "x",
    "binding_y_photo": "y",
    "binding_z_photo": "z",
}


def _binding_extra_block_item(item: dict) -> dict:
    return {
        "binding_x": str(item.get("binding_x") or "")[:64],
        "binding_y": str(item.get("binding_y") or "")[:64],
        "binding_z": str(item.get("binding_z") or "")[:64],
        "gcode_system": normalize_product_setup_gcode_system(str(item.get("gcode_system") or "G54"))[:24],
        "binding_x_photo": str(item.get("binding_x_photo") or "")[:500],
        "binding_y_photo": str(item.get("binding_y_photo") or "")[:500],
        "binding_z_photo": str(item.get("binding_z_photo") or "")[:500],
    }


def _delete_stored_media_url(url: str) -> None:
    path = (url or "").strip()
    if not path:
        return
    media_url = (settings.MEDIA_URL or "/media/").rstrip("/") + "/"
    if path.startswith(media_url):
        path = path[len(media_url) :]
    path = path.lstrip("/")
    try:
        if default_storage.exists(path):
            default_storage.delete(path)
    except Exception:
        pass


def _save_binding_extra_block_photo(setup: ProductSetup, block_index: int, field_name: str, uploaded_file) -> str:
    suffix = _BINDING_PHOTO_FILE_SUFFIX[field_name]
    ext = os.path.splitext(getattr(uploaded_file, "name", "") or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".jpg"
    storage_path = f"products/setup_bindings/setup_{setup.pk}_extra_{block_index}_{suffix}{ext}"
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    saved_path = default_storage.save(storage_path, uploaded_file)
    return default_storage.url(saved_path)


def _safe_binding_extra_blocks_from_json(raw: str) -> list[dict]:
    s = (raw or "").strip()
    if not s:
        return []
    try:
        data = json.loads(s)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data[:_MAX_BINDING_EXTRA_BLOCKS]:
        if not isinstance(item, dict):
            continue
        out.append(_binding_extra_block_item(item))
    return out


def _merge_binding_extra_block_photos(
    new_blocks: list[dict], old_blocks: list | None
) -> list[dict]:
    """Сохранить URL фото доп. блоков, если клиент не передал их при inline-сохранении."""
    old_list = old_blocks if isinstance(old_blocks, list) else []
    merged: list[dict] = []
    photo_fields = ("binding_x_photo", "binding_y_photo", "binding_z_photo")
    for i, blk in enumerate(new_blocks):
        item = dict(blk)
        if i < len(old_list) and isinstance(old_list[i], dict):
            for pf in photo_fields:
                if not (item.get(pf) or "").strip() and (old_list[i].get(pf) or "").strip():
                    item[pf] = str(old_list[i][pf])[:500]
        merged.append(_binding_extra_block_item(item))
    return merged


def _pdf_binding_block_dict(
    *,
    label: str,
    binding_x: str,
    binding_y: str,
    binding_z: str,
    gcode_system: str,
) -> dict:
    bx = (binding_x or "").strip() or "—"
    by = (binding_y or "").strip() or "—"
    bz = (binding_z or "").strip() or "—"
    gc = normalize_product_setup_gcode_system((gcode_system or "").strip() or "G54")
    is_empty = bx == "—" and by == "—" and bz == "—" and gc in ("G54", "")
    return {
        "label": label,
        "binding_x": bx,
        "binding_y": by,
        "binding_z": bz,
        "gcode_system": gc or "G54",
        "is_empty": is_empty,
    }


def _pdf_binding_blocks_for_setup(setup: ProductSetup) -> list[dict]:
    blocks: list[dict] = [
        _pdf_binding_block_dict(
            label="Основная",
            binding_x=setup.binding_x,
            binding_y=setup.binding_y,
            binding_z=setup.binding_z,
            gcode_system=setup.gcode_system,
        )
    ]
    raw = setup.binding_extra_blocks
    if not isinstance(raw, list):
        return blocks
    extra_index = 0
    for item in raw[:_MAX_BINDING_EXTRA_BLOCKS]:
        if not isinstance(item, dict):
            continue
        extra_index += 1
        blk = _pdf_binding_block_dict(
            label=f"Доп. {extra_index}",
            binding_x=str(item.get("binding_x") or ""),
            binding_y=str(item.get("binding_y") or ""),
            binding_z=str(item.get("binding_z") or ""),
            gcode_system=str(item.get("gcode_system") or "G54"),
        )
        if not blk["is_empty"]:
            blocks.append(blk)
    return blocks


def _binding_extra_blocks_template_rows(setup: ProductSetup) -> list[dict]:
    raw_list = setup.binding_extra_blocks
    if not isinstance(raw_list, list):
        return []
    rows: list[dict] = []
    for item in raw_list[:_MAX_BINDING_EXTRA_BLOCKS]:
        if not isinstance(item, dict):
            continue
        gc = normalize_product_setup_gcode_system(str(item.get("gcode_system") or "G54"))
        sel, pnum = product_setup_gcode_inline_parts(gc)
        rows.append(
            {
                "binding_x": str(item.get("binding_x") or "")[:64],
                "binding_y": str(item.get("binding_y") or "")[:64],
                "binding_z": str(item.get("binding_z") or "")[:64],
                "gcode_system": gc,
                "gcode_inline_select_value": sel,
                "gcode_inline_p_number": pnum,
                "binding_x_photo": str(item.get("binding_x_photo") or "")[:500],
                "binding_y_photo": str(item.get("binding_y_photo") or "")[:500],
                "binding_z_photo": str(item.get("binding_z_photo") or "")[:500],
            }
        )
    return rows


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


def _product_drawing_files_qs(product: Product):
    return product.drawing_files.order_by("sort_order", "id")


def _append_product_drawing_file(product: Product, uploaded_file) -> ProductDrawingFile:
    if not uploaded_file:
        raise ValueError("empty file")
    raw_name = (getattr(uploaded_file, "name", "") or "").replace("\\", "/").rsplit("/", 1)[-1]
    ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    if ext != "pdf":
        raise ValueError("pdf required")
    last = _product_drawing_files_qs(product).aggregate(m=Max("sort_order"))["m"]
    n = (last if last is not None else -1) + 1
    base = raw_name or f"drawing_{uuid.uuid4().hex[:10]}.pdf"
    row = ProductDrawingFile(
        product=product,
        sort_order=n,
        original_filename=base[:255],
    )
    row.save()
    row.file.save(base, uploaded_file, save=True)
    product.save(update_fields=["updated_at"])
    return row


def _drawing_files_payload(product: Product) -> dict:
    files_out = []
    for row in _product_drawing_files_qs(product):
        if not row.file:
            continue
        files_out.append(
            {
                "id": row.pk,
                "url": row.file.url,
                "name": row.display_name,
                "title": row.download_title,
            }
        )
    return {"drawing_files": files_out}


def _product_osnastka_links_qs(product: Product):
    return ProductOsnastkaUsage.objects.filter(product=product).select_related("osnastka").order_by(
        "sort_order", "id"
    )


def _product_osnastka_links_payload(product: Product) -> list[dict]:
    out = []
    for link in _product_osnastka_links_qs(product):
        name = (link.osnastka.name or "").strip() or f"#{link.osnastka_id}"
        out.append(
            {
                "id": link.pk,
                "osnastka_id": link.osnastka_id,
                "name": name,
                "url": reverse("osnastka_detail", kwargs={"pk": link.osnastka_id}),
            }
        )
    return out


def _osnastka_catalog_options(*, linked_ids: set[int]) -> list[dict]:
    qs = Product.objects.filter(catalog_section=Product.CATALOG_OSNASTKA).order_by("name", "id")
    if linked_ids:
        qs = qs.exclude(pk__in=linked_ids)
    return [
        {"id": row.pk, "name": (row.name or "").strip() or f"#{row.pk}"}
        for row in qs
    ]


def _product_osnastka_payload(product: Product) -> dict:
    linked_ids = set(_product_osnastka_links_qs(product).values_list("osnastka_id", flat=True))
    return {
        "osnastka_links": _product_osnastka_links_payload(product),
        "osnastka_options": _osnastka_catalog_options(linked_ids=linked_ids),
    }


def _product_osnastka_usage_json(product: Product) -> dict:
    out = _product_osnastka_payload(product)
    out["ok"] = True
    return out


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


# ─── Файловый менеджер для древа изделий ───────────────────────────────────────


def get_all_product_files(product_id: int) -> dict:
    """
    Получить иерархический список всех файлов изделия с группировкой по наладкам.

    Возвращает:
    {
        'product_root': [ProductFile, ...],  # Файлы уровня изделия
        'setups': [
            {'setup': ProductSetup, 'files': [ProductFile, ...]},
            ...
        ]
    }
    """
    product = get_object_or_404(Product, id=product_id)

    # Файлы уровня изделия (setup=null)
    root_files = list(ProductFile.objects.filter(product_id=product_id, setup__isnull=True).order_by("sort_order", "id"))

    # Файлы по наладкам
    setups_with_files = []
    for setup in _product_setups_qs(product):
        setup_files = list(ProductFile.objects.filter(setup_id=setup.id).order_by("sort_order", "id"))
        setups_with_files.append({
            "setup": setup,
            "files": setup_files,
        })

    return {
        "product_root": root_files,
        "setups": setups_with_files,
    }


def upload_product_file(file_obj, product_id: int, setup_id: int | None = None, file_type: str = "custom") -> ProductFile:
    """
    Загрузить файл в изделие (уровень изделия или конкретной наладки).

    Args:
        file_obj: Django UploadedFile object
        product_id: ID изделия
        setup_id: ID наладки (опционально, если None — файл уровня изделия)
        file_type: Тип файла (default: 'custom')

    Returns:
        ProductFile instance
    """
    product = get_object_or_404(Product, id=product_id)
    setup = None
    if setup_id:
        setup = get_object_or_404(ProductSetup, id=setup_id, product_id=product_id)

    # Получить отображаемое имя (без пути)
    file_name = getattr(file_obj, 'name', 'file')
    if '/' in file_name:
        file_name = file_name.rsplit('/', 1)[-1]

    # Создать ProductFile
    pf = ProductFile(
        product=product,
        setup=setup,
        file_type=file_type,
        file=file_obj,
        file_name=file_name,
        sort_order=0,
    )
    pf.save()

    return pf


def delete_product_file(file_id: int) -> bool:
    """
    Удалить файл изделия.

    Args:
        file_id: ID ProductFile

    Returns:
        True if deleted, False if not found
    """
    try:
        pf = ProductFile.objects.get(id=file_id)
        if pf.file:
            # Удалить физический файл
            if hasattr(pf.file, 'delete') and hasattr(pf.file.storage, 'delete'):
                pf.file.delete()
        pf.delete()
        return True
    except ProductFile.DoesNotExist:
        return False


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
            "gcode_system": forms.TextInput(
                attrs={
                    "maxlength": 24,
                    "placeholder": "G54 … G59 или G54.1 P10",
                }
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
            "cad_step_model": forms.FileInput(attrs={"accept": ".stp,.step"}),
        }

    def clean_gcode_system(self) -> str:
        return normalize_product_setup_gcode_system(self.cleaned_data.get("gcode_system", ""))


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
    extra=32,
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

# Диаметр резьбы обозначаем префиксом M (а не ⌀), как для метчика.
_SETUP_TOOL_TYPES_METRIC_THREAD = frozenset({"Метчик", "Раскатник", "Резьбофреза"})


def _is_simple_diameter_value(s: str) -> bool:
    """Только размер/число (опционально ⌀/D и мм), без произвольного текста вроде «Шарик …»."""
    t = (s or "").strip()
    if not t:
        return False
    if re.match(r"^[mM]\d", t):
        return True
    if re.match(r"^(?:[⌀ØφΦ]\s*)?[\d.,]+(?:\s*(?:мм|mm))?\s*$", t, re.IGNORECASE):
        return True
    return bool(re.match(r"^[dD]\d", t))


def _looks_like_descriptive_diameter(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    if re.match(r"^[mM]\d", t):
        return False
    return not _is_simple_diameter_value(t)


def _format_tap_diameter_display(raw: str) -> str:
    u = (raw or "").strip()
    if not u:
        return ""
    while True:
        v = u.lstrip()
        if v.startswith(("⌀", "Ø", "φ", "Φ")):
            u = v[1:].lstrip()
            continue
        md = re.match(r"^[dD](\d.*)$", v)
        if md:
            u = md.group(1).strip()
            continue
        break
    u = u.strip()
    if not u:
        return ""
    if re.match(r"^[mM]", u):
        return "M" + u[1:].lstrip()
    return "M" + u


def _format_diameter_other_display(raw: str) -> str:
    """Тип «Другое»: не добавляем ⌀/M — только снимаем уже стоящие в начале знаки диаметра."""
    u = (raw or "").strip()
    if not u:
        return ""
    t = u
    while True:
        v = t.lstrip()
        if v.startswith(("⌀", "Ø", "φ", "Φ")):
            t = v[1:].lstrip()
            continue
        md = re.match(r"^[dD](\d.*)$", v)
        if md:
            t = md.group(1).strip()
            continue
        break
    return t.strip()


def _format_tool_diameter_display(raw: str, tool_type: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if (tool_type or "").strip() == "Другое":
        return _format_diameter_other_display(s)
    if (tool_type or "").strip() in _SETUP_TOOL_TYPES_METRIC_THREAD:
        return _format_tap_diameter_display(s)
    if re.match(r"^[mM]\d", s):
        return s
    if _looks_like_descriptive_diameter(s):
        return s
    t = s
    while True:
        v = t.lstrip()
        if v.startswith(("⌀", "Ø", "φ", "Φ")):
            t = v[1:].lstrip()
            continue
        md = re.match(r"^[dD](\d.*)$", v)
        if md:
            t = md.group(1).strip()
            continue
        break
    t = t.strip()
    return ("⌀" + t) if t else "⌀"


def _format_tool_overhang_display(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    base = re.sub(r"\s*(?:мм|mm)\s*$", "", s, flags=re.IGNORECASE).strip()
    return f"{base} мм" if base else ""


def _normalize_tool_diameter_for_storage(raw: str, tool_type: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if _looks_like_descriptive_diameter(s):
        return s
    if (tool_type or "").strip() == "Другое":
        return _format_diameter_other_display(s)
    if (tool_type or "").strip() in _SETUP_TOOL_TYPES_METRIC_THREAD:
        return _format_tap_diameter_display(s).replace(" ", "")
    d = _format_tool_diameter_display(s, tool_type)
    if d.startswith("⌀"):
        return d[1:].strip()
    return d


def _normalize_tool_overhang_for_storage(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    return re.sub(r"\s*(?:мм|mm)\s*$", "", s, flags=re.IGNORECASE).strip()


def _normalize_tool_number(raw: str) -> str:
    src = (raw or "").strip().upper()
    if not src:
        return ""
    m = re.match(r"^(?:T\s*)?(\d{1,4})$", src)
    if not m:
        return src
    n = int(m.group(1), 10)
    if n < 100:
        return f"T{n:02d}"
    return f"T{n}"


def _tool_row_sort_key(row: ProductSetupToolRow) -> tuple:
    """Порядок строк в UI и при сохранении: по нормализованному № (T01…), затем по id."""
    raw = (row.tool_number or "").strip()
    norm = _normalize_tool_number(raw)
    if norm.startswith("T") and len(norm) > 1:
        suf = norm[1:]
        if suf.isdigit():
            return (0, int(suf, 10), row.pk)
    if norm:
        return (1, norm.upper(), row.pk)
    return (2, "", row.pk)


def _tool_row_dict_sort_tuple(row: dict) -> tuple:
    tn = str((row.get("tool_number") or "")).strip()
    norm = _normalize_tool_number(tn)
    if norm.startswith("T") and len(norm) > 1 and norm[1:].isdigit():
        return (0, int(norm[1:], 10))
    if norm:
        return (1, norm.upper())
    return (2, "")


def _default_tool_number_list() -> list[str]:
    """Слоты по умолчанию на карточке и в форме: T01–T24 (без T00 / T99)."""
    return [f"T{n:02d}" for n in range(1, 25)]


def _expected_correctors(tool_no: str) -> tuple[str, str]:
    norm = _normalize_tool_number(tool_no)
    if not norm.startswith("T") or len(norm) < 2:
        return "", ""
    suffix = norm[1:].zfill(2)
    return f"H{suffix}", f"D{suffix}"


def _formset_initial_dict_from_db_row(row: ProductSetupToolRow) -> dict:
    raw_tn = (row.tool_number or "").strip()
    norm = _normalize_tool_number(raw_tn)
    if norm.startswith("T"):
        rest = norm[1:]
        if rest.isdigit():
            form_tn = str(int(rest, 10))
        else:
            form_tn = raw_tn
    else:
        form_tn = raw_tn
    return {
        "tool_number": form_tn,
        "kor_n": row.kor_n or "",
        "kor_d": row.kor_d or "",
        "tool_type": row.tool_type or "",
        "tap_hole_type": row.tap_hole_type or "",
        "name": row.name or "",
        "diameter": row.diameter or "",
        "overhang": row.overhang or "",
    }


def _build_formset_initial_for_setup_edit(existing_rows: list[ProductSetupToolRow]) -> list[dict]:
    ordered = sorted(existing_rows, key=_tool_row_sort_key)
    if not ordered:
        return _build_default_tool_rows(None)
    return [_formset_initial_dict_from_db_row(r) for r in ordered]


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
            default_row["diameter"] = "Шарик ⌀6 мм"
        out.append(default_row)
    return out


def _display_dict_from_tool_row(row: ProductSetupToolRow) -> dict:
    raw_tn = (row.tool_number or "").strip()
    norm = _normalize_tool_number(raw_tn)
    display_tn = norm if norm else raw_tn
    exp_h, exp_d = _expected_correctors(display_tn)
    cur_h = (row.kor_n or "").strip()
    cur_d = (row.kor_d or "").strip()
    cur_h_up = cur_h.upper()
    cur_d_up = cur_d.upper()
    exp_h_up = (exp_h or "").strip().upper()
    exp_d_up = (exp_d or "").strip().upper()
    tt = row.tool_type or ""
    kor_n_override = bool(exp_h_up and cur_h_up and cur_h_up != exp_h_up)
    kor_d_override = bool(exp_d_up and cur_d_up and cur_d_up != exp_d_up)
    # В карточке не показываем «лишние» H/D, совпадающие с номером T — только отличия (override) или пусто
    kor_n_show = "" if (exp_h_up and cur_h_up == exp_h_up) else cur_h
    kor_d_show = "" if (exp_d_up and cur_d_up == exp_d_up) else cur_d
    return {
        "id": row.pk,
        "tool_number": display_tn,
        "correction_enabled": bool(row.correction_enabled),
        "kor_n": kor_n_show,
        "kor_d": kor_d_show,
        "tool_type": tt,
        "tap_hole_type": row.tap_hole_type or "",
        "diameter": _format_tool_diameter_display(row.diameter or "", tt),
        "overhang": _format_tool_overhang_display(row.overhang or ""),
        "note": row.name or "",
        "photo_url": row.photo.url if row.photo else "",
        "kor_n_override": kor_n_override,
        "kor_d_override": kor_d_override,
    }


def _build_display_tool_rows(existing_rows: list[ProductSetupToolRow] | None = None) -> list[dict]:
    existing_rows = existing_rows or []
    ordered = sorted(existing_rows, key=_tool_row_sort_key)
    if not ordered:
        out: list[dict] = []
        for tool_no in _default_tool_number_list():
            default_row = {
                "id": None,
                "tool_number": tool_no,
                "correction_enabled": False,
                "kor_n": "",
                "kor_d": "",
                "tool_type": "",
                "tap_hole_type": "",
                "diameter": "",
                "overhang": "",
                "note": "",
                "photo_url": "",
                "kor_n_override": False,
                "kor_d_override": False,
            }
            if tool_no == "T20":
                default_row["tool_type"] = "Датчик привязки"
                default_row["diameter"] = _format_tool_diameter_display(
                    "Шарик ⌀6 мм", default_row["tool_type"]
                )
            out.append(default_row)
        return out
    return [_display_dict_from_tool_row(r) for r in ordered]


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET", "HEAD"])
def products_list_view(request):
    q = (request.GET.get("q") or "").strip()
    qs = _products_qs_for_catalog(Product.CATALOG_NALADKI)
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
@require_http_methods(["GET", "HEAD"])
def osnastka_list_view(request):
    q = (request.GET.get("q") or "").strip()
    qs = _products_qs_for_catalog(Product.CATALOG_OSNASTKA)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    paginator = Paginator(qs, 24)
    page = paginator.get_page(request.GET.get("page") or 1)
    return render(
        request,
        "shifts/osnastka_list.html",
        {
            "products_page": page,
            "search_q": q,
            "username": biota_user(request),
        },
    )


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["POST"])
def product_delete_view(request, pk: int):
    """Удаление карточки наладки — только администратор (Biota)."""
    u = biota_user(request)
    if not _is_admin(u):
        messages.error(request, "Удалять наладки может только администратор.")
        return redirect("products_list")
    product = get_object_or_404(Product, pk=pk)
    nm = (product.name or "").strip() or f"#{pk}"
    list_url = _product_list_url_name(product)
    product.delete()
    messages.success(request, f"Наладка «{nm}» удалена.")
    nxt = (request.POST.get("next") or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(list_url)


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
    binding_blocks = _pdf_binding_blocks_for_setup(setup)
    setup_notes_html = (setup.setup_notes or "").strip()
    product_comment_notes = list(
        ProductNote.objects.filter(product=product, setup__isnull=True).order_by("created_at", "id")
    )
    setup_comment_notes = list(
        ProductNote.objects.filter(product=product, setup=setup).order_by("created_at", "id")
    )
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
            "binding_blocks": binding_blocks,
            "setup_notes_html": setup_notes_html,
            "product_comment_notes": product_comment_notes,
            "setup_comment_notes": setup_comment_notes,
            "username": biota_user(request),
        },
    )


NEW_PRODUCT_NAME_BASE = "Новая наладка"
NEW_OSNASTKA_NAME_BASE = "Новая оснастка"
NEW_PRODUCT_DEFAULT_WORKPIECE = "preparatory"


def _allocate_new_product_name(base: str = NEW_PRODUCT_NAME_BASE) -> str:
    name = base
    n = 2
    while Product.objects.filter(name__iexact=name).exists():
        name = f"{base} {n}"
        n += 1
    return name


def create_product_with_defaults(*, catalog_section: str | None = None) -> Product:
    """Новая карточка: изделие в «Наладках» или «Оснастках», первая установка."""
    section = catalog_section or Product.CATALOG_NALADKI
    name_base = NEW_OSNASTKA_NAME_BASE if section == Product.CATALOG_OSNASTKA else NEW_PRODUCT_NAME_BASE
    with transaction.atomic():
        product = Product.objects.create(
            name=_allocate_new_product_name(name_base),
            description="",
            drawing_blank_size="",
            drawing_blank_type="",
            card_product_type="made",
            card_workpiece_type=NEW_PRODUCT_DEFAULT_WORKPIECE,
            catalog_section=section,
        )
        ProductSetup.objects.create(
            product=product,
            name="Установка 1",
            sort_order=0,
        )
    return product


@biota_login_required
@nav_permission_required("products")
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_create_view(request):
    product = create_product_with_defaults()
    messages.success(request, "Создана новая наладка — заполните карточку изделия.")
    base = _product_detail_url(product)
    return redirect(f"{base}?{urlencode({'tab': 'drawing', 'quick_edit': '1'})}")


@biota_login_required
@nav_permission_required("products")
@write_permission_required
@require_http_methods(["GET", "POST"])
def osnastka_create_view(request):
    product = create_product_with_defaults(catalog_section=Product.CATALOG_OSNASTKA)
    messages.success(request, "Создана новая оснастка — заполните карточку.")
    base = _product_detail_url(product)
    return redirect(f"{base}?{urlencode({'tab': 'drawing', 'quick_edit': '1'})}")


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET", "HEAD", "POST"])
def product_edit_view(request, pk: int):
    """Отдельная форма редактирования изделия отключена — редирект на карточку наладки."""
    get_object_or_404(Product, pk=pk)
    return redirect("product_detail", pk=pk)


@biota_login_required
@nav_permission_required("products")
@require_http_methods(["GET"])
def product_name_suggestions_view(request):
    q = (request.GET.get("q") or "").strip()
    exclude_id_raw = (request.GET.get("exclude_id") or "").strip()
    exclude_id = int(exclude_id_raw) if exclude_id_raw.isdigit() else None
    if len(q) < 2:
        return JsonResponse({"ok": True, "items": []})

    qs = Product.objects.filter(catalog_section=Product.CATALOG_NALADKI)
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


def _post_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "on")


def _product_inline_update_setup(request, product: Product) -> JsonResponse:
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
    changed_setup_fields: list[str] = []
    for field in editable_fields:
        if field not in request.POST:
            continue
        raw = (request.POST.get(field) or "").strip()
        if field == "gcode_system":
            raw = normalize_product_setup_gcode_system(raw)
        setattr(setup, field, raw)
        changed_setup_fields.append(field)
    if "binding_extra_blocks_json" in request.POST:
        new_extra = _safe_binding_extra_blocks_from_json(
            request.POST.get("binding_extra_blocks_json") or "[]"
        )
        setup.binding_extra_blocks = _merge_binding_extra_block_photos(
            new_extra, getattr(setup, "binding_extra_blocks", None)
        )
        if "binding_extra_blocks" not in changed_setup_fields:
            changed_setup_fields.append("binding_extra_blocks")
    if changed_setup_fields:
        setup.save(update_fields=list(dict.fromkeys(changed_setup_fields + ["updated_at"])))
    product_meta_changed: list[str] = []
    if "product_name" in request.POST:
        nm = (request.POST.get("product_name") or "").strip()[:300]
        if not nm:
            return JsonResponse({"ok": False, "error": "Укажите название наладки."}, status=400)
        if Product.objects.filter(name__iexact=nm).exclude(pk=product.pk).exists():
            return JsonResponse(
                {"ok": False, "error": "Наладка с таким названием уже существует."},
                status=400,
            )
        if nm != (product.name or "").strip():
            product.name = nm
            product_meta_changed.append("name")
    if "product_description" in request.POST:
        desc = (request.POST.get("product_description") or "").strip()
        if desc != (product.description or "").strip():
            product.description = desc
            product_meta_changed.append("description")
    product_drawing_update: list[str] = []
    if "drawing_blank_size" in request.POST:
        product.drawing_blank_size = (request.POST.get("drawing_blank_size") or "").strip()[:180]
        product_drawing_update.append("drawing_blank_size")
    if "drawing_blank_type" in request.POST:
        product.drawing_blank_type = (request.POST.get("drawing_blank_type") or "").strip()[:220]
        product_drawing_update.append("drawing_blank_type")
    product_update_fields = list(dict.fromkeys(product_meta_changed + product_drawing_update))
    if product_update_fields:
        product.save(update_fields=product_update_fields + ["updated_at"])
    if product_meta_changed:
        ensure_plan_piece_for_naladki_product(product.pk)
    out_tool_rows = False
    rows_json = (request.POST.get("rows_json") or "").strip()
    if rows_json:
        try:
            rows = json.loads(rows_json)
        except Exception:
            return JsonResponse({"ok": False, "error": "Некорректные данные таблицы инструмента."}, status=400)
        if not isinstance(rows, list):
            return JsonResponse({"ok": False, "error": "Некорректный формат таблицы инструмента."}, status=400)
        parsed_rows: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_tool_number = str((row.get("tool_number") or "")).strip()
            row_correction_enabled = _post_bool(row.get("correction_enabled"))
            row_kor_n = str((row.get("kor_n") or "")).strip()
            row_kor_d = str((row.get("kor_d") or "")).strip()
            row_tool_type = str((row.get("tool_type") or "")).strip()
            row_diameter = _normalize_tool_diameter_for_storage(
                str((row.get("diameter") or "")).strip(), row_tool_type
            )
            row_overhang = _normalize_tool_overhang_for_storage(str((row.get("overhang") or "")).strip())
            row_note = str((row.get("note") or "")).strip()
            row_id_raw = row.get("id")
            row_id: int | None = None
            if row_id_raw is not None and str(row_id_raw).strip().isdigit():
                row_id = int(str(row_id_raw).strip())
            row_vals = (row_tool_number, row_kor_n, row_kor_d, row_tool_type, row_diameter, row_overhang, row_note)
            if all(v == "" for v in row_vals) and not row_correction_enabled:
                continue
            parsed_rows.append(
                {
                    "id": row_id,
                    "tool_number": row_tool_number,
                    "correction_enabled": row_correction_enabled,
                    "kor_n": row_kor_n,
                    "kor_d": row_kor_d,
                    "tool_type": row_tool_type,
                    "diameter": row_diameter,
                    "overhang": row_overhang,
                    "note": row_note,
                }
            )
        indexed = list(enumerate(parsed_rows))
        indexed.sort(key=lambda p: (_tool_row_dict_sort_tuple(p[1]), p[0]))
        existing_by_id = {r.pk: r for r in setup.tools.all()}
        kept_ids: list[int] = []
        for idx, (_, pr) in enumerate(indexed):
            row_id = pr.get("id")
            fields = {
                "sort_order": idx,
                "tool_number": pr["tool_number"],
                "correction_enabled": pr["correction_enabled"],
                "kor_n": pr["kor_n"],
                "kor_d": pr["kor_d"],
                "tool_type": pr["tool_type"],
                "diameter": pr["diameter"],
                "overhang": pr["overhang"],
                "tap_hole_type": "",
                "name": pr["note"],
            }
            if row_id and row_id in existing_by_id:
                obj = existing_by_id[row_id]
                for k, v in fields.items():
                    setattr(obj, k, v)
                obj.save()
                kept_ids.append(obj.pk)
            else:
                obj = ProductSetupToolRow.objects.create(setup=setup, **fields)
                kept_ids.append(obj.pk)
        for orphan in setup.tools.exclude(pk__in=kept_ids):
            if orphan.photo:
                try:
                    orphan.photo.delete(save=False)
                except Exception:
                    pass
            orphan.delete()
        out_tool_rows = True
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
            "binding_extra_blocks": _safe_binding_extra_blocks_from_json(
                json.dumps(getattr(setup, "binding_extra_blocks", None) or [])
            ),
        },
        "product_drawing": {
            "drawing_blank_size": (product.drawing_blank_size or "").strip() or "—",
            "drawing_blank_type": (product.drawing_blank_type or "").strip() or "—",
        },
        "product": {
            "name": (product.name or "").strip(),
            "description": (product.description or "").strip(),
        },
    }
    if out_tool_rows:
        out["tool_rows"] = _build_display_tool_rows(list(setup.tools.all()))
    if (request.POST.get("sync_plan_from_inline") or "").strip() == "1":
        plan_err = validate_product_plan_post(request.POST)
        if plan_err:
            out["plan_sync_error"] = plan_err
        else:
            perr = apply_product_plan_post(product, request.POST)
            if perr:
                out["plan_sync_error"] = perr
            else:
                out["plan_summary"] = plan_card_summary(product)
                out["specs_summary"] = out["plan_summary"]
                out["plan_inline_state"] = plan_inline_state_payload(product)
                out["specs_inline_state"] = out["plan_inline_state"]
    return JsonResponse(out)


@biota_login_required
@nav_permission_required("products")
@write_permission_required
@require_http_methods(["GET", "POST"])
def product_detail_view(request, pk: int):
    product = get_object_or_404(Product.objects.prefetch_related("drawing_files"), pk=pk)
    osnastka_route = getattr(request, "_osnastka_catalog_route", False)
    if osnastka_route and not product.is_osnastka:
        raise Http404("Карточка не найдена.")
    if product.is_osnastka and not osnastka_route:
        q = request.GET.urlencode()
        dest = reverse("osnastka_detail", kwargs={"pk": pk})
        return redirect(f"{dest}?{q}" if q else dest)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "create_setup":
            max_order = product.setups.aggregate(m=Max("sort_order"))["m"]
            next_order = (max_order + 1) if max_order is not None else 0
            n = product.setups.count() + 1
            setup = ProductSetup.objects.create(
                product=product,
                name=f"Установка {n}",
                sort_order=next_order,
            )
            messages.success(request, "Добавлена установка — заполните данные во вкладке.")
            tab_slug = f"setup-{setup.pk}"
            return redirect(f"{_product_detail_url(product)}?{urlencode({'tab': tab_slug})}")

        if action == "add_product_note":
            body = (request.POST.get("body") or "").strip()
            if not body:
                return JsonResponse({"ok": False, "error": "Введите текст заметки."}, status=400)
            if len(body) > 4000:
                return JsonResponse({"ok": False, "error": "Не более 4000 символов."}, status=400)
            author = (biota_user(request) or "").strip() or "?"
            setup = None
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            if setup_id_raw.isdigit():
                setup = ProductSetup.objects.filter(pk=int(setup_id_raw), product=product).first()
                if not setup:
                    return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=400)
            ProductNote.objects.create(
                product=product,
                setup=setup,
                author_username=author[:150],
                body=body,
            )
            return JsonResponse({"ok": True})

        if action == "delete_product_note":
            who = (biota_user(request) or "").strip()
            if not who:
                return JsonResponse({"ok": False, "error": "Не авторизован."}, status=401)
            note_id_raw = (request.POST.get("note_id") or "").strip()
            note_id = int(note_id_raw) if note_id_raw.isdigit() else 0
            if note_id <= 0:
                return JsonResponse({"ok": False, "error": "Не указана заметка."}, status=400)
            note = ProductNote.objects.filter(pk=note_id, product=product).first()
            if not note:
                return JsonResponse({"ok": False, "error": "Заметка не найдена."}, status=404)
            if not _is_admin(who) and (note.author_username or "").strip() != who:
                return JsonResponse({"ok": False, "error": "Нет прав на удаление."}, status=403)
            note.delete()
            return JsonResponse({"ok": True})

        if action == "inline_replace_product_asset":
            field_name = (request.POST.get("field_name") or "").strip()
            allowed = {"drawing_pdf", "cad_model", "cad_step_model", "preview_stl"}
            if field_name not in allowed:
                return JsonResponse({"ok": False, "error": "Некорректное поле файла."}, status=400)
            upload = request.FILES.get("file")
            if not upload:
                return JsonResponse({"ok": False, "error": "Выберите файл."}, status=400)
            raw_name = (upload.name or "").strip()
            ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
            if field_name == "drawing_pdf" and ext != "pdf":
                return JsonResponse({"ok": False, "error": "Для чертежа нужен файл PDF."}, status=400)
            if field_name == "cad_model" and ext not in ("stl", "stp", "step"):
                return JsonResponse(
                    {"ok": False, "error": "Для 3D-модели допустимы расширения STL, STP или STEP."},
                    status=400,
                )
            if field_name == "cad_step_model" and ext not in ("stp", "step"):
                return JsonResponse(
                    {"ok": False, "error": "Для отдельного STEP допустимы только STP или STEP."},
                    status=400,
                )
            if field_name == "preview_stl" and ext != "stl":
                return JsonResponse({"ok": False, "error": "Для предпросмотра нужен файл STL."}, status=400)
            old = getattr(product, field_name)
            if old:
                try:
                    old.delete(save=False)
                except Exception:
                    pass
            setattr(product, field_name, upload)
            product.save(update_fields=[field_name, "updated_at"])
            new_f = getattr(product, field_name)
            return JsonResponse({"ok": True, "field": field_name, "url": new_f.url if new_f else ""})

        if action in ("inline_save_product_plan", "inline_save_product_specs"):
            plan_err = validate_product_plan_post(request.POST)
            if plan_err:
                return JsonResponse({"ok": False, "error": plan_err}, status=400)
            err = apply_product_plan_post(product, request.POST)
            if err:
                return JsonResponse({"ok": False, "error": err}, status=400)
            summary = plan_card_summary(product)
            state = plan_inline_state_payload(product)
            return JsonResponse(
                {
                    "ok": True,
                    "plan_summary": summary,
                    "specs_summary": summary,
                    "plan_inline_state": state,
                    "specs_inline_state": state,
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

        if action == "inline_replace_tool_row_photo":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            tool_row_id_raw = (request.POST.get("tool_row_id") or "").strip()
            tool_row_id = int(tool_row_id_raw) if tool_row_id_raw.isdigit() else 0
            tool_row = ProductSetupToolRow.objects.filter(pk=tool_row_id, setup=setup).first()
            if not tool_row:
                return JsonResponse({"ok": False, "error": "Строка инструмента не найдена."}, status=404)
            image_file = request.FILES.get("image")
            if not image_file:
                return JsonResponse({"ok": False, "error": "Выберите фото."}, status=400)
            if tool_row.photo:
                try:
                    tool_row.photo.delete(save=False)
                except Exception:
                    pass
            tool_row.photo = image_file
            tool_row.save(update_fields=["photo"])
            return JsonResponse(
                {"ok": True, "url": tool_row.photo.url if tool_row.photo else "", "tool_row_id": tool_row.pk}
            )

        if action == "inline_delete_tool_row_photo":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            tool_row_id_raw = (request.POST.get("tool_row_id") or "").strip()
            tool_row_id = int(tool_row_id_raw) if tool_row_id_raw.isdigit() else 0
            tool_row = ProductSetupToolRow.objects.filter(pk=tool_row_id, setup=setup).first()
            if not tool_row:
                return JsonResponse({"ok": False, "error": "Строка инструмента не найдена."}, status=404)
            if tool_row.photo:
                try:
                    tool_row.photo.delete(save=False)
                except Exception:
                    pass
                tool_row.photo = ""
                tool_row.save(update_fields=["photo"])
            return JsonResponse({"ok": True, "tool_row_id": tool_row.pk})

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
            extra_index_raw = (request.POST.get("extra_block_index") or "").strip()
            if extra_index_raw != "":
                if field_name not in _BINDING_EXTRA_PHOTO_FIELDS:
                    return JsonResponse({"ok": False, "error": "Некорректное поле фото."}, status=400)
                try:
                    extra_index = int(extra_index_raw)
                except ValueError:
                    return JsonResponse({"ok": False, "error": "Некорректный блок привязки."}, status=400)
                if extra_index < 0 or extra_index >= _MAX_BINDING_EXTRA_BLOCKS:
                    return JsonResponse({"ok": False, "error": "Некорректный блок привязки."}, status=400)
                blocks = [
                    _binding_extra_block_item(b)
                    for b in (setup.binding_extra_blocks or [])
                    if isinstance(b, dict)
                ]
                while len(blocks) <= extra_index:
                    blocks.append(_binding_extra_block_item({}))
                old_url = blocks[extra_index].get(field_name) or ""
                _delete_stored_media_url(old_url)
                new_url = _save_binding_extra_block_photo(setup, extra_index, field_name, image_file)
                blocks[extra_index][field_name] = new_url
                setup.binding_extra_blocks = blocks[:_MAX_BINDING_EXTRA_BLOCKS]
                setup.save(update_fields=["binding_extra_blocks", "updated_at"])
                return JsonResponse({"ok": True, "url": new_url, "extra_block_index": extra_index})
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

        if action == "inline_append_product_drawing":
            drawing_file = request.FILES.get("drawing_file")
            if not drawing_file:
                return JsonResponse({"ok": False, "error": "Выберите PDF-файл."}, status=400)
            try:
                _append_product_drawing_file(product, drawing_file)
            except ValueError:
                return JsonResponse({"ok": False, "error": "Для чертежа нужен файл PDF."}, status=400)
            except Exception:
                return JsonResponse({"ok": False, "error": "Не удалось сохранить чертёж."}, status=400)
            out = _drawing_files_payload(product)
            out["ok"] = True
            return JsonResponse(out)

        if action == "inline_delete_product_drawing_file":
            fid_raw = (request.POST.get("drawing_file_id") or "").strip()
            fid = int(fid_raw) if fid_raw.isdigit() else 0
            row = ProductDrawingFile.objects.filter(pk=fid, product=product).first()
            if not row:
                return JsonResponse({"ok": False, "error": "Файл не найден."}, status=404)
            row.delete()
            product.save(update_fields=["updated_at"])
            out = _drawing_files_payload(product)
            out["ok"] = True
            return JsonResponse(out)

        if action == "product_add_osnastka":
            if product.is_osnastka:
                return JsonResponse({"ok": False, "error": "Недоступно для карточки оснастки."}, status=400)
            osn_raw = (request.POST.get("osnastka_id") or "").strip()
            osn_id = int(osn_raw) if osn_raw.isdigit() else 0
            if osn_id <= 0:
                return JsonResponse({"ok": False, "error": "Выберите оснастку."}, status=400)
            if osn_id == product.pk:
                return JsonResponse({"ok": False, "error": "Нельзя указать эту же карточку."}, status=400)
            osnastka = Product.objects.filter(pk=osn_id, catalog_section=Product.CATALOG_OSNASTKA).first()
            if not osnastka:
                return JsonResponse({"ok": False, "error": "Оснастка не найдена."}, status=404)
            if ProductOsnastkaUsage.objects.filter(product=product, osnastka=osnastka).exists():
                return JsonResponse({"ok": False, "error": "Эта оснастка уже указана."}, status=400)
            last = _product_osnastka_links_qs(product).aggregate(m=Max("sort_order"))["m"]
            next_order = (last + 1) if last is not None else 0
            try:
                ProductOsnastkaUsage.objects.create(
                    product=product,
                    osnastka=osnastka,
                    sort_order=next_order,
                )
            except IntegrityError:
                return JsonResponse({"ok": False, "error": "Эта оснастка уже указана."}, status=400)
            product.save(update_fields=["updated_at"])
            return JsonResponse(_product_osnastka_usage_json(product))

        if action == "product_remove_osnastka":
            if product.is_osnastka:
                return JsonResponse({"ok": False, "error": "Недоступно для карточки оснастки."}, status=400)
            link_id_raw = (request.POST.get("link_id") or "").strip()
            link_id = int(link_id_raw) if link_id_raw.isdigit() else 0
            if link_id <= 0:
                return JsonResponse({"ok": False, "error": "Не указана связь."}, status=400)
            row = ProductOsnastkaUsage.objects.filter(pk=link_id, product=product).first()
            if not row:
                return JsonResponse({"ok": False, "error": "Связь не найдена."}, status=404)
            row.delete()
            product.save(update_fields=["updated_at"])
            return JsonResponse(_product_osnastka_usage_json(product))

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
            row.delete()
            setup.save(update_fields=["updated_at"])
            out = _program_files_payload(setup)
            out["ok"] = True
            return JsonResponse(out)

        if action == "inline_update_setup":
            try:
                return _product_inline_update_setup(request, product)
            except Exception as save_exc:
                return JsonResponse(
                    {"ok": False, "error": f"Ошибка сохранения: {save_exc}"},
                    status=500,
                )

        if action == "inline_toggle_setup_in_work":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            if "in_work" in request.POST:
                setup.in_work = _post_bool(request.POST.get("in_work"))
            else:
                setup.in_work = not setup.in_work
            setup.save(update_fields=["in_work", "updated_at"])
            setups = list(_product_setups_qs(product))
            return JsonResponse(
                {
                    "ok": True,
                    "setup_id": setup.pk,
                    "in_work": setup.in_work,
                    "setup_order": [
                        {
                            "pk": s.pk,
                            "tab_slug": f"setup-{s.pk}",
                            "name": (s.name or "").strip() or "без названия",
                            "in_work": s.in_work,
                        }
                        for s in setups
                    ],
                }
            )

        if action == "list_piece_norms":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = ProductSetup.objects.filter(pk=setup_id, product=product).first()
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            entries = [
                _piece_norm_entry_dict(e)
                for e in setup.piece_norms.order_by("-created_at", "-id")[:50]
            ]
            return JsonResponse({"ok": True, "setup_id": setup.pk, "entries": entries})

        if action == "list_machine_codes":
            return JsonResponse({"ok": True, "machines": list_machine_codes()})

        if action == "assign_setup_to_machine":
            setup_id_raw = (request.POST.get("setup_id") or "").strip()
            machine_code = (request.POST.get("machine_code") or "").strip()
            setup_id = int(setup_id_raw) if setup_id_raw.isdigit() else 0
            setup = (
                ProductSetup.objects.filter(pk=setup_id, product=product)
                .prefetch_related("tools")
                .first()
            )
            if not setup:
                return JsonResponse({"ok": False, "error": "Установка не найдена."}, status=404)
            result = assign_product_setup_to_machine(
                machine_code=machine_code,
                product=product,
                setup=setup,
            )
            if not result.get("ok"):
                return JsonResponse(result, status=400)
            result["machines_url"] = reverse("machines")
            return JsonResponse(result)

        return JsonResponse({"ok": False, "error": "Неизвестное действие."}, status=400)
    setup_photos = list(product.setup_photos.filter(setup__isnull=True))
    product.drawing_file_list = list(_product_drawing_files_qs(product))
    product.has_any_drawing = bool(product.drawing_file_list)
    setups = list(_product_setups_qs(product).prefetch_related("tools", "program_files"))
    for setup in setups:
        setup.tab_slug = f"setup-{setup.pk}"
        setup.side_notes = list(
            ProductNote.objects.filter(product=product, setup=setup).order_by("created_at", "id")
        )
        prim_pf = _setup_primary_program_field(setup)
        setup.program_text, setup.program_too_large = _read_program_file_for_display(prim_pf)
        setup.program_file_list = list(_setup_program_files_qs(setup))
        setup.has_any_program = bool(setup.program_file_list) or bool(setup.program_file)
        setup.primary_program_url = prim_pf.url if prim_pf else ""
        setup.primary_program_filename = os.path.basename(prim_pf.name) if prim_pf else ""
        setup.tool_rows = list(setup.tools.all())
        setup.tool_display_rows = _build_display_tool_rows(setup.tool_rows)
        setup.binding_extra_blocks_tpl = _binding_extra_blocks_template_rows(setup)
    piece_norms_latest = _latest_piece_norms_by_setup([s.pk for s in setups])
    for setup in setups:
        setup.latest_piece_norm = piece_norms_latest.get(setup.pk)
    has_setup_preview_stl = any(bool(getattr(s, "preview_stl", None)) for s in setups)
    cad_name = (product.cad_model.name or "") if product.cad_model else ""
    cad_ext = _cad_ext(cad_name)
    cad_step_name = (product.cad_step_model.name or "") if product.cad_step_model else ""
    cad_step_ext = _cad_ext(cad_step_name)
    cad_is_step = cad_ext in ("step", "stp")
    preview_stl_url = ""
    if product.preview_stl:
        preview_stl_url = product.preview_stl.url
    elif product.cad_model and cad_ext == "stl":
        preview_stl_url = product.cad_model.url
    cad_inline_preview = bool(preview_stl_url)
    program_text, program_too_large = _read_program_file_for_display(product.program_file)
    tab_default = (request.GET.get("tab") or "drawing").strip() or "drawing"
    setup_slugs = {s.tab_slug for s in setups}
    if tab_default not in ({"drawing"} | setup_slugs):
        tab_default = "drawing"
    active_setup = None
    if tab_default.startswith("setup-"):
        for setup in setups:
            if setup.tab_slug == tab_default:
                active_setup = setup
                break
    inspection_ctx = None
    return render(
        request,
        "shifts/product_detail.html",
        {
            "product": product,
            "product_self_url": _product_detail_url(product),
            **plan_form_context(product),
            "setup_photos": setup_photos,
            "setups": setups,
            "cad_ext": cad_ext,
            "cad_step_ext": cad_step_ext,
            "cad_is_stl": cad_ext == "stl",
            "cad_is_step": cad_is_step,
            "preview_stl_url": preview_stl_url,
            "cad_inline_preview": cad_inline_preview,
            "has_setup_preview_stl": has_setup_preview_stl,
            "program_text": program_text,
            "program_too_large": program_too_large,
            "tab_default": tab_default,
            "active_setup": active_setup,
            "piece_norms_json": json.dumps(
                {str(k): v for k, v in piece_norms_latest.items()},
                ensure_ascii=False,
            ),
            "tool_type_choices": SETUP_TOOL_TYPE_CHOICES,
            "username": biota_user(request),
            "product_notes": list(
                product.notes.filter(setup__isnull=True).order_by("created_at", "id")
            ),
            "product_osnastka_links": _product_osnastka_links_qs(product) if not product.is_osnastka else [],
            "osnastka_catalog_options": (
                _osnastka_catalog_options(
                    linked_ids=set(
                        _product_osnastka_links_qs(product).values_list("osnastka_id", flat=True)
                    )
                )
                if not product.is_osnastka
                else []
            ),
            "show_inspection_link": not product.is_osnastka and bool(setups),
            "machine_codes": list_machine_codes(),
        },
    )


@biota_login_required
@nav_permission_required("products")
@write_permission_required
@require_http_methods(["GET", "POST"])
def osnastka_detail_view(request, pk: int):
    request._osnastka_catalog_route = True
    return product_detail_view(request, pk)


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
                row_tt = cd.get("tool_type") or ""
                ProductSetupToolRow.objects.create(
                    setup=saved_setup,
                    sort_order=idx,
                    tool_number=cd.get("tool_number") or "",
                    kor_n=cd.get("kor_n") or "",
                    kor_d=cd.get("kor_d") or "",
                    tool_type=row_tt,
                    tap_hole_type=cd.get("tap_hole_type") or "",
                    name=cd.get("name") or "",
                    diameter=_normalize_tool_diameter_for_storage(cd.get("diameter") or "", row_tt),
                    overhang=_normalize_tool_overhang_for_storage(cd.get("overhang") or ""),
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
            initial=_build_formset_initial_for_setup_edit(list(setup.tools.all())),
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
