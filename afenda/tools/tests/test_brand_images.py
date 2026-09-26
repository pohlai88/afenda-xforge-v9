import colorsys
import io
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from afenda.tools import brand_images
from afenda.tools.rules import load_brand
from afenda.tools.brand_images import (
    ADDON_TARGETS,
    CONTRACT,
    IN_PRODUCT,
    LIGHT,
    PRIMARY,
    TARGETS,
    _solid,
    render_all,
    rgb,
    tile_png,
)

ALL_TARGETS = {**TARGETS, **ADDON_TARGETS}

# A lockup drawn on its blue tile covers ~11% of the canvas in fully opaque
# pixels; the bare mark the white lockups use covers ~4%. Anything above this
# threshold means the tile came back behind the mark.
MAX_OPAQUE_FRACTION = 0.08

# The Engineered X exactly as the signed-off artwork draws it, in its own
# 100-unit frame. Transcribed from the artwork a second time, by hand, so that
# this file and brand_images are two independent copies: an accidental edit to
# the geometry has to be made twice, identically, to get past the suite.
SIGNED_OFF_ARMS = (
    ((23, 23), (39.8, 23), (49.25, 46.25), (46.25, 49.25)),
    ((23, 77), (39.8, 77), (49.25, 53.75), (46.25, 50.75)),
    ((77, 23), (60.2, 23), (50.75, 46.25), (53.75, 49.25)),
    ((77, 77), (60.2, 77), (50.75, 53.75), (53.75, 50.75)),
)
SIGNED_OFF_COLOURWAYS = {
    "PRIMARY": ("#09111F", ("#D9DEE5", "#AAB3C0", "#659CFF", "#1F6FFF"), 0.225, None),
    "LIGHT": ("#FFFFFF", ("#6C7581", "#464F5A", "#1F6FFF", "#0049C1"), 0.225, "#E3E8EF"),
    "IN_PRODUCT": ("#1E3A8A", ("#FFFFFF",) * 4, 0.20, None),
}

# Rendered big enough that LANCZOS is not asked to invent an intermediate
# colour anywhere but on the wedges' own edges.
BIG = 512


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
        rels = [rel for rel, k in ALL_TARGETS.items() if k == kind]
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
        self.assertEqual(sorted(p.relative_to(self.root).as_posix() for p in self.written), sorted(ALL_TARGETS))
        for rel, kind in ALL_TARGETS.items():
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


class MarkGeometryTests(unittest.TestCase):
    """The shape itself, independent of any file it is written into."""

    def test_mark_is_the_signed_off_geometry(self):
        self.assertEqual(brand_images.MARK_ARMS, SIGNED_OFF_ARMS)
        self.assertEqual(brand_images.MARK_FRAME, 100.0)
        self.assertEqual(brand_images.MARK_BOX, (23.0, 23.0, 77.0, 77.0))

    def test_mark_is_symmetric_about_both_diagonals(self):
        """Four wedges that have drifted apart still render; they just stop
        being the mark. Mirroring x maps the western pair onto the eastern one
        and mirroring y maps north onto south, so both axes are checked."""
        nw, sw, ne, se = brand_images.MARK_ARMS
        flip_x = lambda arm: tuple((100 - x, y) for x, y in arm)
        flip_y = lambda arm: tuple((x, 100 - y) for x, y in arm)
        self.assertEqual(flip_x(nw), ne, "the mark is not symmetric left to right")
        self.assertEqual(flip_x(sw), se, "the mark is not symmetric left to right")
        self.assertEqual(flip_y(nw), sw, "the mark is not symmetric top to bottom")
        self.assertEqual(flip_y(ne), se, "the mark is not symmetric top to bottom")

    def test_wedges_taper_onto_a_diamond_void(self):
        """Each wedge is wide at the frame and narrow at the centre, and the
        narrow end is a flat cut rather than a point. The void those four cuts
        leave is what stops the halves fusing into a blob at 16px, so it has to
        be a real width - not a hairline the renderer can round away."""
        for i, arm in enumerate(brand_images.MARK_ARMS):
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = arm
            outer = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            tip = ((x2 - x3) ** 2 + (y2 - y3) ** 2) ** 0.5
            self.assertAlmostEqual(outer, 16.8, places=6, msg=i)
            self.assertAlmostEqual(tip, 18 ** 0.5, places=6, msg=i)
            self.assertGreater(outer / tip, 3.0, f"wedge {i} barely tapers")
        # The void's own width: the gap between the western and eastern tips,
        # measured across the centre at the height where both cuts begin.
        nw, _, ne, _ = brand_images.MARK_ARMS
        self.assertEqual(nw[2][1], ne[2][1], "the two tips no longer start at the same height")
        self.assertAlmostEqual(ne[2][0] - nw[2][0], 1.5, places=6, msg="the diamond void has closed up")

    def test_arms_project_without_moving_the_mark(self):
        """Every renderer scales MARK_ARMS through arms_at/arms_in, so the whole
        identity rides on those two being exact. A tile's mark must land on the
        artwork's own 23% inset and 54% occupancy at any size."""
        for frame in (16, 64, 100, 512):
            arms = brand_images.arms_in(frame, brand_images.BOXED_INK)
            xs = [x for arm in arms for x, _ in arm]
            ys = [y for arm in arms for _, y in arm]
            self.assertAlmostEqual(min(xs), frame * 0.23, places=6, msg=frame)
            self.assertAlmostEqual(min(ys), frame * 0.23, places=6, msg=frame)
            self.assertAlmostEqual(max(xs) - min(xs), frame * 0.54, places=6, msg=frame)
            self.assertAlmostEqual(max(ys) - min(ys), frame * 0.54, places=6, msg=frame)

    def test_tile_svg_is_the_artwork(self):
        """The SVG is the one output that can be diffed against the artwork
        character for character, so it is worth asserting literally."""
        self.assertIn('rx="22.5" fill="#09111F"', brand_images.tile_svg(PRIMARY))
        self.assertIn('d="M 23 23 L 39.8 23 L 49.25 46.25 L 46.25 49.25 Z" fill="#D9DEE5"',
                      brand_images.tile_svg(PRIMARY))
        self.assertIn('rx="20" fill="#1E3A8A"', brand_images.tile_svg(IN_PRODUCT))
        self.assertIn('stroke="#E3E8EF"', brand_images.tile_svg(LIGHT))


class ColourwayTests(unittest.TestCase):
    """The three approved renderings, and which surface is allowed which."""

    def test_colourways_are_the_signed_off_values(self):
        for name, (ground, fills, radius, edge) in SIGNED_OFF_COLOURWAYS.items():
            cw = getattr(brand_images, name)
            self.assertEqual((cw.ground, cw.fills, cw.radius, cw.edge), (ground, fills, radius, edge), name)

    def test_every_target_kind_is_rendered_and_contracted(self):
        """A new kind in TARGETS with no branch in render_all raises at render
        time; a new kind with no CONTRACT entry does not, it just quietly draws
        whatever the default colourway happens to be. This closes that."""
        tile_kinds = {k for k in set(ALL_TARGETS.values()) if k.startswith(("tile_", "badge_"))}
        self.assertEqual(tile_kinds, set(CONTRACT), "a mark-bearing kind has no colourway contracted to it")

    def test_contract_is_what_render_all_actually_reads(self):
        """The test above only proves CONTRACT is populated, not that anything
        consults it -- and for a while nothing did for two of the four kinds:
        render_all hardcoded IN_PRODUCT for tile_svg and tile_ico, so editing
        their contract changed nothing on disk and this file stayed green.

        Repoint every mark-bearing kind at PRIMARY and re-render into a scratch
        tree: each one has to come back carrying PRIMARY's ground. A kind that
        ignores CONTRACT keeps its old ground and fails here.
        """
        import tempfile
        from unittest import mock
        ground = rgb(PRIMARY.ground)
        forced = dict.fromkeys(CONTRACT, PRIMARY)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(brand_images.CONTRACT, forced, clear=True):
            root = Path(tmp)
            render_all(root)
            for rel, kind in ALL_TARGETS.items():
                if kind not in forced:
                    continue
                if rel.endswith(".svg"):
                    self.assertIn(f'fill="{PRIMARY.ground}"', (root / rel).read_text(encoding="utf-8"),
                                  f"{rel} ({kind}) did not follow CONTRACT to PRIMARY")
                    continue
                with Image.open(root / rel) as im:
                    corner = im.convert("RGB").getpixel((im.width // 2, max(1, im.height // 100)))
                self.assertEqual(corner, ground,
                                 f"{rel} ({kind}) did not follow CONTRACT to PRIMARY")

    def test_the_badge_is_two_tone_and_the_product_mark_is_not(self):
        """The whole point of the four-fill pipeline, in one assertion. The
        badge shows all four of its fills; the in-product mark is one white."""
        self.assertEqual(len(set(PRIMARY.fills)), 4, "the badge is no longer four distinct fills")
        self.assertEqual(_wedge_colours(PRIMARY), [rgb(f) for f in PRIMARY.fills],
                         "the badge is not drawing its four fills, wedge for wedge")
        self.assertEqual(set(_wedge_colours(IN_PRODUCT)), {rgb("#FFFFFF")},
                         "the in-product mark is carrying more than one fill")
        self.assertEqual(_wedge_colours(LIGHT), [rgb(f) for f in LIGHT.fills])

    def test_each_colourway_keeps_its_own_corner_radius(self):
        """22.5% for the badge and 20% in-product are different numbers on
        purpose. Read it off the pixels: at 6% in from a corner the badge is
        still cut away and the tighter in-product tile is not."""
        for cw, cut in ((PRIMARY, True), (IN_PRODUCT, False)):
            alpha = tile_png(BIG, cw).getchannel("A")
            self.assertEqual(alpha.getpixel((0, 0)), 0, "a tile corner is not rounded at all")
            probe = round(BIG * 0.06)
            self.assertEqual(alpha.getpixel((probe, probe)) == 0, cut,
                             f"radius {cw.radius} is not what got drawn")

    def test_the_light_tile_ends_itself_with_a_hairline(self):
        """A white tile on a white page has no edge without it."""
        im = tile_png(BIG, LIGHT).convert("RGBA")
        edge = im.getpixel((BIG // 2, 1))[:3]
        self.assertNotEqual(edge, rgb(LIGHT.ground), "the white tile has no hairline and dissolves into the page")


def _wedge_colours(cw) -> list:
    """The colour actually painted at the centre of each of the four wedges.

    Sampling beats collecting every opaque colour: the tile is supersampled and
    resized, so each wedge's edge contributes a smear of blends that are just as
    opaque as its fill. The centroid of a convex quad is inside it, and the
    artwork's coordinates are the tile's own coordinates scaled by side/100.
    """
    im = tile_png(BIG, cw).convert("RGB")
    out = []
    for arm in brand_images.MARK_ARMS:
        cx = sum(x for x, _ in arm) / len(arm) * BIG / brand_images.MARK_FRAME
        cy = sum(y for _, y in arm) / len(arm) * BIG / brand_images.MARK_FRAME
        out.append(im.getpixel((round(cx), round(cy))))
    return out


ROOT = Path(__file__).resolve().parents[3]
# The colours Odoo draws its own artwork in. #985184 and #1AD3BB are the pair
# afenda_brand's own icon test names as Odoo artwork; the three purples are
# what rules.py rewrites everywhere that is text rather than artwork.
ODOO_ARTWORK_COLOURS = ("714b67", "875a7b", "7c7bad", "985184", "1ad3bb")
_ODOO_ARTWORK = re.compile("#(?:" + "|".join(ODOO_ARTWORK_COLOURS) + r")\b", re.I)


class SvgRecolourTests(unittest.TestCase):
    """The upstream illustrations carrying Odoo brand colour.

    These are the asset half of the brand problem. `.svg` is deliberately
    absent from rebrand.TEXT_SUFFIXES, so no rule reaches them and only this
    table does -- which means nothing but a test keeps the table honest.
    """

    def test_no_svg_in_the_tree_still_carries_an_odoo_brand_colour(self):
        """The one that catches an upstream refresh adding an eighteenth file.

        Scanning beats trusting RECOLOUR: a hand-maintained list of paths is
        exactly the thing that goes stale when upstream ships a new
        illustration, and the failure is invisible -- a purple drawing in a
        rebranded product that nobody is looking for.
        """
        offenders = []
        for top in ("addons", "odoo", "afenda"):
            base = ROOT / top
            if not base.is_dir():
                continue
            for path in base.rglob("*.svg"):
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                hits = _ODOO_ARTWORK.findall(text)
                if hits:
                    offenders.append(f"{path.relative_to(ROOT).as_posix()} ({len(hits)})")
        self.assertEqual(
            offenders, [],
            "an SVG still carries Odoo brand colour; add it to "
            "brand_images.RECOLOUR and re-run the module:\n  " + "\n  ".join(offenders),
        )

    def test_every_listed_path_exists_and_is_actually_recoloured(self):
        """A dead entry in RECOLOUR is a lie about what the table covers.

        Both halves matter. A path that no longer exists means upstream moved
        the file and the colour went unrewritten somewhere else; a path that
        exists but contains no Odoo colour once meant something and now only
        suggests the table is bigger than the problem.
        """
        missing = [r for r in brand_images.RECOLOUR if not (ROOT / r).is_file()]
        self.assertEqual(missing, [], f"RECOLOUR names files that do not exist: {missing}")

        upstream = {}
        for rel in brand_images.RECOLOUR:
            blob = subprocess.run(
                ["git", "show", f"archive/upstream-19.0:{rel}"],
                cwd=ROOT, capture_output=True, text=True,
            )
            if blob.returncode == 0:
                upstream[rel] = len(_ODOO_ARTWORK.findall(blob.stdout))
        if not upstream:
            self.skipTest("archive/upstream-19.0 is not available in this checkout")
        inert = [rel for rel, n in upstream.items() if n == 0]
        self.assertEqual(
            inert, [],
            f"RECOLOUR lists files that carry no Odoo colour upstream either: {inert}",
        )

    def test_the_two_odoo_purples_do_not_collapse_to_one_brand_colour(self):
        """Inside one drawing a shade pair has to stay a pair.

        The text rule in rules.py sends both purples to the primary, which is
        right for SCSS where the lighter one is a variant of the darker. Doing
        that here would flatten account/multi_ledger.svg, the one file that
        carries both, into a single-colour silhouette.
        """
        swatch = brand_images.SVG_SWATCH
        self.assertNotEqual(
            swatch["#714b67"], swatch["#875a7b"],
            "the two Odoo purples map to the same brand colour and the artwork flattens",
        )

    def test_recolouring_is_idempotent_and_preserves_line_endings(self):
        """Re-running must be a no-op, including on the CRLF file.

        base_automation/automation.svg is CRLF where the rest of the table is
        LF. Translating on write turned its one-colour change into a 25-line
        diff, which is how a colour edit hides inside a whitespace edit.
        """
        once = brand_images.recolour_svg('a="#714B67" b="#875a7b" c="#1AD3BB"')
        self.assertEqual(brand_images.recolour_svg(once), once, "recolour is not idempotent")

        crlf = 'x="#714B67"\r\ny="1"\r\n'
        out = brand_images.recolour_svg(crlf)
        self.assertEqual(out.count("\r\n"), 2, "recolour_svg dropped a CRLF")
        self.assertNotIn("#714B67", out)

    def test_every_replacement_colour_is_in_the_brand_palette(self):
        """A recolour that invents a colour is a second palette by accident."""
        brand = load_brand()
        allowed = {brand["primary"].upper(), *(t.upper() for t in brand["tags"])}
        for odoo, replacement in brand_images.SVG_SWATCH.items():
            self.assertIn(
                replacement.upper(), allowed,
                f"{odoo} maps to {replacement}, which is not in BRAND",
            )


class RecolouredFilesAreCoherentTests(unittest.TestCase):
    """The guard that the five-hex check was not.

    `test_no_svg_in_the_tree_still_carries_an_odoo_brand_colour` looks for five
    known hexes, and it passed while neutral_face.svg, smiling_face.svg and
    survey_background_sample.svg each sat half-recoloured: Odoo ships shade
    VARIANTS of its purple (#6B4862, #7D5372, #906083) that no grep for the
    canonical three will ever find. Each of those files had one hex swapped to
    a brand blue and a variant left behind, so the drawing came out blue and
    purple at once - worse than leaving it alone, and invisible to a colour
    count. This checks the property that actually matters: a file this table
    claims to have recoloured carries no purple that is not ours.
    """

    def test_no_recoloured_file_keeps_a_purple_that_is_not_ours(self):
        brand = load_brand()
        ours = {brand["primary"].upper(), *(t.upper() for t in brand["tags"])}
        # Plus the crossings the icon generator legitimately produces where two
        # brand tags overlap; those are derived from BRAND, not left over from
        # Odoo, and they are purple by construction when two purples cross.
        from afenda.tools.app_icons import controlled_overlap_colour
        for a in list(ours):
            for b2 in list(ours):
                r, g, bl = controlled_overlap_colour(
                    tuple(int(a[i:i + 2], 16) for i in (1, 3, 5)),
                    tuple(int(b2[i:i + 2], 16) for i in (1, 3, 5)))
                ours.add("#%02X%02X%02X" % (r, g, bl))

        offenders = {}
        for rel in brand_images.RECOLOUR:
            path = ROOT / rel
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            left = sorted({
                f"#{m.group(1).upper()}"
                for m in re.finditer(r"#([0-9a-fA-F]{6})\b", text)
                if _is_purple_family(m.group(1)) and f"#{m.group(1).upper()}" not in ours
            })
            if left:
                offenders[rel] = left
        self.assertEqual(
            offenders, {},
            "a recoloured SVG still carries a non-brand purple, so the drawing "
            "is part blue and part purple; add the shade to SVG_SWATCH:\n"
            + "\n".join(f"  {k}: {v}" for k, v in offenders.items()),
        )


def _is_purple_family(hex6: str) -> bool:
    """Hue 260-340 with enough saturation and mid lightness to read as purple.

    Hue rather than a hex list, because the hex list is exactly what missed the
    shade variants. The saturation and value floors keep near-greys and
    near-blacks out, which would otherwise swamp the result.
    """
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, sat, val = colorsys.rgb_to_hsv(r, g, b)
    return 260 <= hue * 360 <= 340 and sat >= 0.18 and 0.15 <= val <= 0.85
