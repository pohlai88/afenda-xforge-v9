import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from afenda.tools.brand_images import TARGETS, render_all


class BrandImagesTests(unittest.TestCase):
    def test_renders_every_target_with_expected_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = render_all(root)
            self.assertEqual(sorted(p.relative_to(root).as_posix() for p in written), sorted(TARGETS))
            for rel, kind in TARGETS.items():
                data = (root / rel).read_bytes()
                if rel.endswith(".svg"):
                    self.assertTrue(data.startswith(b"<svg"), rel)
                    self.assertNotIn(b"Odoo", data)
                elif rel.endswith(".ico"):
                    self.assertTrue(data.startswith(b"\x00\x00\x01\x00"), rel)
                else:
                    im = Image.open(io.BytesIO(data))
                    self.assertEqual(im.format, "PNG", rel)
                    if kind == "tile_png":
                        self.assertEqual(im.width, im.height, rel)

    def test_sizes_match_odoo_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_all(root)
            expect = {
                "addons/web/static/img/odoo-icon-192x192.png": (192, 192),
                "addons/web/static/img/odoo-icon-512x512.png": (512, 512),
                "addons/web/static/img/odoo-icon-ios.png": (512, 512),
                "addons/web/static/img/odoo_logo_tiny.png": (186, 60),
                "addons/web/static/img/logo.png": (180, 79),
                "addons/mail/static/src/img/odoo_o.png": (100, 100),
                "odoo/addons/base/static/img/res_company_logo.png": (450, 120),
            }
            for rel, size in expect.items():
                self.assertEqual(Image.open(root / rel).size, size, rel)
