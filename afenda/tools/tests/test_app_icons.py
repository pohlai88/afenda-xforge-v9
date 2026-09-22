"""Tests for the module app-icon generator.

The render is expensive (108 icons in the real tree), so setUpClass renders the
fixture tree once through ``brand_images.render_all`` - which also proves the
generator is wired into it - and every test reads that one render.
"""
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image

from afenda.tools import app_icons, brand_images

BLUE = (30, 58, 138)
GRAPHITE = (75, 85, 99)

# Fixture content the generator must leave exactly as it found it.
UNTOUCHED = b"not an icon, and not the generator's business"
PROVIDER_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50"><rect width="50" height="50" fill="#00B0F0"/></svg>'

# module -> (size, ships an icon.svg upstream)
FIXTURES = {
    "account": ((100, 100), True),      # mapped
    "crm": ((100, 100), True),          # mapped, a different glyph
    "stock": ((128, 128), False),       # mapped, PNG only
    "sms": ((80, 80), True),            # mapped, a glyph that is small in its em box
    "x_technical": ((100, 100), True),  # unmapped -> AFENDA mark on graphite
    "l10n_zz": ((250, 167), True),      # unmapped and not square
}
# Rendered from odoo/addons/base, which no addons/* glob reaches.
BASE_FIXTURES = ("icon", "settings", "modules")


def _transform(svg: str):
    """The affine the generated SVG puts on its glyph, as a function."""
    numbers = r"(-?[\d.]+(?:e-?\d+)?)"
    m = re.search(
        rf"transform=\"translate\({numbers} {numbers}\) scale\({numbers} {numbers}\) "
        rf"translate\({numbers} {numbers}\)\"",
        svg,
    )
    tx, ty, sx, sy, dx, dy = (float(v) for v in m.groups())
    return lambda x, y: ((x + dx) * sx + tx, (y + dy) * sy + ty)


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
        cls.third_party = sorted(app_icons.THIRD_PARTY)[:2]
        cls.provider_bytes = {}
        for module in cls.third_party:
            d = cls.root / "addons" / module / "static" / "description"
            d.mkdir(parents=True)
            # A real, perfectly renderable icon: the generator must still pass it by.
            Image.new("RGBA", (100, 100), (0, 128, 0, 255)).save(d / "icon.png")
            (d / "icon.svg").write_text(PROVIDER_SVG, encoding="utf-8")
            cls.provider_bytes[module] = {
                n: hashlib.sha256((d / n).read_bytes()).hexdigest() for n in ("icon.png", "icon.svg")
            }
        cls.base = cls.root / app_icons.BASE_DESCRIPTION
        cls.base.mkdir(parents=True)
        for stem in BASE_FIXTURES:
            Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(cls.base / f"{stem}.png")
        # board.svg exists without a board.png: neither may be created or touched.
        (cls.base / "board.svg").write_bytes(UNTOUCHED)
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

    def test_svg_carries_the_glyph_its_mapping_names(self):
        """Different-per-module is not the same as right-per-module: this ties
        APP_GLYPHS to what is drawn, so shuffling the map fails."""
        font = TTFont(app_icons.FA_TTF)
        glyphs = font.getGlyphSet()
        for module in ("account", "crm", "sms"):
            pen = SVGPathPen(glyphs)
            glyphs[font.getBestCmap()[int(app_icons.APP_GLYPHS[module], 16)]].draw(pen)
            self.assertIn(pen.getCommands(), self.svgs[module],
                          f"{module} does not carry the outline of U+{app_icons.APP_GLYPHS[module].upper()}")

    def test_svg_transform_places_the_glyph_upright_and_centred(self):
        """The transform is the one piece of this file no pixel can check: a
        two-stage translate around a NEGATIVE y scale, because the font's y axis
        points up and SVG's points down. Applied to the glyph's own bounds it
        must land at GLYPH_SCALE of the tile, centred - and not upside down."""
        font = TTFont(app_icons.FA_TTF)
        glyphs = font.getGlyphSet()
        side = app_icons.SVG_SIDE
        for module in ("account", "crm", "sms"):
            bounds = BoundsPen(glyphs)
            glyphs[font.getBestCmap()[int(app_icons.APP_GLYPHS[module], 16)]].draw(bounds)
            x0, y0, x1, y1 = bounds.bounds
            place = _transform(self.svgs[module])
            left, bottom = place(x0, y0)  # the font's low y is the glyph's bottom
            right, top = place(x1, y1)
            self.assertLess(top, bottom, f"{module} is drawn upside down")
            self.assertAlmostEqual(max(right - left, bottom - top), side * app_icons.GLYPH_SCALE, places=2,
                                   msg=f"{module} is not {app_icons.GLYPH_SCALE:.0%} of the tile")
            self.assertAlmostEqual((left + right) / 2, side / 2, places=2, msg=f"{module} x centre")
            self.assertAlmostEqual((top + bottom) / 2, side / 2, places=2, msg=f"{module} y centre")
            for value in (left, right, top, bottom):
                self.assertTrue(0 < value < side, f"{module} spills out of the tile at {value}")

    # --- what the generator must NOT touch --------------------------------

    def test_third_party_provider_icons_are_left_alone(self):
        """A provider's mark is not Odoo's identity, and the provider kanban is
        unusable without it. Fails if THIRD_PARTY stops being honoured."""
        self.assertTrue(self.third_party)
        written = {p.relative_to(self.root).as_posix() for p in self.written}
        for module in self.third_party:
            for name, before in self.provider_bytes[module].items():
                path = self.root / "addons" / module / "static" / "description" / name
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before,
                                 f"{module}/{name} was rewritten")
                self.assertNotIn(self._rel(module, name), written)

    # --- odoo/addons/base -------------------------------------------------

    def test_base_fallback_and_root_menu_icons_are_branded(self):
        """base/static/description/icon.png is what get_module_icon falls back to
        for every module without its own, and settings.png / modules.png are the
        Settings and Apps root menus. No addons/* glob reaches them.

        `icon` is the generic case, so it gets the generic tile: the AFENDA mark
        on graphite, like any unmapped module. The two root menus are real apps
        and get the Ledger Blue tile with their own glyph.
        """
        written = {p.relative_to(self.root).as_posix() for p in self.written}
        for stem in BASE_FIXTURES:
            rel = f"{app_icons.BASE_DESCRIPTION}/{stem}.png"
            self.assertIn(rel, written, rel)
            expected = GRAPHITE if stem == "icon" else BLUE
            with Image.open(self.base / f"{stem}.png") as im:
                im = im.convert("RGBA")
                self.assertEqual(im.size, (100, 100), stem)
                self.assertEqual(im.getpixel((50, 0))[:3], expected, f"{stem} is not a brand tile")
                self.assertEqual(im.getpixel((0, 0))[3], 0, f"{stem} has a square corner")
                box = _white_bbox(im)
                self.assertIsNotNone(box, f"{stem} has no glyph")
        # Every pair must be distinguishable. `icon` and `settings` were once
        # both f013, which made the Settings root menu identical to the tile
        # ~530 unmapped modules show; `icon` and `modules` are the same trap one
        # mapping away.
        digests = {
            stem: hashlib.sha256((self.base / f"{stem}.png").read_bytes()).hexdigest()
            for stem in BASE_FIXTURES
        }
        self.assertEqual(
            len(set(digests.values())), len(BASE_FIXTURES),
            f"two base icons draw the same tile: {digests}",
        )
        # And the fallback must be exactly what an unmapped module gets: same
        # graphite tile, same mark. x_technical is unmapped in FIXTURES.
        fallback = Image.open(self.base / "icon.png").convert("RGBA").resize((100, 100))
        unmapped = self.pngs["x_technical"]
        self.assertEqual(
            list(fallback.getdata()), list(unmapped.getdata()),
            "the fallback icon is not the same tile an unmapped module gets",
        )

    def test_base_icons_are_never_invented(self):
        """board.svg has no board.png beside it in the fixture: the generator
        renders from the PNGs it finds and creates nothing."""
        self.assertFalse((self.base / "board.png").exists())
        self.assertEqual((self.base / "board.svg").read_bytes(), UNTOUCHED)
        for stem in BASE_FIXTURES:
            self.assertFalse((self.base / f"{stem}.svg").exists(), f"{stem}.svg was invented")


if __name__ == "__main__":
    unittest.main()
