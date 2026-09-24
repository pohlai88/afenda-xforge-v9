"""The hero art is generated, and this is what keeps that true.

Artwork in this repo is never hand-authored: it is produced from committed
inputs by a committed generator, so anyone can reproduce it and nobody has to
trust a binary somebody once dropped in. The crystal bear is the awkward case,
because its GEOMETRY cannot be synthesised - it is a one-time vtracer trace of
the owner's flat layout. That makes colour_trace.svg and path_notbear.txt
inputs rather than outputs, and it makes this the only thing standing between
"generated" and "generated once, then diverged".
"""
import unittest
from pathlib import Path

from afenda.tools.crystal_bear import crystal

ROOT = Path(__file__).resolve().parents[3]


class CrystalBearTests(unittest.TestCase):
    def test_the_committed_svg_is_what_the_generator_produces(self):
        """The golden guard: regenerate and compare, exactly like the corpus.

        A drift here means the committed art no longer matches its inputs, and
        the honest reading is that someone edited the SVG by hand. Run
        `python -m afenda.tools.crystal_bear` and commit the result instead.
        """
        committed = (ROOT / crystal.TARGET).read_text(encoding="utf-8")
        self.assertEqual(
            crystal.build(), committed,
            "the committed hero art is not what the generator produces from the "
            "committed inputs; regenerate with `python -m afenda.tools.crystal_bear`",
        )

    def test_the_traced_inputs_are_present(self):
        """They cannot be regenerated, so their absence is unrecoverable.

        Re-tracing would give a marginally different path, which means a silent
        change to artwork the owner has already signed off.
        """
        for name in ("colour_trace.svg", "path_notbear.txt"):
            path = Path(crystal.HERE) / name
            self.assertTrue(path.is_file(), f"the traced input {name} is missing")
            self.assertGreater(path.stat().st_size, 500, f"{name} is suspiciously small")

    def test_rendering_is_idempotent(self):
        """A second run must write nothing, or every build dirties the tree."""
        self.assertEqual(
            crystal.render_all(ROOT), [],
            "render_all rewrote the hero art when nothing had changed",
        )

    def test_the_glow_uses_fill_rule_not_clip_rule(self):
        """The trap that survived three drafts, pinned so it cannot come back.

        clip-rule is ignored on a filled path - it only binds inside a clipPath
        - so a glow path carrying clip-rule fills with the default nonzero rule
        and tints the WHOLE canvas instead of the bear. It reads as a smudge on
        the paper, no colour count can see it, and masking only moves it.
        """
        svg = crystal.build()
        haze = svg[svg.index("url(#hazeFade)") - 200:svg.index("url(#hazeFade)") + 60]
        self.assertIn('fill-rule="evenodd"', haze,
                      "the glow path lost its fill-rule and will tint the whole canvas")
        self.assertNotIn('clip-rule="evenodd" fill="url(#hazeFade)"', svg,
                         "the glow path is using clip-rule, which does nothing on a fill")

    def test_the_art_carries_no_background(self):
        """It sits on the page's own surface; a rect of its own seams."""
        self.assertNotIn(f'<rect width="{crystal.W}" height="{crystal.H}" fill="{crystal.RAMP["paper"]}"/>',
                         crystal.build(), "the hero art paints its own paper and will seam at the panel edge")

    def test_the_ramp_is_the_customers_green_not_brand(self):
        """Recorded as a deliberate exemption, not left to be discovered.

        This is tenant hero art. Its colours are the customer's and none of
        them is in BRAND, so any palette guard has to exempt it on purpose.
        """
        from afenda.tools.rules import load_brand
        brand = load_brand()
        ours = {brand["primary"].upper(), *(t.upper() for t in brand["tags"])}
        ramp = {v.upper() for k, v in crystal.RAMP.items() if k not in ("cream", "paper")}
        self.assertEqual(
            ramp & ours, set(),
            "a crystal-bear colour is now also a BRAND colour; that is probably "
            "fine but it is no longer a clean tenant/brand separation",
        )
        self.assertEqual(crystal.hexa(crystal.BASE), "#1C573E",
                         "the canonical green moved; the owner ruled #1C573E")
