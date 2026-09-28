"""Ссылка на вкладку установки и QR для сканирования с телефона."""
from __future__ import annotations

import io
import re
from urllib.parse import urlencode

from django.http import HttpRequest
from django.urls import reverse

from .models import Product, ProductSetup

_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.I)


def _detail_path(product: Product) -> str:
    name = "osnastka_detail" if product.is_osnastka else "product_detail"
    return reverse(name, kwargs={"pk": product.pk})


def setup_tab_path(product: Product, setup: ProductSetup) -> str:
    return f"{_detail_path(product)}?{urlencode({'tab': f'setup-{setup.pk}'})}"


def setup_tab_absolute_url(request: HttpRequest, product: Product, setup: ProductSetup) -> str:
    path = setup_tab_path(product, setup)
    return request.build_absolute_uri(path)


def setup_url_is_localhost(url: str) -> bool:
    u = (url or "").lower()
    return "://127.0.0.1" in u or "://localhost" in u or "://[::1]" in u


def qr_svg_markup(text: str) -> str:
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        return ""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(image_factory=SvgPathImage).save(buf)
    raw = buf.getvalue().decode("utf-8", errors="replace")
    return _XML_DECL.sub("", raw).strip()
