"""Tests for the module app-icon generator.

The render is expensive (108 icons in the real tree), so setUpClass renders the
fixture tree once through ``brand_images.render_all`` - which also proves the
generator is wired into it - and every test reads that one render.

The icons are free-standing duotone marks: a glyph in colour A, an accent shape
in colour B, and a controlled darkening of the two where they cross. There is no
tile, so nothing here may assert a filled edge or a background colour; what it
asserts instead is the three-colour construction, the overlap colour, and the
transparency.
"""
import hashlib
import re
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageStat

from afenda.tools import app_icons, brand_images
from afenda.tools.xforge_icons.paths import bounds as path_bounds, flatten_path

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
        """(A, B, overlap) for a mapped module, as RGB triples."""
        glyph, accent, _shape = app_icons.ACCENTS[module]
        a, b = app_icons.rgb(glyph), app_icons.rgb(accent)
        return a, b, app_icons.controlled_overlap_colour(a, b)

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
            # Every mapped module was placed by eye. The scorer exists for the
            # ones that were not, and must never quietly take one of these over:
            # a shape of None or "auto" here is a hand-placed accent lost.
            self.assertNotIn(shape, (None, app_icons.AUTO),
                             f"{module} would be auto-placed; its explicit shape was dropped")
            original = app_icons.design_for(module)
            resolved = app_icons.resolve_design(original)
            self.assertEqual(
                (resolved.code, resolved.glyph, resolved.accent, resolved.shape, resolved.art),
                (original.code, original.glyph, original.accent, original.shape, original.art),
                f"{module}'s design was rewritten on its way to the renderer")
            # The band is the one field resolution is allowed to fill in. It is
            # placed against the accent AFTER the accent is clipped to the body,
            # so it cannot be written in the table beside the shape - the table
            # does not know the body. Hard-coding one here would be the same
            # mistake as hard-coding a scored shape.
            self.assertIsNone(original.band, f"{module} hard-codes a band")
            self.assertIsNotNone(resolved.band, f"{module} reached the renderer with no band")

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
        overlap colour and NOTHING else; an unmapped one is the grey mark alone.

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
                expected = {a, b, app_icons.controlled_overlap_colour(a, b)}
                self.assertEqual(len(expected), 3, f"{name}: A, B and the overlap are not three colours")
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
            for name, colour in zip(("glyph", "accent", "overlap"), self._trio(module)):
                self.assertGreater(counts[colour], floor,
                                   f"{module}: the {name} colour {colour} covers {counts[colour]} px")

    def test_the_overlap_colour_darkens_without_collapsing_to_mud(self):
        """Pins the blend itself, for one known pair: account is Ledger Blue
        over Teal.

        The overlap has to stay a darkening - lighter than neither ink, or it
        stops reading as an overprint - while staying a colour. Raw multiply
        gives (6, 33, 75), luminance 0.016, which is the near-black this
        replaced. Fails if the overlap reverts to raw multiply, becomes a plain
        alpha blend or the arithmetic midpoint, or is hand-picked: each passes
        the tests above by accident and none stays in step when a colour moves.
        """
        a, b, over = self._trio("account")
        self.assertEqual(a, (30, 58, 138))
        self.assertEqual(b, (47, 143, 138))
        raw = app_icons.multiply(a, b)
        self.assertEqual(raw, (6, 33, 75))
        self.assertLess(app_icons.relative_luminance(raw), app_icons.MIN_OVERLAP_LUMINANCE,
                        "raw multiply is no longer the mud case this is here to fix")
        self.assertEqual(over, (22, 66, 106))
        # Darker than both inks, lighter than the raw multiply, and not the
        # midpoint (38, 100, 138) the relaxation eases toward.
        self.assertLess(app_icons.relative_luminance(over), app_icons.relative_luminance(a))
        self.assertLess(app_icons.relative_luminance(over), app_icons.relative_luminance(b))
        self.assertGreater(app_icons.relative_luminance(over), app_icons.relative_luminance(raw))
        self.assertNotEqual(over, tuple(round((x + y) / 2) for x, y in zip(a, b)))
        self.assertGreater(_colours(self.pngs["account"])[over], 0,
                           "the overlap colour is nowhere in the rendered icon")

    def test_the_overlap_colour_clears_the_luminance_floor(self):
        """Every pair actually in the tables, not just the one pinned above.

        Eighteen of the twenty-one mapped pairs multiply to below the floor -
        ledger x mustard bottoms out at 0.007 - so this is the assertion that
        the rescue reaches all of them and not only the pair someone tested by
        hand. Fails if the floor is raised past what the easing can deliver, if
        the easing is shortened, or if a new colour pair is added whose own
        midpoint is already too dark to rescue.
        """
        pairs = {(g, a) for g, a, _s in app_icons.ACCENTS.values()}
        pairs |= {(d.glyph, d.accent) for d in app_icons.BASE_ICONS.values() if d.accent}
        self.assertGreaterEqual(len(pairs), 20)
        rescued = 0
        for glyph, accent in sorted(pairs):
            a, b = app_icons.rgb(glyph), app_icons.rgb(accent)
            over = app_icons.controlled_overlap_colour(a, b)
            self.assertGreaterEqual(
                app_icons.relative_luminance(over), app_icons.MIN_OVERLAP_LUMINANCE,
                f"{glyph} x {accent} crosses at {app_icons._hex(over)}, below the readable floor")
            self.assertNotIn(over, (a, b), f"{glyph} x {accent} does not read as a crossing at all")
            rescued += app_icons.relative_luminance(app_icons.multiply(a, b)) < app_icons.MIN_OVERLAP_LUMINANCE
        self.assertGreater(rescued, len(pairs) // 2,
                           "raw multiply no longer collapses, so this guard is measuring nothing")

    def test_glyph_is_scaled_and_centred(self):
        """The ink is GLYPH_SCALE of the short side and centred - for every
        glyph, whatever share of its em box it fills. Fails if the glyph is
        missing, sized from the font size instead of the measured ink, stretched
        to the canvas, or pushed off centre.

        Measured over ALL THREE colours. It used to exclude the accent, because
        the accent ran off the canvas and would have swamped the box - and that
        exclusion is exactly what the clipping fix removed. The accent is now
        inside the body, so every opaque pixel is the icon, and excluding one of
        its three colours would measure a shape with a bite taken out of it
        (stock came out at 78.1% that way, against a real span of 84%)."""
        for module, im in self.pngs.items():
            if module in MAPPED:
                a, b, over = self._trio(module)
                box = _ink_bbox(im, [a, b, over], accent=None)
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
        """MARK_SVG_BOX is what the SVG fallback every unmapped module ships
        scales and centres to. It is imported from brand_images rather than
        copied, but that only removes one way for it to rot: `mark_svg` could
        still emit paths that leave the declared box. The mark is straight-edged
        polygons, so its extent is just the extent of its coordinates."""
        paths = re.sub(r'fill="[^"]*"', "", brand_images.mark_svg(("#000000",) * 4))
        numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", paths)]
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
            over = app_icons._hex(app_icons.controlled_overlap_colour(*(app_icons.rgb(c) for c in (glyph, accent))))
            clip = app_icons.svg_clip_id(app_icons.design_for(module))
            self.assertIn(f'fill="{glyph}"', svg, f"{module} does not draw its glyph in colour A")
            self.assertIn(f'fill="{accent}"', svg, f"{module} does not draw its accent in colour B")
            self.assertIn(f'fill="{over}"', svg, f"{module} has no overlap layer")
            # Two clips now, because there are two planes to cut the body with:
            # the accent, and the xForge band the accent crosses.
            self.assertIn(f'<clipPath id="{clip}-accent">', svg, module)
            self.assertIn(f'<clipPath id="{clip}-band">', svg, module)
            self.assertIn(f'clip-path="url(#{clip}-accent)"', svg, module)
            self.assertIn(f'clip-path="url(#{clip}-band)"', svg, module)
            # The body, three times: once whole in colour A, once clipped to the
            # accent in colour B, once clipped to accent AND band in the crossing
            # colour. It must be the body that repeats, never a fill of the
            # accent shape - that is what keeps the silhouette the body.
            self.assertEqual(svg.count("<path d="), 3,
                             f"{module} does not draw its body three times")
            # And the accent shape itself is never painted, only ever a clip.
            body_shape = "<circle" if "circle" in svg else None
            if body_shape:
                self.assertEqual(svg.count("<circle"), 1,
                                 f"{module} paints its accent instead of clipping with it")

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
            if module not in self.svgs:
                continue
            art = app_icons.AUTHORED_ART.get(module)
            if art:
                # An authored module draws its own silhouette and NOT the glyph
                # its mapping names - that is the point of authoring it. The
                # mapping stays in APP_GLYPHS because the fallback path still
                # needs a glyph if the art is ever withdrawn, and because
                # test_every_mapped_module_has_an_accent holds the two tables
                # together by key.
                self.assertIn(app_icons.AUTHORED_SHAPES[art](False)["body"], self.svgs[module],
                              f"{module} does not carry its authored silhouette")
                self.assertNotIn(pen.getCommands(), self.svgs[module],
                                 f"{module} draws its authored art AND its glyph")
                continue
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
        glyph_modules = [m for m in MAPPED if m not in app_icons.AUTHORED_ART][:3]
        self.assertTrue(glyph_modules, "no glyph-drawn module left to check the font transform on")
        for module in glyph_modules:
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

    def test_authored_art_is_placed_without_the_font_flip(self):
        """The authored silhouettes go through the same two-stage transform, but
        their y scale is POSITIVE: they are drawn in SVG coordinates, which
        already point down, so flipping them would stand them on their heads.
        Same GLYPH_SCALE, same centre, same no-spill rule as the glyphs."""
        side = app_icons.SVG_SIDE
        self.assertTrue(app_icons.AUTHORED_ART, "no authored art to check")
        for module, art in sorted(app_icons.AUTHORED_ART.items()):
            if module not in self.svgs:
                continue
            body = flatten_path(app_icons.AUTHORED_SHAPES[art](False)["body"])
            x0, y0, x1, y1 = path_bounds(body)
            place = _transform(self.svgs[module])
            left, top = place(x0, y0)  # SVG's low y is the top
            right, bottom = place(x1, y1)
            self.assertLess(top, bottom, f"{module} is drawn upside down")
            self.assertAlmostEqual(max(right - left, bottom - top), side * app_icons.GLYPH_SCALE, places=2,
                                   msg=f"{module} is not {app_icons.GLYPH_SCALE:.0%} of the icon")
            self.assertAlmostEqual((left + right) / 2, side / 2, places=2, msg=f"{module} x centre")
            self.assertAlmostEqual((top + bottom) / 2, side / 2, places=2, msg=f"{module} y centre")
            for value in (left, right, top, bottom):
                self.assertTrue(0 < value < side, f"{module} spills out of the icon at {value}")

    # --- the silhouette ---------------------------------------------------

    def test_the_silhouette_is_the_body_and_nothing_hangs_outside_it(self):
        """The regression test for the bug that motivated the rewrite.

        The accent used to be painted where it fell OUTSIDE the glyph, so an
        icon's real outline was its glyph union a disc or a bar hanging in empty
        space past the edge of the mark. At apps-menu size that read as a
        rendering fault. Every opaque pixel must lie inside the body now, and
        this has to hold for both geometry sources - the authored silhouettes
        and the glyphs - because they go through one compositor.
        """
        side = 256
        for module in sorted(set(MAPPED) | set(app_icons.AUTHORED_ART)):
            design = app_icons.resolve_design(app_icons.design_for(module))
            body = app_icons.body_alpha(design, side)
            painted = None
            for mask, _colour in app_icons.plane_masks(design, side):
                painted = mask if painted is None else ImageChops.lighter(painted, mask)
            outside = app_icons._mask_area(ImageChops.subtract(painted, body))
            self.assertLess(outside / max(app_icons._mask_area(body), 1.0), 0.001,
                            f"{module} paints {outside:.0f} px of ink outside its own silhouette")

    def test_the_planes_partition_the_body_without_a_halo(self):
        """The planes are a partition, not a stack of overlapping shapes: they
        sum to the body's coverage at every alpha, so no seam between them
        renders as a translucent line. Fails if a plane is dropped, if two
        planes double-count the crossing, or if either mask operation is
        reverted to a subtraction that is not alpha-correct."""
        side = 256
        for module in sorted(set(MAPPED) | set(app_icons.AUTHORED_ART)):
            design = app_icons.resolve_design(app_icons.design_for(module))
            ink = app_icons._mask_area(app_icons.body_alpha(design, side))
            total = sum(app_icons._mask_area(m) for m, _c in app_icons.plane_masks(design, side))
            self.assertAlmostEqual(total / ink, 1.0, delta=0.002,
                                   msg=f"{module}'s planes cover {total / ink:.3f} of its body, not 1.000")

    def test_the_band_gives_every_mapped_icon_a_real_third_colour(self):
        """Clipping the accent to the body costs colour B its own area - an
        accent wholly inside the body has no outside part left to carry it - so
        the xForge band exists to cut the accent in two and put the third colour
        back at the crossing of two planes.

        It has to be PLACED to do that. Measured with one fixed band across
        every icon, 17 of the 50 lost a plane: the accent either missed the band
        entirely (project, purchase, survey at 0.000) or sat wholly inside it
        (web, crm, board at 0.001). This is the gate on that.
        """
        side = 256
        floor = 0.02
        for module in MAPPED:
            design = app_icons.resolve_design(app_icons.design_for(module))
            ink = app_icons._mask_area(app_icons.body_alpha(design, side))
            planes = app_icons.plane_masks(design, side)
            self.assertEqual(len(planes), 3, f"{module} does not render three planes")
            for name, (mask, _c) in zip(("colour A", "colour B", "the crossing"), planes):
                share = app_icons._mask_area(mask) / ink
                self.assertGreater(share, floor,
                                   f"{module}: {name} covers {share:.1%} of the body, under the {floor:.0%} floor")

    def test_every_authored_shape_parses_and_stays_inside_its_artboard(self):
        """The authored art is the other geometry source, and it is data rather
        than code, so it gets the same scrutiny the glyphs get from the cmap
        test: every path parses to real contours, and nothing strays outside the
        artboard it was drawn in."""
        from afenda.tools.xforge_icons.v4_shapes import H, W
        self.assertTrue(app_icons.AUTHORED_SHAPES, "there is no authored art")
        for key, builder in sorted(app_icons.AUTHORED_SHAPES.items()):
            for micro in (False, True):
                art = builder(micro)
                self.assertIn("body", art, f"{key} (micro={micro}) declares no body")
                for role, d in art.items():
                    if not isinstance(d, str):
                        continue  # marks and stages carry coordinates, not paths
                    contours = flatten_path(d)
                    self.assertTrue(contours, f"{key}.{role} parses to nothing")
                    x0, y0, x1, y1 = path_bounds(contours)
                    self.assertTrue(-W <= x0 and x1 <= 2 * W and -H <= y0 and y1 <= 2 * H,
                                    f"{key}.{role} runs to ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})")

    def test_a_module_without_authored_art_still_renders(self):
        """One pipeline, two geometry sources: the 83 modules with no art of
        their own must keep working, and must go through the glyph. Fails if the
        authored path becomes mandatory."""
        for module in ("sms", "calendar", "x_technical"):
            design = app_icons.design_for(module)
            self.assertIsNone(design.art, f"{module} unexpectedly has authored art")
            im = app_icons.icon_png(64, 64, design)
            self.assertEqual(im.size, (64, 64))
            self.assertTrue(_colours(im), f"{module} rendered nothing")

    # --- V2 quality gates -------------------------------------------------

    def test_the_three_masks_decompose_the_glyph_without_a_halo(self):
        """Alpha-correct decomposition, asserted where it differs from the
        subtraction it replaced: the antialiased rim, where the glyph and the
        accent both sit at partial coverage.

        A*(1-B) + A*B == A at every alpha. ImageChops.subtract does not satisfy
        that - at glyph 128 against accent 128 it gives 0 for the glyph-only
        layer and 64 for the intersection, so half the glyph's coverage
        disappears and the seam between the two shapes renders as a translucent
        halo. Fails on reverting either _mask_only or _mask_intersection to
        subtract, and on the two being swapped.
        """
        flat = Image.new("L", (32, 32), 128)
        self.assertAlmostEqual(
            app_icons._mask_area(app_icons._mask_only(flat, flat))
            + app_icons._mask_area(app_icons._mask_intersection(flat, flat)),
            app_icons._mask_area(flat), delta=32 * 32 / 255.0,
            msg="at half coverage the glyph-only and overlap layers do not add back up to the glyph")
        # And on real ink, where the partial-coverage rim is a thin ring rather
        # than the whole canvas.
        for module in sorted(app_icons.ACCENTS):
            design = app_icons.design_for(module)
            glyph = app_icons._glyph_alpha(design, 256)
            accent = app_icons.accent_mask(design.shape, 256)
            ink = app_icons._mask_area(glyph)
            parts = (app_icons._mask_area(app_icons._mask_only(glyph, accent))
                     + app_icons._mask_area(app_icons._mask_intersection(glyph, accent)))
            self.assertAlmostEqual(parts / ink, 1.0, delta=0.002,
                                   msg=f"{module} loses {1 - parts / ink:.2%} of its ink at the accent seam")

    def test_no_glyph_is_cropped_at_the_canvas_edge(self):
        """At every size the apps menu asks for. The glyph is GLYPH_SCALE of the
        short side, so it clears the border by about 8% of it - but the accent
        bleeds off the canvas on purpose, so "does anything touch the edge" is
        the wrong question. What may not touch the edge is glyph ink: colour A,
        or the overlap colour, which only exists where the glyph is.

        Fails on GLYPH_SCALE going back above 1.0, on the centring paste losing
        its floor division, and on an accent being composited under the glyph
        rather than over it (which would paint A out to the bleeding edge).
        """
        designs = [(m, app_icons.design_for(m)) for m in sorted(app_icons.ACCENTS)]
        designs += [(f"base/{s}", d) for s, d in sorted(app_icons.BASE_ICONS.items())]
        for name, design in designs:
            colours = [app_icons.rgb(design.glyph)]
            accent = None
            if design.accent:
                colours.append(app_icons.rgb(design.accent))
                colours.append(app_icons.controlled_overlap_colour(colours[0], colours[1]))
                accent = 1
            for size in (16, 24, 32, 48, 64, 128):
                im = app_icons.icon_png(size, size, design)
                px = im.load()
                edge = {(x, y) for x in range(size) for y in (0, size - 1)}
                edge |= {(x, y) for y in range(size) for x in (0, size - 1)}
                cropped = sorted(p for p in edge
                                 if px[p][3] >= 250 and _nearest(px[p], colours) != accent)
                self.assertEqual(cropped, [],
                                 f"{name} at {size}px: glyph ink runs off the canvas at {cropped[:4]}")

    def test_modules_that_share_a_glyph_stay_apart(self):
        """sale and sale_management are one app in two packages; sms and
        mass_mailing_sms are two apps drawn with one bubble; hr_expense and
        payment both use the receipt. Each pair is one glyph, so the accent is
        the only thing telling them apart in the menu.

        Fails if a duplicated glyph is added without also differing in accent,
        and if the accent that is meant to separate two of them is moved to a
        shape and colour that renders near enough identically to be useless.
        """
        groups = defaultdict(list)
        for module, code in app_icons.APP_GLYPHS.items():
            groups[code].append(module)
        shared = {code: mods for code, mods in groups.items() if len(mods) > 1}
        self.assertGreaterEqual(len(shared), 3, "the known same-glyph pairs are gone; re-derive this test")
        for code, modules in sorted(shared.items()):
            for i, first in enumerate(modules):
                for second in modules[i + 1:]:
                    self.assertNotEqual(app_icons.ACCENTS[first], app_icons.ACCENTS[second],
                                        f"{first} and {second} share U+{code.upper()} and their whole accent")
                    a = app_icons.icon_png(64, 64, app_icons.design_for(first))
                    b = app_icons.icon_png(64, 64, app_icons.design_for(second))
                    differing = sum(max(band) > 8 for band in
                                    ImageChops.difference(a, b).getdata()) / (64 * 64)
                    self.assertGreater(differing, 0.05,
                                       f"{first} and {second} differ on only {differing:.1%} of the icon")
        # The two payment providers carry different glyphs outright, so they are
        # told apart before the accent is reached at all.
        self.assertNotEqual(app_icons.APP_GLYPHS["payment_custom"], app_icons.APP_GLYPHS["payment_demo"])

    def test_png_and_svg_are_the_same_icon(self):
        """The two are served side by side in the apps menu, so a browser
        picking one over the other must not change the picture.

        No SVG rasteriser is installed in this venv (no cairosvg, no svglib), so
        this is structural rather than pixel-by-pixel: the same three colours,
        and the same accent at the same coordinates in the same 0..100 box.
        Fails if either renderer is changed alone - a different overlap colour,
        an accent scaled in one box and not the other, a shape resolved twice to
        two different answers.
        """
        for module, svg in self.svgs.items():
            design = app_icons.resolve_design(app_icons.design_for(module))
            png_colours = set(_colours(app_icons.icon_png(UNRESAMPLED, UNRESAMPLED, design)))
            svg_colours = {app_icons.rgb(c) for c in re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg)}
            self.assertEqual(png_colours, svg_colours,
                             f"{module}: the PNG and the SVG are not drawn in the same colours")
            if not design.accent:
                continue
            kind, geom = app_icons.ACCENT_SHAPES[design.shape]
            element = app_icons._accent_svg(design.shape)
            self.assertIn(element, svg, f"{module}: the SVG does not carry its {design.shape} accent")
            u = app_icons.SVG_SIDE / 100.0
            if kind == "polygon":
                points = re.search(r'points="([^"]+)"', element).group(1)
                got = [tuple(float(v) for v in p.split(",")) for p in points.split()]
                want = [(x * u, y * u) for x, y in geom]
            else:
                attrs = {k: float(v) for k, v in re.findall(r'(\w+)="(-?[\d.]+)"', element)}
                if kind == "circle":
                    got = [attrs["cx"], attrs["cy"], attrs["r"]]
                    want = [v * u for v in geom]
                else:
                    x0, y0, x1, y1, r = geom
                    got = [attrs["x"], attrs["y"], attrs["width"], attrs["height"], attrs["rx"]]
                    want = [x0 * u, y0 * u, (x1 - x0) * u, (y1 - y0) * u, r * u]
            self.assertEqual(got, want,
                             f"{module}: the SVG accent is not the mask's geometry scaled to the viewBox")

    def test_svg_clip_ids_are_unique_per_icon(self):
        """Ids are document-global. A constant id is fine while every icon.svg
        is its own image resource and wrong the moment two are inlined into one
        page: the second icon's clip resolves to the first icon's accent, so its
        overlap layer is drawn through the wrong shape.

        Fails on going back to a constant, and on deriving the id from anything
        that does not separate two icons - the shape alone, say.
        """
        designs = {m: app_icons.resolve_design(app_icons.design_for(m)) for m in app_icons.ACCENTS}
        designs.update({f"base/{s}": app_icons.resolve_design(d)
                        for s, d in app_icons.BASE_ICONS.items() if d.accent})
        ids = {name: app_icons.svg_clip_id(d) for name, d in designs.items()}
        self.assertGreater(len(ids), 40)
        # One id per distinct picture. Three of the odoo/addons/base icons
        # deliberately reuse a module's design outright (settings is base's,
        # modules is web's, board is board's), and two identical pictures
        # sharing a clip id is right: the clip resolves to the same accent.
        self.assertEqual(len(set(ids.values())), len(set(designs.values())),
                         "two different icons share a clip id")
        collisions = defaultdict(set)
        for name, clip in ids.items():
            collisions[clip].add(designs[name])
        for clip, sharing in collisions.items():
            self.assertEqual(len(sharing), 1, f"{clip} is shared by {sharing}")
        account = designs["account"]
        for changed in (account._replace(code="f0f2"), account._replace(glyph=app_icons.PLUM),
                        account._replace(accent=app_icons.OCHRE), account._replace(shape="dot-br"),
                        account._replace(art=None)):
            self.assertNotEqual(app_icons.svg_clip_id(changed), app_icons.svg_clip_id(account),
                                f"the clip id ignores {changed}")
        # and it is the id the file on disk actually declares and refers to.
        # Two clips are derived from it now - the accent and the band - so the
        # counts are per derived id rather than one total: declared once each,
        # and the accent referenced twice because both the colour-B plane and
        # the crossing plane sit inside it.
        for module in MAPPED:
            if module not in self.svgs:
                continue
            svg = self.svgs[module]
            self.assertEqual(svg.count(f'id="{ids[module]}-accent"'), 1, module)
            self.assertEqual(svg.count(f'id="{ids[module]}-band"'), 1, module)
            self.assertEqual(svg.count(f'url(#{ids[module]}-accent)'), 2, module)
            self.assertEqual(svg.count(f'url(#{ids[module]}-band)'), 1, module)

    def test_an_unmapped_accent_is_placed_by_the_scorer(self):
        """A Design with no shape is a module nobody has art-directed. It gets a
        scored placement rather than a crash or a silently monotone icon - and
        the PNG and the SVG must land on the same one, which is why render_all
        resolves once and hands the concrete design to both.

        Fails if the scorer is bypassed, if it can return something that is not
        a real candidate, or if the SVG is allowed to serialise an unresolved
        shape and quietly pick its own.
        """
        blank = app_icons.Design(app_icons.APP_GLYPHS["stock"], app_icons.TEAL, app_icons.OCHRE)
        self.assertIsNone(blank.shape)
        resolved = app_icons.resolve_design(blank)
        self.assertIn(resolved.shape, app_icons.AUTO_ACCENT_CANDIDATES)
        self.assertEqual(app_icons.resolve_design(blank._replace(shape=app_icons.AUTO)), resolved)
        with self.assertRaises(ValueError):
            app_icons.icon_svg(blank)
        with self.assertRaises(ValueError):
            app_icons.icon_svg(blank._replace(shape=app_icons.AUTO))
        self.assertIn(app_icons.svg_clip_id(resolved), app_icons.icon_svg(resolved))
        self.assertEqual(app_icons.icon_png(120, 120, blank).tobytes(),
                         app_icons.icon_png(120, 120, resolved).tobytes())
        # A scored placement is held to the same ceiling as a hand-placed one.
        self.assertLessEqual(app_icons.accent_overlap(resolved), app_icons.MAX_OVERLAP)
        # The shards are offered, and nothing in the shipped tables uses one:
        # adding a candidate is not the same as reassigning an icon.
        self.assertTrue({s for s in app_icons.AUTO_ACCENT_CANDIDATES if s.startswith("shard-")})
        self.assertEqual({s for _g, _a, s in app_icons.ACCENTS.values() if s.startswith("shard-")}, set())

    def test_the_accent_scorer_prefers_a_deliberate_crossing(self):
        """The scorer is only worth having if its ranking means something.
        Against a square glyph, a band covering about a fifth of it must beat
        one that barely grazes it and one that swallows it.

        Fails if accent_score returns a constant, if the distance-from-target
        term loses its absolute value, or if the out-of-band penalties go."""
        side = 200
        glyph = Image.new("L", (side, side), 0)
        ImageDraw.Draw(glyph).rectangle((20, 20, 179, 179), fill=255)

        def band(share: float) -> Image.Image:
            mask = Image.new("L", (side, side), 0)
            ImageDraw.Draw(mask).rectangle((20, 180 - round(160 * share), 179, 179), fill=255)
            return mask

        target = app_icons.accent_score(glyph, band(0.20))
        self.assertLess(target, app_icons.accent_score(glyph, band(0.02)),
                        "an accent that grazes the glyph scores as well as one that crosses it")
        self.assertLess(target, app_icons.accent_score(glyph, band(0.60)),
                        "an accent that swallows the glyph scores as well as one that crosses it")
        self.assertLess(target, app_icons.accent_score(glyph, band(0.95)))
        self.assertLess(app_icons.accent_score(glyph, band(0.60)), app_icons.accent_score(glyph, band(0.95)))

    def test_the_accent_overlap_band_is_reported(self):
        """OVERLAP_BAND is reported, never enforced, and this is where it is
        reported. Thirty of the forty-five mapped modules sit above it; each of
        those accents was placed by eye, so turning the band into a gate would
        bulk-reassign two thirds of the family to fix a number nobody has looked
        at. test_the_accent_never_swallows_the_glyph is the gate instead.

        GLYPH_SCALE moved 0.88 -> 0.84 in V2 and every share below moved with
        it - a smaller glyph leaves more of a fixed accent outside itself.
        Re-measure before arguing to tighten the gate toward the band.

        What this asserts is only that the report is real: one row per mapped
        module, every share a fraction of the ink. So it cannot go blind while
        still printing something reassuring.
        """
        report = app_icons.overlap_report()
        self.assertEqual(sorted(m for m, _s in report), sorted(app_icons.ACCENTS))
        low, high = app_icons.OVERLAP_BAND
        outside = [(m, s) for m, s in report if not low <= s <= high]
        print(f"\n  accent overlap at GLYPH_SCALE {app_icons.GLYPH_SCALE}: "
              f"{len(report) - len(outside)}/{len(report)} inside {low:.0%}-{high:.0%}, "
              f"{len(outside)} outside")
        for module, share in outside:
            print(f"    {share:6.1%}  {module}" + ("   <- no overlap, so no third colour" if not share else ""))
        for module, share in report:
            self.assertTrue(0.0 <= share <= 1.0, f"{module}: {share} is not a share of the ink")
            self.assertLessEqual(share, app_icons.MAX_OVERLAP, module)

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
                    expected += [b, app_icons.controlled_overlap_colour(expected[0], b)]
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

    def test_the_accent_never_swallows_the_glyph(self):
        """The accent exists to add a second colour and a third where it crosses
        the glyph. Past half the glyph's ink it stops reading as an accent and
        starts reading as a stain, and the thing the icon is meant to say goes
        with it.

        Measured across the whole set at GLYPH_SCALE 0.84, the spread runs from
        0.0% (website_forum, whose wedge no longer reaches the glyph at all) to
        49.6% (event), and the worst offenders are the ones that look wrong: the
        accent disc sat behind the shopping basket's slats and turned the lower
        half into a brown mass. The ceiling is set at half because above that the
        accent is the larger shape. event sits 0.4 points under it, so this has
        very little slack left.

        Fails on: moving an accent so it lands on the glyph's body rather than in
        its empty space, growing an accent shape without re-checking the set, or
        shrinking GLYPH_SCALE further without re-checking it either.
        """
        worst = [f"{m} {s:.1%}" for m, s in app_icons.overlap_report() if s > app_icons.MAX_OVERLAP]
        self.assertEqual(
            worst, [],
            "the accent covers more than half the glyph on: " + ", ".join(worst),
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
