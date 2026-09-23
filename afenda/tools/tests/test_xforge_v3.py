"""Gates for the AFENDA xForge Application Icon System V3.1 reconstruction.

These pin the reconstruction directive's own acceptance conditions, so a later
edit that quietly reintroduces a glyph master, a raster payload, a background
tile or a non-deterministic id fails here rather than in review.
"""
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from afenda.tools.xforge_icons_v3 import validate
from afenda.tools.xforge_icons_v3.geometry import (MASTERS, PLANES, SOFTEN_RADIUS,
                                                   plane_points, soften)
from afenda.tools.xforge_icons_v3.material import TIERS, controlled_overlap, rgb, tier_for
from afenda.tools.xforge_icons_v3.render_png import icon_png
from afenda.tools.xforge_icons_v3.render_svg import icon_svg
from afenda.tools.xforge_icons_v3.spec import ORDER, SIZES, SPECS, VIEWBOX


class StructureTests(unittest.TestCase):
    def test_every_ordered_icon_has_a_spec_and_a_bespoke_master(self):
        """ORDER, SPECS and MASTERS are one table in three parts. The count is
        not pinned - the family grows a tranche at a time - but an entry that
        exists in one and not the others ships a half-defined icon."""
        self.assertEqual(len(set(ORDER)), len(ORDER), "an icon key is repeated")
        self.assertEqual(set(ORDER), set(SPECS), "ORDER and SPECS disagree")
        for key in ORDER:
            self.assertIn(key, SPECS, f"{key} has no spec")
            self.assertIn(key, MASTERS, f"{key} has no bespoke master")
            self.assertTrue(MASTERS[key]["body"].strip(), f"{key} has an empty body")

    def test_no_structural_faults(self):
        """The whole gate set in one assertion; see validate.check_all."""
        self.assertEqual(validate.check_all(), [])

    def test_no_raster_payload_in_any_svg(self):
        for key in ORDER:
            svg = icon_svg(key, 128)
            self.assertNotIn("<image", svg, key)
            self.assertNotIn("data:image", svg, key)
            self.assertNotIn("base64,", svg, key)

    def test_no_generic_icon_library_is_the_master(self):
        """A master may be informed by a glyph; it may not BE one."""
        for key in ORDER:
            svg = icon_svg(key, 128).lower()
            for bad in validate.PROHIBITED_SOURCES:
                self.assertNotIn(bad, svg, f"{key} references {bad}")

    def test_every_svg_has_a_square_viewbox(self):
        for key in ORDER:
            self.assertIn(f'viewBox="0 0 {VIEWBOX} {VIEWBOX}"', icon_svg(key, 128), key)

    def test_no_background_tile(self):
        """V3 icons are free-standing; the corners must be transparent."""
        for key in ORDER:
            im = icon_png(key, 64).convert("RGBA")
            for xy in ((0, 0), (63, 0), (0, 63), (63, 63)):
                self.assertEqual(im.getpixel(xy)[3], 0, f"{key} is painted at {xy}")

    def test_ids_are_unique_per_icon_and_namespaced(self):
        uids = {key: SPECS[key].uid() for key in ORDER}
        self.assertEqual(len(set(uids.values())), len(ORDER), "two icons share an id namespace")
        for key, uid in uids.items():
            svg = icon_svg(key, 128)
            for ref in re.findall(r"url\(#([^)]+)\)", svg):
                self.assertTrue(ref.startswith(uid), f"{key} references foreign id {ref}")


class DeterminismTests(unittest.TestCase):
    def test_svg_generation_is_deterministic(self):
        for key in ORDER:
            self.assertEqual(icon_svg(key, 128), icon_svg(key, 128), key)

    def test_png_generation_is_deterministic(self):
        for key in ORDER:
            self.assertEqual(icon_png(key, 64).tobytes(), icon_png(key, 64).tobytes(), key)

    def test_the_digest_moves_with_the_spec_and_not_otherwise(self):
        spec = SPECS["accounting"]
        self.assertEqual(spec.digest(), SPECS["accounting"].digest())
        for changed in (spec.__class__(**{**spec.__dict__, "base": "#123456"}),
                        spec.__class__(**{**spec.__dict__, "plane": "shard-tl"})):
            self.assertNotEqual(changed.digest(), spec.digest())


class MaterialTests(unittest.TestCase):
    def test_the_responsive_rule_is_the_one_the_manifest_states(self):
        """Flat duotone at 16-24, reduced at 32, crystal at 48-128."""
        self.assertEqual(tier_for(16).name, "flat")
        self.assertEqual(tier_for(24).name, "flat")
        self.assertEqual(tier_for(32).name, "reduced")
        self.assertEqual(tier_for(48).name, "crystal")
        self.assertEqual(tier_for(128).name, "crystal")

    def test_flat_sizes_carry_no_gradient(self):
        for size in (16, 24):
            self.assertNotIn("linearGradient", icon_svg("accounting", size), size)
        for size in (32, 64, 128):
            self.assertIn("linearGradient", icon_svg("accounting", size), size)

    def test_the_crossing_never_collapses_to_black(self):
        """A multiply of two mid-dark brand colours lands near black, and a
        near-black crossing reads as a hole rather than as two planes meeting."""
        for key in ORDER:
            spec = SPECS[key]
            c = controlled_overlap(rgb(spec.base), rgb(spec.accent))
            self.assertGreater(sum(c), 42, f"{key}'s crossing is effectively black: {c}")

    def test_every_plane_named_by_a_spec_exists(self):
        for key in ORDER:
            spec = SPECS[key]
            self.assertIn(spec.plane, PLANES, key)
            self.assertIn(spec.deep_plane, PLANES, key)
            self.assertNotEqual(spec.plane, spec.deep_plane,
                                f"{key}'s two planes are the same, so they cannot cross")
            if spec.accent_facet:
                self.assertIn(spec.accent_facet, MASTERS[key],
                              f"{key} names an accent facet its master does not have")

    def test_planes_run_past_the_frame(self):
        """A plane that stops inside the frame shows its own end and reads as a
        sticker rather than as structure passing through the object."""
        for name in PLANES:
            pts = plane_points(name)
            self.assertTrue(any(x < 0 or x > VIEWBOX or y < 0 or y > VIEWBOX for x, y in pts),
                            f"{name} is fully inside the frame")


class ExportTests(unittest.TestCase):
    def test_every_required_size_renders_at_that_size(self):
        for key in ORDER:
            for size in SIZES:
                im = icon_png(key, size)
                self.assertEqual(im.size, (size, size), f"{key}@{size}")
                self.assertTrue(im.getbbox(), f"{key}@{size} rendered nothing")

    def test_the_icon_fills_its_frame_without_touching_the_edge(self):
        for key in ORDER:
            im = icon_png(key, 128)
            x0, y0, x1, y1 = im.getchannel("A").getbbox()
            span = max(x1 - x0, y1 - y0) / 128
            self.assertGreater(span, 0.70, f"{key} is small in its frame ({span:.2f})")
            self.assertLessEqual(span, 1.0, key)

    def test_accounting_keeps_its_ledger_marks_at_every_size(self):
        """The mandated calibration. Three marks at 32 and up; at 16-24 an
        optically equivalent reduction to two, never nothing."""
        for size in SIZES:
            im = icon_png("accounting", size).convert("RGBA")
            px = im.load()
            light = sum(1 for y in range(size) for x in range(size)
                        if px[x, y][3] > 200 and min(px[x, y][:3]) > 190)
            self.assertGreater(light, 0,
                               f"accounting@{size} has no ledger marks left")

    def test_the_export_writes_svg_png_and_a_manifest(self):
        from afenda.tools.xforge_icons_v3.__main__ import export
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = export(out)
            self.assertEqual(len(manifest["icons"]), len(ORDER))
            self.assertEqual(manifest["canonical"], "svg")
            for key in ORDER:
                self.assertTrue((out / "svg" / f"{key}.svg").is_file(), key)
                for size in SIZES:
                    p = out / "png" / f"{key}@{size}.png"
                    self.assertTrue(p.is_file(), f"{key}@{size}")
                    self.assertGreater(p.stat().st_size, 0, f"{key}@{size} is empty")
            self.assertTrue((out / "manifest.json").is_file())
            self.assertTrue((out / "review" / "contact-sheet.png").is_file())


class ProductionSafetyTests(unittest.TestCase):
    def test_the_lab_does_not_write_to_production_icon_paths(self):
        """The reconstruction is a lab. Nothing in it may name a production
        module icon path, so an accidental export cannot overwrite the tree."""
        root = Path(__file__).resolve().parents[2] / "tools" / "xforge_icons_v3"
        for py in sorted(root.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            self.assertNotIn("static/description", text, f"{py.name} names a production path")
            self.assertNotIn("addons/", text, f"{py.name} names the addons tree")


class MaterialDepthTests(unittest.TestCase):
    """Per-facet gradients: the property that separates the board from a flat fill."""

    def test_every_region_carries_its_own_ramp(self):
        """A single shared ramp cannot model a form: every facet drawn on top of
        it is constant, and a family of constant facets reads as a sticker."""
        for key in ORDER:
            svg = icon_svg(key, 128)
            self.assertGreaterEqual(svg.count("<linearGradient"), 4,
                                    f"{key} does not shade its regions separately")
            for ref in set(re.findall(r'fill="url\(#([^)]+)\)"', svg)):
                self.assertIn(f'id="{ref}"', svg, f"{key} fills with undeclared {ref}")

    def test_geometry_running_past_the_frame_uses_a_global_light(self):
        """A shard's own bounding box is mostly outside the picture, so under
        objectBoundingBox which END of its ramp lands on the icon depends on
        which shard the spec assigned. The light must not be that arbitrary."""
        for key in ORDER:
            svg = icon_svg(key, 128)
            # Only the roles painted on geometry that LEAVES the frame. The
            # body and its facets are bounded by it, so their own box is a
            # meaningful extent - and using it is what gives a ring or a
            # triangle the full value range instead of the middle of one.
            for role in ("deep", "accentplane"):
                m = re.search(rf'<linearGradient id="[^"]*-{role}" gradientUnits="([^"]+)"', svg)
                self.assertIsNotNone(m, f"{key} declares no {role} ramp")
                self.assertEqual(m.group(1), "userSpaceOnUse",
                                 f"{key}'s {role} ramp is sized to its own box")

    def test_the_flat_tier_still_carries_no_ramp_at_all(self):
        for size in (16, 24):
            for key in ORDER:
                self.assertNotIn("linearGradient", icon_svg(key, size), f"{key}@{size}")


class SoftVertexTests(unittest.TestCase):
    def test_softening_rounds_corners_rather_than_moving_them(self):
        square = "M40 40 L216 40 L216 216 L40 216 Z"
        rounded = soften(square, 10.0)
        self.assertGreater(rounded.count("L"), 20, "no arc was generated")
        xs = [float(t.split()[0]) for t in rounded.replace("M", "L").split("L")[1:] if t.strip()]
        self.assertGreater(min(xs), 39.0, "the shape shrank")
        self.assertLess(max(xs), 217.0, "the shape grew")

    def test_softening_is_deterministic(self):
        """Clipper works on an integer lattice and the arc tolerance is fixed,
        so two builds of one commit stay byte-identical."""
        for key, radius in SOFTEN_RADIUS.items():
            d = MASTERS[key]["body"]
            self.assertEqual(soften(d, radius), soften(d, radius), key)

    def test_the_softened_masters_actually_carry_arcs(self):
        """A gear tooth and a cube corner are the sharpest vertices in the family."""
        for key in SOFTEN_RADIUS:
            self.assertGreater(MASTERS[key]["body"].count("L"), 60,
                               f"{key} still has raw polygon vertices")

    def test_a_shape_thinner_than_the_radius_is_left_alone(self):
        """Eroding past its own width would delete it, so the original comes
        back unrounded. Silently dropping the geometry would lose a facet."""
        sliver = "M20 128 L236 128 L236 130 L20 130 Z"
        corners = {(20.0, 128.0), (236.0, 128.0), (236.0, 130.0), (20.0, 130.0)}
        out = soften(sliver, 20.0)
        got = {(float(a), float(b)) for a, b in
               (t.split() for t in out.replace("M", "L").replace("Z", "").split("L") if t.strip())}
        self.assertEqual(got, corners, "a sliver was rounded away or displaced")


class DerivationTests(unittest.TestCase):
    def test_the_raster_is_the_canonical_svg_and_not_a_second_drawing(self):
        """Two implementations of one picture drift. They had already disagreed
        over which ledger marks to draw at 16 and 24."""
        import inspect

        from afenda.tools.xforge_icons_v3 import render_png
        src = inspect.getsource(render_png)
        self.assertIn("icon_svg", src, "the raster does not read the canonical SVG")
        self.assertNotIn("ImageDraw", src, "the raster is drawing its own geometry again")

    def test_the_optical_correction_lives_in_the_canonical_master(self):
        """The 16-24 reduction is a property of the icon, not of one output format."""
        small = MASTERS["accounting"]["detail_small"]
        full = MASTERS["accounting"]["detail"]
        for size in (16, 24):
            self.assertIn(small, icon_svg("accounting", size), f"@{size}")
        for size in (32, 64, 128):
            self.assertIn(full, icon_svg("accounting", size), f"@{size}")


class ApertureTests(unittest.TestCase):
    def test_a_master_with_an_aperture_keeps_it_open(self):
        """The gear's hole is its recognition cue, and it is cut by clip-rule,
        not fill-rule: a clipPath child ignores fill-rule entirely. When the clip
        falls back to nonzero winding the hole silently fills with whichever
        planes cross it."""
        for key in ORDER:
            if "aperture" not in MASTERS[key]:
                continue
            im = icon_png(key, 128).convert("RGBA")
            px = im.load()
            r = 18  # inside the 20px aperture radius at 128, clear of its edge
            painted = sum(1 for dy in range(-r, r + 1) for dx in range(-r, r + 1)
                          if dx * dx + dy * dy <= r * r and px[64 + dx, 64 + dy][3] > 40)
            self.assertEqual(painted, 0, f"{key}'s aperture is {painted}px filled")

    def test_the_clip_declares_the_same_rule_as_the_fill(self):
        for key in ORDER:
            if "aperture" not in MASTERS[key]:
                continue
            svg = icon_svg(key, 128)
            self.assertIn('clip-rule="evenodd"', svg, f"{key}'s clip would fill the aperture")
