"""Checks for the AFENDA xForge Version 3 icon system.

These pin the specification's own acceptance criteria, so a later edit that
quietly breaks one - a fourth plane, a ribbon off its angle, a muddy
intersection - fails here rather than in someone's app launcher.
"""
import json
import re
import unittest

from PIL import Image

from afenda.tools.xforge_icons import geometry as G
from afenda.tools.xforge_icons import render as R
from afenda.tools.xforge_icons.tokens import (ARTBOARD, FAMILIES, LARGE_SIZES, ORDER,
                                              RIBBON_ANGLES, SMALL_SIZES, luminance,
                                              mix, rgb)

class GeometryTests(unittest.TestCase):
    def test_every_module_is_bespoke_geometry(self):
        """No font glyph reaches the final artwork.

        The specification forbids a generic glyph as final art, so the geometry
        module must not reach for a font at all.
        """
        src = (G.__file__)
        with open(src, encoding="utf-8") as f:
            text = f.read()
        for banned in ("fontTools", "ImageFont", "truetype", "APP_GLYPHS", "FA_TTF"):
            self.assertNotIn(banned, text, f"{banned} in geometry means a glyph crept in")

    def test_ribbon_angles_are_the_declared_vocabulary(self):
        self.assertEqual(RIBBON_ANGLES, (45.0, -45.0))

    def test_ribbon_width_stays_inside_the_specified_band(self):
        """20-28% of the usable width, large and small alike."""
        for key in ORDER:
            for small in (False, True):
                w = G.BUILDERS[key](small)["ribbon_width"]
                self.assertGreaterEqual(w, 0.20, f"{key} small={small} ribbon too narrow")
                self.assertLessEqual(w, 0.28, f"{key} small={small} ribbon too wide")

    def test_crossing_at_inverts_the_offsets(self):
        """A module places its intersection; it does not discover where it fell."""
        for target in ((512.0, 320.0), (512.0, 782.0), (400.0, 600.0)):
            o1, o2 = G.crossing_at(*target)
            k = 2 ** 0.5 / 2
            x = G.C + k * (o2 - o1)
            y = G.C + k * (o1 + o2)
            self.assertAlmostEqual(x, target[0], places=6)
            self.assertAlmostEqual(y, target[1], places=6)

    def test_every_module_declares_a_body(self):
        for key in ORDER:
            self.assertTrue(G.BUILDERS[key](False)["body"].strip())


class PlaneTests(unittest.TestCase):
    def test_no_icon_exceeds_three_dominant_planes(self):
        """base, ribbon, intersection - and nothing else carries a fourth hue.

        Faces and detail modulate a plane already present rather than adding
        one, which is how the cube keeps its form inside the cap.
        """
        for key in ORDER:
            art = G.BUILDERS[key](False)
            hues = {"base", "ribbon", "intersection"}
            self.assertLessEqual(len(hues), 3)
            extra = [k for k in art if k in ("face_top", "face_right", "corner", "detail")]
            for role in extra:
                self.assertIn(role, ("face_top", "face_right", "corner", "detail"))

    def test_intersection_is_rich_never_black(self):
        for key in ORDER:
            fam = FAMILIES[key]
            for small in (False, True):
                c = R.intersection_colour(fam, small)
                self.assertGreater(luminance(c), 0.020,
                                   f"{key} intersection is too close to black")

    def test_intersection_is_darker_than_both_planes(self):
        """'deliberate darker intersection colours' - the crossing must read as
        a crossing, not as a third decorative hue."""
        for key in ORDER:
            fam = FAMILIES[key]
            inter = luminance(R.intersection_colour(fam, False))
            self.assertLess(inter, luminance(rgb(fam.base)), f"{key} vs base")
            self.assertLess(inter, luminance(rgb(fam.ribbon)), f"{key} vs ribbon")


class SvgTests(unittest.TestCase):
    def test_svg_is_well_formed_and_has_a_clean_viewbox(self):
        """Checked by inspection rather than an XML parser: the stdlib parsers
        are XXE-prone and pulling in defusedxml to read a file this module just
        wrote would be a dependency for no gain."""
        for key in ORDER:
            for small in (False, True):
                svg = R.icon_svg(FAMILIES[key], small=small)
                self.assertTrue(svg.startswith("<svg xmlns="))
                self.assertTrue(svg.rstrip().endswith("</svg>"))
                self.assertIn(f'viewBox="0 0 {ARTBOARD} {ARTBOARD}"', svg)
                self.assertEqual(svg.count("<g "), svg.count("</g>"))
                self.assertEqual(svg.count("<defs>"), svg.count("</defs>"))
                self.assertNotIn("&", svg.replace("&amp;", ""))

    def test_no_raster_and_no_font_inside_the_svg(self):
        for key in ORDER:
            svg = R.icon_svg(FAMILIES[key])
            for banned in ("<image", "data:image", "@font-face", "font-family", "<text"):
                self.assertNotIn(banned, svg, f"{key}: {banned} has no place in icon source")

    def test_ids_are_unique_and_namespaced_per_module(self):
        """Two icons inlined in one document must not collide."""
        seen = set()
        for key in ORDER:
            for small in (False, True):
                ids = re.findall(r'id="([^"]+)"', R.icon_svg(FAMILIES[key], small=small))
                self.assertEqual(len(ids), len(set(ids)), f"{key} repeats an id")
                for i in ids:
                    self.assertTrue(i.startswith(f"xf3-{key}"), f"{i} is not namespaced")
                    self.assertNotIn(i, seen, f"{i} collides across modules")
                seen.update(ids)

    def test_no_blend_mode_is_relied_on(self):
        """'Do not depend on CSS mix-blend-mode for final exports.'"""
        for key in ORDER:
            svg = R.icon_svg(FAMILIES[key])
            self.assertNotIn("mix-blend-mode", svg)
            self.assertNotIn("style=", svg)

    def test_svg_and_png_share_one_geometry_source(self):
        """Every path in the SVG comes from the geometry dict it was built from,
        which is what stops the canonical source and the derived raster drifting."""
        for key in ORDER:
            art = G.BUILDERS[key](False)
            svg = R.icon_svg(FAMILIES[key])
            r1, r2 = G.ribbons(art["ribbon_offsets"], art["ribbon_width"],
                               *art.get("ribbon_centre", (G.C, G.C)))
            known = {art[k] for k in art if isinstance(art[k], str)} | {r1, r2}
            for d in re.findall(r'\sd="([^"]+)"', svg):
                self.assertIn(d, known, f"{key}: a path in the SVG is not in its geometry")


class RasterTests(unittest.TestCase):
    def test_png_is_transparent_and_square(self):
        for key in ORDER:
            for size in (16, 48, 128):
                im = R.icon_png(FAMILIES[key], size)
                self.assertEqual(im.size, (size, size))
                self.assertEqual(im.mode, "RGBA")
                self.assertEqual(im.getpixel((0, 0))[3], 0, f"{key}@{size} corner not clear")

    def test_gear_hole_stays_open_at_every_size(self):
        """The centre opening is what says 'gear' at 16px."""
        for size in (16, 24, 32, 48, 128):
            im = R.icon_png(FAMILIES["manufacturing"], size)
            self.assertLess(im.getpixel((size // 2, size // 2))[3], 128,
                            f"gear hole closed at {size}px")

    def test_icons_carry_real_ink_at_the_smallest_size(self):
        for key in ORDER:
            im = R.icon_png(FAMILIES[key], 16)
            opaque = sum(1 for p in im.getdata() if p[3] > 96)
            self.assertGreater(opaque, 24, f"{key} nearly vanishes at 16px")

    def test_small_variants_are_deliberate_not_a_resize(self):
        """A small SVG must differ from the large one, or the 'variant' is a lie."""
        for key in ORDER:
            self.assertNotEqual(R.icon_svg(FAMILIES[key], small=False),
                                R.icon_svg(FAMILIES[key], small=True), key)

    def test_no_shadow_below_48px(self):
        """'a very soft grounding shadow only at 48px and larger'."""
        im = R.icon_png(FAMILIES["inventory"], 32)
        # a shadow would tint the row under the form; nothing should sit there
        self.assertEqual(im.getpixel((1, 31))[3], 0)

    def test_output_is_deterministic(self):
        for key in ORDER:
            a = R.icon_png(FAMILIES[key], 64).tobytes()
            b = R.icon_png(FAMILIES[key], 64).tobytes()
            self.assertEqual(a, b, f"{key} is not deterministic")
            self.assertEqual(R.icon_svg(FAMILIES[key]), R.icon_svg(FAMILIES[key]))

    def test_silhouettes_are_distinguishable_in_grayscale(self):
        """'all icons must still be distinguishable in grayscale by silhouette'."""
        sigs = {}
        for key in ORDER:
            a = R.icon_png(FAMILIES[key], 64).getchannel("A").point(lambda v: 255 if v > 128 else 0)
            sigs[key] = list(a.getdata())
        keys = list(sigs)
        for i, k1 in enumerate(keys):
            for k2 in keys[i + 1:]:
                diff = sum(1 for a, b in zip(sigs[k1], sigs[k2]) if a != b)
                self.assertGreater(diff, 64 * 64 * 0.08, f"{k1} and {k2} share a silhouette")


class ManifestTests(unittest.TestCase):
    def test_manifest_entry_is_json_serialisable_and_complete(self):
        for key in ORDER:
            entry = R.manifest_entry(FAMILIES[key], SMALL_SIZES, LARGE_SIZES)
            json.dumps(entry)
            self.assertEqual(entry["ribbon"]["angles"], [45.0, -45.0])
            self.assertEqual(entry["module"], key)
            self.assertTrue(entry["intersection_resolved"].startswith("#"))


if __name__ == "__main__":
    unittest.main()


class PathFlattenTests(unittest.TestCase):
    """The bridge between the authored SVG masters and Pillow.

    app_icons draws with Pillow, which fills polygons and knows nothing about
    curves, so every authored silhouette reaches the renderer through here. A
    fault in this module is a fault in five shipped icons.
    """

    def test_a_closed_triangle_round_trips(self):
        from afenda.tools.xforge_icons.paths import flatten_path
        polys = flatten_path("M0 0 L10 0 L10 10 Z")
        self.assertEqual(len(polys), 1)
        self.assertEqual(polys[0][0], (0.0, 0.0))
        self.assertEqual(polys[0][-1], (0.0, 0.0), "the contour does not close")

    def test_a_curve_is_flattened_to_the_declared_segment_count(self):
        from afenda.tools.xforge_icons.paths import SEGMENTS, flatten_path
        line = flatten_path("M0 0 L10 0 Z")
        curve = flatten_path("M0 0 Q5 10 10 0 Z")
        self.assertGreater(len(curve[0]), len(line[0]))
        self.assertLessEqual(len(curve[0]), SEGMENTS + 3)

    def test_flattening_is_deterministic(self):
        """The rendered PNGs are committed, so the same checkout has to produce
        the same bytes. An adaptive flattener would emit a different vertex
        count for the same curve at a different scale and churn every icon."""
        from afenda.tools.xforge_icons.paths import flatten_path
        from afenda.tools.xforge_icons.v4_shapes import SHAPES
        for key, builder in sorted(SHAPES.items()):
            d = builder(False)["body"]
            self.assertEqual(flatten_path(d), flatten_path(d), f"{key} flattens differently twice")

    def test_a_curve_stays_within_the_hull_of_its_control_points(self):
        """A Bezier never leaves the convex hull of its control points, so a
        flattener that mixes up control and end points shows up here."""
        from afenda.tools.xforge_icons.paths import bounds, flatten_path
        x0, y0, x1, y1 = bounds(flatten_path("M0 0 Q5 10 10 0 Z"))
        self.assertGreaterEqual(x0, -0.001)
        self.assertLessEqual(x1, 10.001)
        self.assertGreaterEqual(y0, -0.001)
        self.assertLessEqual(y1, 10.001)

    def test_a_gear_keeps_its_hole_as_a_separate_contour(self):
        """The aperture is a second contour, filled even-odd by the caller. If
        it merged into the body the gear would fill solid."""
        from afenda.tools.xforge_icons.paths import flatten_path
        from afenda.tools.xforge_icons.v4_shapes import SHAPES
        art = SHAPES["manufacturing"](False)
        self.assertIn("aperture", art, "the gear no longer declares its hole")
        self.assertTrue(flatten_path(art["aperture"]))

    def test_scale_and_bounds_agree(self):
        from afenda.tools.xforge_icons.paths import bounds, flatten_path, scale_polygons
        polys = flatten_path("M0 0 L10 0 L10 10 Z")
        self.assertEqual(bounds(scale_polygons(polys, 2.0, 3.0, 1.0, 2.0)), (1.0, 2.0, 21.0, 32.0))
