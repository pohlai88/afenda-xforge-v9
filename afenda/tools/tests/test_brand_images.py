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
                elif rel.endswith(".jpg"):
                    im = Image.open(io.BytesIO(data))
                    self.assertEqual(im.format, "JPEG", rel)
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
                "addons/web/static/img/nologo.png": (180, 79),
                "addons/web/static/img/logo_inverse_white_206px.png": (627, 206),
                "addons/web/static/img/default_icon_app.png": (180, 180),
                "addons/web/static/img/enterprise_upgrade.jpg": (1, 1),
                "odoo/addons/base/static/img/logo_white.png": (600, 194),
                "odoo/addons/base/static/img/demo_logo_report.png": (621, 196),
            }
            for rel, size in expect.items():
                with Image.open(root / rel) as im:
                    self.assertEqual(im.size, size, rel)

    def test_white_lockups_have_no_dark_pixels(self):
        rels = [rel for rel, kind in TARGETS.items() if kind == "lockup_white_png"]
        self.assertTrue(rels, "no lockup_white_png targets")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_all(root)
            for rel in rels:
                with Image.open(root / rel) as src:
                    pixels = list(src.convert("RGBA").getdata())
                opaque = 0
                for r, g, b, a in pixels:
                    if a == 0:
                        continue
                    opaque += 1
                    self.assertGreater(max(r, g, b), 200, f"{rel} has a dark pixel {(r, g, b, a)}")
                self.assertGreater(opaque, 0, rel)

    def test_faint_watermark_alpha(self):
        rels = [rel for rel, kind in TARGETS.items() if kind == "lockup_faint_png"]
        self.assertTrue(rels, "no lockup_faint_png targets")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_all(root)
            for rel in rels:
                with Image.open(root / rel) as src:
                    lo, hi = src.convert("RGBA").getchannel("A").getextrema()
                self.assertGreater(hi, 0, rel)
                self.assertLessEqual(hi, 40, rel)
