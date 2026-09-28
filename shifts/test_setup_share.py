from django.test import SimpleTestCase

from shifts.setup_share import qr_svg_markup, setup_url_is_localhost


class SetupShareQrTests(SimpleTestCase):
    def test_qr_svg_markup_returns_svg(self):
        markup = qr_svg_markup("https://example.com/products/9/?tab=setup-11")
        self.assertTrue(markup)
        self.assertIn("<svg", markup.lower())
        self.assertIn("<path", markup.lower())

    def test_localhost_detection(self):
        self.assertTrue(setup_url_is_localhost("http://127.0.0.1:8000/products/1/?tab=setup-2"))
        self.assertFalse(setup_url_is_localhost("https://shop.example.com/products/1/?tab=setup-2"))
