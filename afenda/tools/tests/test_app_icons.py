"""Tests for the module app-icon generator.

The render is expensive (108 icons in the real tree), so setUpClass renders the
fixture tree once through ``brand_images.render_all`` - which also proves the
generator is wired into it - and every test reads that one render.

The icons are free-standing duotone marks: a glyph in colour A, an accent shape
in colour B, and the multiply of the two where they cross. There is no tile, so
nothing here may assert a filled edge or a background colour; what it asserts
instead is the three-colour construction, the multiply, and the transparency.
"""
import hashlib
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image

from afenda.tools import app_icons, brand_images

GREY = app_icons.rgb(app_icons.GREY)

# Fixture content the generator must leave exactly as it found it.
UNTOUCHED = b"not an icon, and not the generator's business"
PROVIDER_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50"><rect width="50" height="50" fill="#00B0F0"/></svg>'

# module -> (size, ships an icon.svg upstream). Between them the mapped ones
# cover all three accent primitives: a disc, a wedge and a bar.
FIXTURES = {
    "account": ((100, 100), True),      # mapped, disc accent
    "crm": ((100, 100), True),          # mapped, wedge accent, a different glyph
    "hr_holidays": ((100, 100), True),  # mapped, bar accent
    "stock": ((128, 128), False),       # mapped, PNG only
    "sms": ((80, 80), True),            # mapped, a glyph that is small in its em box
    "x_technical": ((100, 100), True),  # unmapped -> the AFENDA mark in grey
    "l10n_zz": ((250, 167), True),      # unmapped and not square
}
MAPPED = [m for m in FIXTURES if m in app_icons.APP_GLYPHS]
# Rendered from odoo/addons/base, which no addons/* glob reaches.
BASE_FIXTURES = ("icon", "settings", "modules", "exception")

# A colour has to cover this much of an icon to count as being in the picture.
# The thinnest real one in the fixtures is crm's multiply at 0.9%: its wedge
# only clips the corner of the suitcase.
MIN_SHARE = 0.002

# Above this size no supersampling happens (MAX_SUPERSAMPLED // side == 1), so
# the composite is returned unresampled and every opaque pixel is exactly one
# of the three colours. Below it, LANCZOS rings and blends along every seam.
UNRESAMPLED = 600


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


def _colours(im: Image.Image) -> Counter:
    """Fully opaque colours and how many pixels each covers."""
    return Counter(rgba[:3] for rgba in im.getdata() if rgba[3] == 255)


def _nearest(pixel, colours) -> int:
    """Index of the colour ``pixel`` is closest to."""
    r, g, b = pixel[:3]
    return min(range(len(colours)),
               key=lambda i: (r - colours[i][0]) ** 2 + (g - colours[i][1]) ** 2 + (b - colours[i][2]) ** 2)


def _ink_bbox(im: Image.Image, colours, accent: int | None):
    """Bounding box of the glyph, found by colour rather than by opacity.

    The accent bleeds off the canvas on purpose, so the opaque bounding box of
    the whole icon says nothing about the glyph. Every pixel that is nearer to
    colour A or to the multiply than to the accent is glyph, antialiased edges
    included - which is what keeps this measuring the drawing and not the
    resampler.
    """
    px = im.load()
    x0, y0, x1, y1 = im.width, im.height, -1, -1
    count = 0
    for y in range(im.height):
        for x in range(im.width):
            if px[x, y][3] <= 100 or _nearest(px[x, y], colours) == accent:
                continue
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
            # Deliberately opaque red: proves the file was rewritten, and that
            # the new icon does not simply keep whatever was underneath it.
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

    def _trio(self, module: str):
        """(A, B, multiply) for a mapped module, as RGB triples."""
        glyph, accent, _shape = app_icons.ACCENTS[module]
        a, b = app_icons.rgb(glyph), app_icons.rgb(accent)
        return a, b, app_icons.multiply(a, b)

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

    # --- the colour table ------------------------------------------------

    def test_every_mapped_module_has_an_accent(self):
        """APP_GLYPHS and ACCENTS are one table in two halves. Fails if a module
        is added to one and not the other - which would be a KeyError mid-render
        on a tree of 108 icons, or a glyph silently drawn with no accent."""
        self.assertEqual(set(app_icons.APP_GLYPHS), set(app_icons.ACCENTS))
        palette = {
            getattr(app_icons, n) for n in
            ("LEDGER", "SLATE", "INDIGO", "TEAL", "MOSS", "PLUM", "MULBERRY",
             "OCHRE", "MUSTARD", "BRICK", "CLAY", "VIOLET", "GREY")
        }
        for module, (glyph, accent, shape) in app_icons.ACCENTS.items():
            self.assertIn(glyph, palette, f"{module} draws in a colour outside the brand palette")
            self.assertIn(accent, palette, f"{module} accents in a colour outside the brand palette")
            self.assertIn(shape, app_icons.ACCENT_SHAPES, f"{module} names a shape that does not exist")
            self.assertNotEqual(glyph, accent, f"{module} is monotone: the accent would not show")

    # --- the mark --------------------------------------------------------

    def test_the_mark_is_free_standing_and_not_a_tile(self):
        """Fails the moment a container tile comes back. A rounded tile at the
        radius this generator used to draw leaves about 3% of the canvas clear
        and fills all four corners; these marks leave 29-78% clear and fill at
        most one corner (crm's wedge, which bleeds off the top right on
        purpose). Standing free on transparency is what lets 108 of them tell
        each other apart in the apps menu."""
        for module, im in self.pngs.items():
            w, h = im.size
            clear_corners = sum(im.getpixel(c)[3] == 0 for c in
                                ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))
            self.assertGreaterEqual(clear_corners, 3, f"{module} fills {4 - clear_corners} corners")
            clear = sum(1 for rgba in im.getdata() if rgba[3] == 0) / (w * h)
            self.assertGreater(clear, 0.20, f"{module} is only {clear:.0%} transparent - that is a tile")
            self.assertLess(clear, 0.90, f"{module} is {clear:.0%} transparent - there is barely a mark")

    def test_the_construction_is_exactly_three_colours(self):
        """The whole design in one assertion, read off an unresampled render so
        there is nothing to round: a mapped icon is colour A, colour B and their
        multiply and NOTHING else; an unmapped one is the grey mark alone.

        Fails if the accent layer is dropped, if the overlap is painted in A or
        B instead of the third colour, if a background creeps back in, or if
        APP_GLYPHS stops being consulted either way round."""
        designs = {m: app_icons.design_for(m) for m in FIXTURES}
        designs.update({f"base/{s}": d for s, d in app_icons.BASE_ICONS.items()})
        for name, design in designs.items():
            im = app_icons.icon_png(UNRESAMPLED, UNRESAMPLED, design)
            a = app_icons.rgb(design.glyph)
            if design.accent:
                b = app_icons.rgb(design.accent)
                expected = {a, b, app_icons.multiply(a, b)}
                self.assertEqual(len(expected), 3, f"{name}: A, B and the multiply are not three colours")
            else:
                expected = {a}
            self.assertEqual(set(_colours(im)), expected,
                             f"{name} is not built from exactly its glyph colour, its accent and their multiply")
        self.assertIn("account", app_icons.APP_GLYPHS)
        self.assertNotIn("x_technical", app_icons.APP_GLYPHS)

    def test_every_rendered_icon_really_shows_all_three_colours(self):
        """The test above proves the recipe; this one proves the picture. Each
        of the three colours has to survive into the file on disk with real
        coverage, so an accent that misses the glyph entirely - no overlap, no
        third colour, a flat two-colour mark - fails here rather than shipping."""
        for module in MAPPED:
            im = self.pngs[module]
            counts = _colours(im)
            floor = im.width * im.height * MIN_SHARE
            for name, colour in zip(("glyph", "accent", "multiply"), self._trio(module)):
                self.assertGreater(counts[colour], floor,
                                   f"{module}: the {name} colour {colour} covers {counts[colour]} px")

    def test_the_overlap_is_the_multiply_of_the_two_colours(self):
        """Pins the blend itself, for one known pair: account is Ledger Blue
        over Teal. Fails if the overlap becomes an alpha blend, a screen, or a
        hand-picked third hex - each of which passes the tests above only by
        accident and none of which stays in step when a colour changes."""
        a, b, over = self._trio("account")
        self.assertEqual(a, (30, 58, 138))
        self.assertEqual(b, (47, 143, 138))
        self.assertEqual(over, (6, 33, 75))  # not the 50% blend (38, 100, 138)
        self.assertEqual(app_icons.multiply(a, b), over)
        self.assertGreater(_colours(self.pngs["account"])[over], 0,
                           "the multiply colour is nowhere in the rendered icon")

    def test_glyph_is_scaled_and_centred(self):
        """The ink is GLYPH_SCALE of the short side and centred - for every
        glyph, whatever share of its em box it fills. Fails if the glyph is
        missing, sized from the font size instead of the measured ink, stretched
        to the canvas, or pushed off centre. The glyph is found by colour: the
        accent runs off the canvas and would swamp any opacity-based box."""
        for module, im in self.pngs.items():
            if module in MAPPED:
                a, b, over = self._trio(module)
                box = _ink_bbox(im, [a, b, over], accent=1)
            else:
                box = _ink_bbox(im, [GREY], accent=None)
            self.assertIsNotNone(box, f"{module} has no glyph ink")
            x0, y0, x1, y1, _count = box
            side = min(im.size)
            span = max(x1 - x0 + 1, y1 - y0 + 1) / side
            self.assertAlmostEqual(span, app_icons.GLYPH_SCALE, delta=0.03,
                                   msg=f"{module} ink spans {span:.1%} of the short side")
            self.assertAlmostEqual((x0 + x1 + 1) / 2, im.width / 2, delta=side * 0.02, msg=f"{module} x centre")
            self.assertAlmostEqual((y0 + y1 + 1) / 2, im.height / 2, delta=side * 0.02, msg=f"{module} y centre")

    def test_each_mapping_draws_its_own_glyph(self):
        """Fails if every module renders the same picture (mapping ignored)."""
        # Digests, not pixel lists: a failure here should be one line, not 10000.
        account, crm, technical = (
            hashlib.sha256(self.pngs[m].tobytes()).hexdigest() for m in ("account", "crm", "x_technical")
        )
        self.assertNotEqual(account, crm, "account and crm render the same mark")
        self.assertNotEqual(account, technical, "a mapped and an unmapped module render the same mark")

    def test_the_mark_box_matches_the_mark(self):
        """MARK_SVG_BOX is a hand-copied measurement of a shape that lives in
        another module, so it rots silently: the SVG fallback every unmapped
        module ships would keep scaling and centring to the old outline. The
        mark is straight-edged polygons, so its extent is just the extent of
        its coordinates, and that can be re-derived here."""
        numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", brand_images.MARK_SVG_INNER.replace("{fg}", ""))]
        self.assertTrue(numbers, "the mark is no longer plain polygon coordinates")
        xs, ys = numbers[0::2], numbers[1::2]
        self.assertEqual(app_icons.MARK_SVG_BOX, (min(xs), min(ys), max(xs), max(ys)),
                         "the AFENDA mark was redrawn and MARK_SVG_BOX was not")

    # --- the font --------------------------------------------------------

    def test_every_codepoint_exists_in_the_fontawesome_cmap(self):
        cmap = TTFont(app_icons.FA_TTF).getBestCmap()
        for module, code in app_icons.APP_GLYPHS.items():
            self.assertRegex(code, r"^[0-9a-f]{4}$", module)
            self.assertIn(int(code, 16), cmap, f"{module}: U+{code.upper()} is not in the font")

    # --- the SVG ---------------------------------------------------------

    def test_svg_draws_the_same_three_layers_as_the_png(self):
        """The SVG is served beside the PNG in the apps menu, so the two must be
        the same picture. Fails if the SVG keeps a tile, loses the accent, or
        skips the clipped multiply layer that stands in for the raster's
        intersection mask."""
        for module, svg in self.svgs.items():
            self.assertTrue(svg.startswith("<svg"), module)
            self.assertIn('viewBox="0 0 50 50"', svg)
            self.assertNotIn("<rect width=\"50\"", svg, f"{module} still has a tile behind the mark")
            for dead in ("#985184", "#1AD3BB", "Odoo", "odoo"):
                self.assertNotIn(dead, svg, module)
            if module not in MAPPED:
                self.assertIn(app_icons.GREY, svg, module)
                self.assertNotIn("clipPath", svg, f"{module} is unmapped and has no accent to clip to")
                continue
            glyph, accent, _shape = app_icons.ACCENTS[module]
            over = app_icons._hex(app_icons.multiply(*(app_icons.rgb(c) for c in (glyph, accent))))
            self.assertIn(f'fill="{glyph}"', svg, f"{module} does not draw its glyph in colour A")
            self.assertIn(f'fill="{accent}"', svg, f"{module} does not draw its accent in colour B")
            self.assertIn(f'fill="{over}"', svg, f"{module} has no multiply layer")
            self.assertIn(f'<clipPath id="{app_icons.ACCENT_CLIP_ID}">', svg, module)
            self.assertIn(f'clip-path="url(#{app_icons.ACCENT_CLIP_ID})"', svg, module)
            # The multiply layer must be the glyph again, not a fill of the
            # accent: two copies of the same outline, one clipped.
            self.assertEqual(svg.count("<path d="), 2, f"{module} does not draw the glyph twice")

    def test_svg_accent_geometry_matches_the_masks(self):
        """One table drives both renders. Fails if the SVG shape drifts from the
        mask the PNG uses - a circle at a different centre, a bar at a different
        height - which would show as the PNG and the SVG disagreeing in the
        apps menu depending on which one the browser picked."""
        for shape, (kind, _geom) in app_icons.ACCENT_SHAPES.items():
            element = app_icons._accent_svg(shape)
            self.assertIn({"circle": "<circle", "polygon": "<polygon", "rect": "<rect"}[kind], element, shape)
        # account's disc-br is (70, 70, 34) in a 0..100 box, so half of that in
        # the 50-unit viewBox.
        self.assertIn('<circle cx="35" cy="35" r="17"', self.svgs["account"])
        self.assertIn('<rect x="3" y="2" width="44" height="14" rx="6.5"', self.svgs["hr_holidays"])
        self.assertIn("<polygon", self.svgs["crm"])

    def test_svg_glyphs_differ_between_modules(self):
        """Fails if the SVG path is a constant rather than the mapped glyph."""
        self.assertNotEqual(self.svgs["account"], self.svgs["crm"])
        self.assertNotEqual(self.svgs["account"], self.svgs["x_technical"])

    def test_svg_carries_the_glyph_its_mapping_names(self):
        """Different-per-module is not the same as right-per-module: this ties
        APP_GLYPHS to what is drawn, so shuffling the map fails."""
        font = TTFont(app_icons.FA_TTF)
        glyphs = font.getGlyphSet()
        for module in MAPPED:
            pen = SVGPathPen(glyphs)
            glyphs[font.getBestCmap()[int(app_icons.APP_GLYPHS[module], 16)]].draw(pen)
            if module in self.svgs:
                self.assertIn(pen.getCommands(), self.svgs[module],
                              f"{module} does not carry the outline of U+{app_icons.APP_GLYPHS[module].upper()}")

    def test_svg_transform_places_the_glyph_upright_and_centred(self):
        """The transform is the one piece of this file no pixel can check: a
        two-stage translate around a NEGATIVE y scale, because the font's y axis
        points up and SVG's points down. Applied to the glyph's own bounds it
        must land at GLYPH_SCALE of the icon, centred - and not upside down."""
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
                                   msg=f"{module} is not {app_icons.GLYPH_SCALE:.0%} of the icon")
            self.assertAlmostEqual((left + right) / 2, side / 2, places=2, msg=f"{module} x centre")
            self.assertAlmostEqual((top + bottom) / 2, side / 2, places=2, msg=f"{module} y centre")
            for value in (left, right, top, bottom):
                self.assertTrue(0 < value < side, f"{module} spills out of the icon at {value}")

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
        for every module without its own, and settings.png / modules.png /
        exception.png are the Settings, Apps and Tests root menus. No addons/*
        glob reaches them.

        `icon` is the generic case, so it gets the generic treatment: the AFENDA
        mark in grey, like any unmapped module. The root menus are real apps and
        get their own glyph and accent.
        """
        written = {p.relative_to(self.root).as_posix() for p in self.written}
        for stem in BASE_FIXTURES:
            rel = f"{app_icons.BASE_DESCRIPTION}/{stem}.png"
            self.assertIn(rel, written, rel)
            design = app_icons.BASE_ICONS[stem]
            with Image.open(self.base / f"{stem}.png") as im:
                im = im.convert("RGBA")
                self.assertEqual(im.size, (100, 100), stem)
                self.assertEqual(im.getpixel((0, 0))[3], 0, f"{stem} has grown a tile")
                counts = _colours(im)
                floor = im.width * im.height * MIN_SHARE
                expected = [app_icons.rgb(design.glyph)]
                if design.accent:
                    b = app_icons.rgb(design.accent)
                    expected += [b, app_icons.multiply(expected[0], b)]
                for colour in expected:
                    self.assertGreater(counts[colour], floor,
                                       f"{stem} is not the duotone every other icon is: {colour} is missing")
        # Every pair must be distinguishable. `icon` and `settings` were once
        # both f013, which made the Settings root menu identical to the mark
        # ~530 unmapped modules show; `icon` and `modules` are the same trap one
        # mapping away.
        digests = {
            stem: hashlib.sha256((self.base / f"{stem}.png").read_bytes()).hexdigest()
            for stem in BASE_FIXTURES
        }
        self.assertEqual(
            len(set(digests.values())), len(BASE_FIXTURES),
            f"two base icons draw the same mark: {digests}",
        )
        # And the fallback must be exactly what an unmapped module gets: the
        # same grey mark. x_technical is unmapped in FIXTURES.
        fallback = Image.open(self.base / "icon.png").convert("RGBA").resize((100, 100))
        unmapped = self.pngs["x_technical"]
        self.assertEqual(
            list(fallback.getdata()), list(unmapped.getdata()),
            "the fallback icon is not the same mark an unmapped module gets",
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
