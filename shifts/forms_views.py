"""Раздел «Формы» — конструктор печатных бланков A4."""
import json
import os
import re
import uuid

from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .auth_utils import biota_login_required, biota_user, nav_permission_required, write_permission_required
from .models import PrintForm

MAX_FORMS = 200
MAX_ELEMENTS = 200
MAX_PAGES = 20
MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
VALID_ORIENTATIONS = {PrintForm.ORIENTATION_PORTRAIT, PrintForm.ORIENTATION_LANDSCAPE}
VALID_ELEMENT_TYPES = {"heading", "text", "table", "checkbox", "list", "line", "date", "fio", "item", "image"}
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_BORDER_STYLES = {"solid", "dashed", "dotted", "double"}
_HEADING_ALIGNS = {"left", "center", "right"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MEDIA_SRC_RE = re.compile(r"^/media/forms/[A-Za-z0-9._/-]+$")
_DEFAULT_PAGE_SETTINGS = {
    "margin_mm": 12,
    "border_inset_mm": 8,
    "border_width_mm": 1,
    "border_style": "solid",
    "border_color": "#000000",
    "page_count": 1,
}
_DEFAULT_IMAGE_FRAME_COLOR = "#1f4e79"


def _norm_page_settings(raw) -> dict:
    src = raw if isinstance(raw, dict) else {}
    style = str(src.get("border_style") or _DEFAULT_PAGE_SETTINGS["border_style"]).strip().lower()
    if style not in _BORDER_STYLES:
        style = "solid"
    color = str(src.get("border_color") or _DEFAULT_PAGE_SETTINGS["border_color"]).strip()
    if not _HEX_COLOR_RE.match(color):
        color = "#000000"

    def _mm(key: str, default: float, lo: float, hi: float) -> float:
        try:
            val = float(src.get(key, default))
        except (TypeError, ValueError):
            val = default
        return round(max(lo, min(hi, val)), 1)

    try:
        page_count = int(src.get("page_count") or 1)
    except (TypeError, ValueError):
        page_count = 1

    return {
        "margin_mm": _mm("margin_mm", 12, 0, 40),
        "border_inset_mm": _mm("border_inset_mm", 8, 0, 40),
        "border_width_mm": _mm("border_width_mm", 1, 0.1, 5),
        "border_style": style,
        "border_color": color,
        "page_count": max(1, min(MAX_PAGES, page_count)),
    }


def _norm_cell(raw, *, default_hidden: bool = False) -> dict:
    def _cell_text_fmt(item: dict) -> dict:
        align = str(item.get("align") or "left").strip().lower()
        if align not in _HEADING_ALIGNS:
            align = "left"
        try:
            font_size = int(item.get("font_size") or 12)
        except (TypeError, ValueError):
            font_size = 12
        return {
            "align": align,
            "font_size": max(8, min(48, font_size)),
            "bold": bool(item.get("bold")),
            "italic": bool(item.get("italic")),
            "underline": bool(item.get("underline")),
        }

    if isinstance(raw, str):
        return {
            "text": raw[:500],
            "bg": "#ffffff",
            "colspan": 1,
            "rowspan": 1,
            "hidden": default_hidden,
            **_cell_text_fmt({}),
        }
    if isinstance(raw, dict):
        bg = str(raw.get("bg") or "#ffffff").strip()
        if not _HEX_COLOR_RE.match(bg):
            bg = "#ffffff"
        return {
            "text": str(raw.get("text") or "")[:500],
            "bg": bg,
            "colspan": max(1, min(20, int(raw.get("colspan") or 1))),
            "rowspan": max(1, min(50, int(raw.get("rowspan") or 1))),
            "hidden": bool(raw.get("hidden")),
            **_cell_text_fmt(raw),
        }
    return {
        "text": "",
        "bg": "#ffffff",
        "colspan": 1,
        "rowspan": 1,
        "hidden": default_hidden,
        **_cell_text_fmt({}),
    }


def _form_to_dict(form: PrintForm) -> dict:
    elements = _norm_elements(form.elements if isinstance(form.elements, list) else [])
    page_settings = _sync_page_count(form.page_settings, elements)
    return {
        "id": form.pk,
        "name": form.name,
        "orientation": form.orientation,
        "show_border": form.show_border,
        "page_settings": page_settings,
        "elements": elements,
        "created_by": form.created_by,
        "updated_at": form.updated_at.isoformat(),
    }


def _norm_elements(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:MAX_ELEMENTS]:
        if not isinstance(item, dict):
            continue
        t = str(item.get("type") or "").strip()
        if t not in VALID_ELEMENT_TYPES:
            continue
        el = {"id": str(item.get("id") or ""), "type": t}
        if t == "heading":
            el["text"] = str(item.get("text") or "")[:500]
            align = str(item.get("align") or "left").strip().lower()
            if align not in _HEADING_ALIGNS:
                align = "left"
            el["align"] = align
            try:
                font_size = int(item.get("font_size") or 16)
            except (TypeError, ValueError):
                font_size = 16
            el["font_size"] = max(8, min(48, font_size))
        elif t == "text":
            el["text"] = str(item.get("text") or "")[:4000]
            try:
                height_px = int(item.get("height_px") or 0)
            except (TypeError, ValueError):
                height_px = 0
            el["height_px"] = max(0, min(2000, height_px))
        elif t == "table":
            el["rows"] = max(1, min(50, int(item.get("rows") or 1)))
            el["cols"] = max(1, min(20, int(item.get("cols") or 1)))
            cells = item.get("cells")
            norm_rows: list[list[dict]] = []
            if isinstance(cells, list):
                for row in cells[: el["rows"]]:
                    src = row if isinstance(row, list) else []
                    norm_rows.append([_norm_cell(c) for c in src[: el["cols"]]])
            while len(norm_rows) < el["rows"]:
                norm_rows.append([])
            for ri in range(el["rows"]):
                while len(norm_rows[ri]) < el["cols"]:
                    norm_rows[ri].append(_norm_cell(""))
                norm_rows[ri] = norm_rows[ri][: el["cols"]]
            el["cells"] = norm_rows
            cols = el["cols"]
            rows = el["rows"]
            raw_widths = item.get("col_widths")
            col_widths: list[float] = []
            if isinstance(raw_widths, list) and len(raw_widths) == cols:
                for w in raw_widths:
                    try:
                        col_widths.append(float(w))
                    except (TypeError, ValueError):
                        col_widths.append(100 / cols)
            else:
                w = round(100 / cols, 1)
                col_widths = [w] * cols
            for i in range(cols):
                col_widths[i] = round(max(5.0, min(95.0, col_widths[i])), 1)
            total = sum(col_widths)
            if total > 0 and abs(total - 100) > 0.05:
                col_widths = [round(w / total * 100, 1) for w in col_widths]
                col_widths[-1] = round(col_widths[-1] + (100 - sum(col_widths)), 1)
            el["col_widths"] = col_widths
            raw_heights = item.get("row_heights")
            row_heights: list[int] = []
            if isinstance(raw_heights, list) and len(raw_heights) == rows:
                for h in raw_heights:
                    try:
                        row_heights.append(int(h))
                    except (TypeError, ValueError):
                        row_heights.append(0)
            else:
                row_heights = [0] * rows
            el["row_heights"] = [max(0, min(300, h)) for h in row_heights]
        elif t == "checkbox":
            el["label"] = str(item.get("label") or "")[:300]
            el["checked"] = bool(item.get("checked"))
        elif t == "list":
            el["ordered"] = bool(item.get("ordered"))
            items = item.get("items")
            if isinstance(items, list):
                el["items"] = [str(x or "")[:500] for x in items[:50]]
            else:
                el["items"] = [""]
        elif t == "line":
            pass
        elif t == "date":
            el["label"] = str(item.get("label") or "Дата:")[:120]
            el["value"] = str(item.get("value") or "")[:50]
            el["placeholder"] = str(item.get("placeholder") or "дд.мм.гггг")[:50]
        elif t == "fio":
            el["label"] = str(item.get("label") or "ФИО:")[:120]
            el["value"] = str(item.get("value") or "")[:200]
            el["placeholder"] = str(item.get("placeholder") or "Фамилия Имя Отчество")[:80]
        elif t == "item":
            el["num"] = str(item.get("num") or "1.")[:10]
            el["label"] = str(item.get("label") or "")[:200]
            el["value"] = str(item.get("value") or "")[:500]
            el["placeholder"] = str(item.get("placeholder") or "")[:80]
        elif t == "image":
            src = str(item.get("src") or "").strip()
            if src and not _MEDIA_SRC_RE.match(src):
                src = ""
            el["src"] = src[:500]
            frame_color = str(item.get("frame_color") or _DEFAULT_IMAGE_FRAME_COLOR).strip()
            if not _HEX_COLOR_RE.match(frame_color):
                frame_color = _DEFAULT_IMAGE_FRAME_COLOR
            el["frame_color"] = frame_color
            try:
                frame_width = float(item.get("frame_width_mm", 1.5))
            except (TypeError, ValueError):
                frame_width = 1.5
            el["frame_width_mm"] = round(max(0.3, min(5.0, frame_width)), 1)
            try:
                width_pct = float(item.get("width_pct", 60))
            except (TypeError, ValueError):
                width_pct = 60.0
            el["width_pct"] = round(max(20.0, min(100.0, width_pct)), 1)
            align = str(item.get("align") or "center").strip().lower()
            if align not in _HEADING_ALIGNS:
                align = "center"
            el["align"] = align
            el["alt"] = str(item.get("alt") or "")[:200]
        try:
            page = int(item.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        el["page"] = max(0, min(MAX_PAGES - 1, page))
        if not el.get("id"):
            continue
        out.append(el)
    return out


def _sync_page_count(page_settings, elements: list) -> dict:
    ps = _norm_page_settings(page_settings)
    max_page = 0
    for el in elements:
        if not isinstance(el, dict):
            continue
        try:
            max_page = max(max_page, int(el.get("page") or 0))
        except (TypeError, ValueError):
            pass
    ps["page_count"] = max(ps["page_count"], max_page + 1)
    ps["page_count"] = max(1, min(MAX_PAGES, ps["page_count"]))
    last = ps["page_count"] - 1
    for el in elements:
        if isinstance(el, dict) and int(el.get("page") or 0) > last:
            el["page"] = last
    return ps


@biota_login_required
@nav_permission_required("forms")
@require_http_methods(["GET"])
def forms_view(request):
    return render(request, "shifts/forms.html")


@biota_login_required
@nav_permission_required("forms")
@write_permission_required
@require_http_methods(["GET", "POST"])
def forms_api_list(request):
    if request.method == "GET":
        forms = PrintForm.objects.all()[:MAX_FORMS]
        return JsonResponse({"ok": True, "forms": [_form_to_dict(f) for f in forms]})

    if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": False, "error": "Ожидается AJAX."}, status=400)
    if PrintForm.objects.count() >= MAX_FORMS:
        return JsonResponse({"ok": False, "error": f"Достигнут лимит форм ({MAX_FORMS})."}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)

    name = " ".join(str(data.get("name") or "").split()).strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Укажите название формы."}, status=400)

    orientation = str(data.get("orientation") or PrintForm.ORIENTATION_PORTRAIT).strip()
    if orientation not in VALID_ORIENTATIONS:
        orientation = PrintForm.ORIENTATION_PORTRAIT

    page_settings = _norm_page_settings(data.get("page_settings"))
    form = PrintForm.objects.create(
        name=name[:200],
        orientation=orientation,
        show_border=bool(data.get("show_border", True)),
        page_settings=page_settings,
        elements=[],
        created_by=biota_user(request) or "",
    )
    return JsonResponse({"ok": True, "form": _form_to_dict(form)})


@biota_login_required
@nav_permission_required("forms")
@write_permission_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def forms_api_detail(request, pk: int):
    try:
        form = PrintForm.objects.get(pk=pk)
    except PrintForm.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Форма не найдена."}, status=404)

    if request.method == "GET":
        return JsonResponse({"ok": True, "form": _form_to_dict(form)})

    if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": False, "error": "Ожидается AJAX."}, status=400)

    if request.method == "DELETE":
        form.delete()
        return JsonResponse({"ok": True})

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Некорректный JSON."}, status=400)

    if "name" in data:
        name = " ".join(str(data.get("name") or "").split()).strip()
        if name:
            form.name = name[:200]
    if "orientation" in data:
        orientation = str(data.get("orientation") or "").strip()
        if orientation in VALID_ORIENTATIONS:
            form.orientation = orientation
    if "show_border" in data:
        form.show_border = bool(data.get("show_border"))
    if "page_settings" in data:
        form.page_settings = _norm_page_settings(data.get("page_settings"))
    if "elements" in data:
        form.elements = _norm_elements(data.get("elements"))
    # Согласовать page_count с элементами (и после частичного PATCH).
    elements = form.elements if isinstance(form.elements, list) else []
    form.page_settings = _sync_page_count(form.page_settings, elements)
    form.elements = elements

    form.save()
    return JsonResponse({"ok": True, "form": _form_to_dict(form)})


@biota_login_required
@nav_permission_required("forms")
@write_permission_required
@require_http_methods(["POST"])
def forms_api_upload(request):
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return JsonResponse({"ok": False, "error": "Ожидается AJAX."}, status=400)

    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"ok": False, "error": "Файл не передан."}, status=400)

    raw_name = (getattr(uploaded, "name", "") or "").replace("\\", "/").rsplit("/", 1)[-1]
    ext = os.path.splitext(raw_name)[1].lower()
    if ext not in _IMAGE_EXTS:
        return JsonResponse(
            {"ok": False, "error": "Допустимы только изображения: JPG, PNG, GIF, WEBP."},
            status=400,
        )

    size = getattr(uploaded, "size", None)
    if size is not None and size > MAX_IMAGE_UPLOAD_BYTES:
        return JsonResponse({"ok": False, "error": "Файл больше 5 МБ."}, status=400)

    content_type = (getattr(uploaded, "content_type", "") or "").lower()
    if content_type and not content_type.startswith("image/"):
        return JsonResponse({"ok": False, "error": "Файл должен быть изображением."}, status=400)

    storage_name = f"forms/{uuid.uuid4().hex}{ext}"
    saved_path = default_storage.save(storage_name, uploaded)
    url = default_storage.url(saved_path)
    if "://" in url:
        from urllib.parse import urlparse

        url = urlparse(url).path or url
    if not url.startswith("/"):
        url = "/" + url.lstrip("/")
    if not _MEDIA_SRC_RE.match(url):
        url = "/media/" + saved_path.replace("\\", "/").lstrip("/")

    return JsonResponse({"ok": True, "url": url})
