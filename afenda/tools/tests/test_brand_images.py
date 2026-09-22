import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from afenda.tools.brand_images import TARGETS, _solid, render_all

# A lockup drawn on its blue tile covers ~11% of the canvas in fully opaque
# pixels; the bare mark the white lockups use covers ~4%. Anything above this
# threshold means the tile came back behind the mark.
MAX_OPAQUE_FRACTION = 0.08


class BrandImagesTests(unittest.TestCase):
    """Every test reads the one render produced in setUpClass; none of them write."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.written = render_all(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _targets_of_kind(self, kind: str) -> list[str]:
        rels = [rel for rel, k in TARGETS.items() if k == kind]
        self.assertTrue(rels, f"no {kind} targets")
        return rels

    def _alpha(self, rel: str) -> Image.Image:
        with Image.open(self.root / rel) as src:
            return src.convert("RGBA").getchannel("A")

    def _assert_transparent_corners(self, rel: str, alpha: Image.Image):
        w, h = alpha.size
        for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            self.assertEqual(alpha.getpixel(corner), 0, f"{rel} is not transparent at {corner}")

    def test_renders_every_target_with_expected_format(self):
        self.assertEqual(sorted(p.relative_to(self.root).as_posix() for p in self.written), sorted(TARGETS))
        for rel, kind in TARGETS.items():
            data = (self.root / rel).read_bytes()
            if rel.endswith(".svg"):
                self.assertTrue(data.startswith(b"<svg"), rel)
                self.assertNotIn(b"Odoo", data)
            elif rel.endswith(".ico"):
                self.assertTrue(data.startswith(b"\x00\x00\x01\x00"), rel)
            else:
                with Image.open(io.BytesIO(data)) as im:
                    self.assertEqual(im.format, "JPEG" if rel.endswith(".jpg") else "PNG", rel)
                    if kind == "tile_png":
                        self.assertEqual(im.width, im.height, rel)

    def test_sizes_match_odoo_originals(self):
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
            "addons/web/static/img/enterprise_upgrade.jpg": (2378, 1306),
            "odoo/addons/base/static/img/logo_white.png": (600, 194),
            "odoo/addons/base/static/img/demo_logo_report.png": (621, 196),
        }
        for rel, size in expect.items():
            with Image.open(self.root / rel) as im:
                self.assertEqual(im.size, size, rel)

    def test_solid_replaces_colour_and_keeps_alpha(self):
        src = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
        src.putpixel((0, 0), (30, 58, 138, 255))
        src.putpixel((1, 0), (15, 23, 42, 128))
        self.assertEqual(
            list(_solid(src, (255, 255, 255)).getdata()),
            [(255, 255, 255, 255), (255, 255, 255, 128), (255, 255, 255, 0)],
        )

    def test_white_lockups_have_no_dark_pixels(self):
        for rel in self._targets_of_kind("lockup_white_png"):
            with Image.open(self.root / rel) as src:
                pixels = list(src.convert("RGBA").getdata())
            opaque = 0
            for r, g, b, a in pixels:
                if a == 0:
                    continue
                opaque += 1
                self.assertGreater(max(r, g, b), 200, f"{rel} has a dark pixel {(r, g, b, a)}")
            self.assertGreater(opaque, 0, rel)

    def test_white_lockups_have_no_tile(self):
        """The colour test above cannot see this: _solid whitens whatever shape it
        is given, so a reinstated blue tile would still be all-white pixels. Only
        the alpha channel shows that the mark is bare rather than on a solid tile.
        """
        for rel in self._targets_of_kind("lockup_white_png"):
            alpha = self._alpha(rel)
            self._assert_transparent_corners(rel, alpha)
            values = list(alpha.getdata())
            opaque = sum(1 for v in values if v == 255) / len(values)
            self.assertGreater(opaque, 0.02, f"{rel} looks empty: only {opaque:.2%} opaque")
            self.assertLess(
                opaque,
                MAX_OPAQUE_FRACTION,
                f"{rel} is {opaque:.2%} opaque - the mark is sitting on its tile again",
            )

    def test_faint_watermark_alpha(self):
        for rel in self._targets_of_kind("lockup_faint_png"):
            alpha = self._alpha(rel)
            self._assert_transparent_corners(rel, alpha)
            values = list(alpha.getdata())
            self.assertLessEqual(max(values), 40, rel)
            covered = sum(1 for v in values if v > 0) / len(values)
            self.assertGreater(covered, 0.05, f"{rel} covers only {covered:.2%} of the page: the lockup is missing")
