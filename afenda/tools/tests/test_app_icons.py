"""Tests for the module app-icon generator.

The render is expensive (108 icons in the real tree), so setUpClass renders the
fixture tree once through ``brand_images.render_all`` - which also proves the
generator is wired into it - and every test reads that one render.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

from afenda.tools import app_icons, brand_images

BLUE = (30, 58, 138)
GRAPHITE = (75, 85, 99)

# module -> (size, ships an icon.svg upstream)
FIXTURES = {
    "account": ((100, 100), True),      # mapped
    "crm": ((100, 100), True),          # mapped, a different glyph
    "stock": ((128, 128), False),       # mapped, PNG only
    "sms": ((80, 80), True),            # mapped, a glyph that is small in its em box
    "x_technical": ((100, 100), True),  # unmapped -> AFENDA mark on graphite
    "l10n_zz": ((250, 167), True),      # unmapped and not square
}


def _white_bbox(im: Image.Image):
    """Bounding box of the opaque near-white ink (the glyph or the mark)."""
    w, h = im.size
    px = im.load()
    x0, y0, x1, y1 = w, h, -1, -1
    count = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 200 and min(r, g, b) > 200:
                count += 1
                x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    return (x0, y0, x1, y1, count) if count else None


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        for module, (size, has_svg) in FIXTURES.items():
            d = cls.root / "addons" / module / "static" / "description"
            d.mkdir(parents=True)
            # Deliberately not a tile: a flat red source proves the file was rewritten.
            Image.new("RGBA", size, (255, 0, 0, 255)).save(d / "icon.png")
            if has_svg:
                (d / "icon.svg").write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50">'
                    '<rect width="50" height="50" fill="#985184"/></svg>',
                    encoding="utf-8",
                )
        cls.written = brand_images.render_all(cls.root)
        cls.pngs = {m: Image.open(cls.root / "addons" / m / "static" / "description" / "icon.png").convert("RGBA")
                    for m in FIXTURES}
        cls.svgs = {m: (cls.root / "addons" / m / "static" / "description" / "icon.svg").read_text(encoding="utf-8")
                    for m, (_s, has_svg) in FIXTURES.items() if has_svg}

    @classmethod
    def tearDownClass(cls):
        for im in cls.pngs.values():
            im.close()
        cls._tmp.cleanup()

    def _rel(self, module: str, name: str) -> str:
        return f"addons/{module}/static/description/{name}"

    # --- discovery -------------------------------------------------------

    def test_brand_images_render_all_writes_the_app_icons(self):
        """Fails if the generator is not called from brand_images.render_all."""
        written = {p.relative_to(self.root).as_posix() for p in self.written}
        for module, (_size, has_svg) in FIXTURES.items():
            self.assertIn(self._rel(module, "icon.png"), written)
            self.assertEqual(has_svg, self._rel(module, "icon.svg") in written, module)

    def test_no_svg_is_created_where_upstream_ships_none(self):
        """Fails if the generator writes icon.svg next to every icon.png."""
        for module, (_size, has_svg) in FIXTURES.items():
            path = self.root / "addons" / module / "static" / "description" / "icon.svg"
            self.assertEqual(has_svg, path.exists(), module)

    def test_png_keeps_the_original_pixel_size(self):
        """Fails if the generator assumes 100x100 or squares non-square icons."""
        for module, (size, _has_svg) in FIXTURES.items():
            self.assertEqual(self.pngs[module].size, size, module)

    # --- the tile --------------------------------------------------------

    def test_tile_is_full_bleed_with_rounded_corners(self):
        """Fails on a square tile (corner opaque) or a tile inset from the edge."""
        for module, im in self.pngs.items():
            w, h = im.size
            for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
                self.assertEqual(im.getpixel(corner)[3], 0, f"{module} is opaque at {corner}")
            for edge in ((w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
                r, g, b, a = im.getpixel(edge)
                self.assertEqual(a, 255, f"{module} is transparent at {edge}")
                self.assertIn((r, g, b), (BLUE, GRAPHITE), f"{module} at {edge}")

    def test_mapped_modules_are_blue_and_unmapped_ones_graphite(self):
        """Fails if APP_GLYPHS stops being consulted, either way round."""
        for module in FIXTURES:
            expected = BLUE if module in app_icons.APP_GLYPHS else GRAPHITE
            im = self.pngs[module]
            self.assertEqual(im.getpixel((im.width // 2, 0))[:3], expected, module)
        self.assertIn("account", app_icons.APP_GLYPHS)
        self.assertNotIn("x_technical", app_icons.APP_GLYPHS)

    def test_glyph_is_white_and_scaled_to_the_tile(self):
        """The central test: the ink is white, centred, and GLYPH_SCALE of the
        short side - for every glyph, whatever share of its em box it fills.
        Fails if the glyph is missing, sized from the font size instead of the
        measured ink, stretched over the tile, or pushed off centre. The share
        is taken of the SHORT side, so it holds for non-square icons too."""
        for module, im in self.pngs.items():
            box = _white_bbox(im)
            self.assertIsNotNone(box, f"{module} has no white ink")
            x0, y0, x1, y1, _count = box
            side = min(im.size)
            span = max(x1 - x0 + 1, y1 - y0 + 1) / side
            self.assertAlmostEqual(span, app_icons.GLYPH_SCALE, delta=0.03,
                                   msg=f"{module} ink spans {span:.1%} of the tile")
            self.assertAlmostEqual((x0 + x1 + 1) / 2, im.width / 2, delta=side * 0.02, msg=f"{module} x centre")
            self.assertAlmostEqual((y0 + y1 + 1) / 2, im.height / 2, delta=side * 0.02, msg=f"{module} y centre")

    def test_each_mapping_draws_its_own_glyph(self):
        """Fails if every module renders the same picture (mapping ignored)."""
        # Digests, not pixel lists: a failure here should be one line, not 10000.
        account, crm, technical = (
            hashlib.sha256(self.pngs[m].tobytes()).hexdigest() for m in ("account", "crm", "x_technical")
        )
        self.assertNotEqual(account, crm, "account and crm render the same tile")
        self.assertNotEqual(account, technical, "a mapped and an unmapped module render the same tile")

    # --- the font --------------------------------------------------------

    def test_every_codepoint_exists_in_the_fontawesome_cmap(self):
        cmap = TTFont(app_icons.FA_TTF).getBestCmap()
        for module, code in app_icons.APP_GLYPHS.items():
            self.assertRegex(code, r"^[0-9a-f]{4}$", module)
            self.assertIn(int(code, 16), cmap, f"{module}: U+{code.upper()} is not in the font")

    # --- the SVG ---------------------------------------------------------

    def test_svg_is_a_branded_tile(self):
        for module, svg in self.svgs.items():
            self.assertTrue(svg.startswith("<svg"), module)
            self.assertIn('viewBox="0 0 50 50"', svg)
            self.assertIn("#1E3A8A" if module in app_icons.APP_GLYPHS else "#4B5563", svg, module)
            for dead in ("#985184", "#1AD3BB", "Odoo", "odoo"):
                self.assertNotIn(dead, svg, module)
            self.assertIn("<path", svg, module)

    def test_svg_glyphs_differ_between_modules(self):
        """Fails if the SVG path is a constant rather than the mapped glyph."""
        self.assertNotEqual(self.svgs["account"], self.svgs["crm"])
        self.assertNotEqual(self.svgs["account"], self.svgs["x_technical"])


if __name__ == "__main__":
    unittest.main()
