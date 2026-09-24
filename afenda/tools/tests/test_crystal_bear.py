"""The hero art is generated, and this is what keeps that true.

Artwork in this repo is never hand-authored: it is produced from committed
inputs by a committed generator, so anyone can reproduce it and nobody has to
trust a binary somebody once dropped in. The crystal bear is the awkward case,
because its GEOMETRY cannot be synthesised - it is a one-time vtracer trace of
the owner's flat layout. That makes colour_trace.svg and path_notbear.txt
inputs rather than outputs, and it makes this the only thing standing between
"generated" and "generated once, then diverged".
"""
import re
import unittest
from pathlib import Path

from lxml import etree

from afenda.tools.crystal_bear import crystal

ROOT = Path(__file__).resolve().parents[3]
SVG_NS = "{http://www.w3.org/2000/svg}"

# Every class the page's CSS is promised, spelled out here rather than imported
# from the generator, so dropping one from build() fails instead of shrinking
# the list the test reads.
LAYER_CLASSES = (
    "afb-haze", "afb-body", "afb-base", "afb-facet", "afb-f1", "afb-f2", "afb-f3",
    "afb-shadow", "afb-s1", "afb-s2", "afb-headlight", "afb-sheen", "afb-rim",
    "afb-face", "afb-bush", "afb-branch",
)
SCALE_HUES = ("aurora", "dusk", "ember", "forest", "mint", "moss")
SCALE_STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
TOKEN = re.compile(r"^\s*(--bear-[a-z0-9-]+):\s*oklch\(([\d.]+)% ([\d.]+) ([\d.]+)\);$", re.M)


def svg_root():
    return etree.fromstring(crystal.build().encode("utf-8"))


def template_root():
    return etree.fromstring((ROOT / crystal.TEMPLATE_TARGET).read_bytes())


def inline_svg():
    svgs = template_root().findall(f".//{SVG_NS}svg")
    assert len(svgs) == 1, f"expected one inline svg, found {len(svgs)}"
    return svgs[0]


def elements(root):
    """Real elements only: lxml yields comments from iter() too."""
    return [el for el in root.iter() if isinstance(el.tag, str)]


def classes(root):
    return [set((el.get("class") or "").split()) for el in elements(root)]


def scale_tokens():
    css = (ROOT / crystal.SCALES_TARGET).read_text(encoding="utf-8")
    return {name: (float(L) / 100, float(C), float(h)) for name, L, C, h in TOKEN.findall(css)}, css


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
        haze = svg[svg.index("url(#afb-hazeFade)") - 200:svg.index("url(#afb-hazeFade)") + 60]
        self.assertIn('fill-rule="evenodd"', haze,
                      "the glow path lost its fill-rule and will tint the whole canvas")
        self.assertNotIn('clip-rule="evenodd" fill="url(#afb-hazeFade)"', svg,
                         "the glow path is using clip-rule, which does nothing on a fill")

    def test_the_art_carries_no_background(self):
        """It sits on the page's own surface; a rect of its own seams."""
        self.assertNotIn(f'<rect width="{crystal.W}" height="{crystal.H}" fill="{crystal.RAMP["paper"]}"/>',
                         crystal.build(), "the hero art paints its own paper and will seam at the panel edge")
        # Layers now carry classes, so the literal above no longer covers a
        # paper rect written with one; read the tree as well.
        paper = crystal.RAMP["paper"].upper()
        for el in elements(svg_root()):
            if el.tag == f"{SVG_NS}rect":
                self.assertNotEqual((el.get("fill") or "").upper(), paper,
                                    "the hero art paints its own paper and will seam at the panel edge")

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


class CrystalBearOutputsTests(unittest.TestCase):
    """The inline template and the colour scales, generated beside the SVG.

    The page's CSS reaches the bear through these, so they carry the same
    guarantee as the art: regenerated from the same inputs, compared byte for
    byte, and checked for the promises Task 2's CSS will lean on.
    """

    def test_the_committed_template_is_what_the_generator_produces(self):
        committed = (ROOT / crystal.TEMPLATE_TARGET).read_text(encoding="utf-8")
        self.assertEqual(crystal.build_template(), committed,
                         "auth_bear.xml is not what the generator produces; regenerate with "
                         "`python -m afenda.tools.crystal_bear`")

    def test_the_committed_scales_are_what_the_generator_produces(self):
        committed = (ROOT / crystal.SCALES_TARGET).read_text(encoding="utf-8")
        self.assertEqual(crystal.build_scales_css(), committed,
                         "auth_bear_scales.css is not what the generator produces; regenerate with "
                         "`python -m afenda.tools.crystal_bear`")

    def test_the_inline_bear_is_the_standalone_bear_verbatim(self):
        """Undo the indent and the root attributes and it must be build() exactly."""
        text = (ROOT / crystal.TEMPLATE_TARGET).read_text(encoding="utf-8")
        start = text.index("        <svg ")
        end = text.index("</svg>", start) + len("</svg>")
        body = "\n".join(line[8:] if line.startswith("        ") else line
                         for line in text[start:end].split("\n"))
        self.assertTrue(body.startswith(crystal.SVG_ROOT_INLINE))
        self.assertEqual(crystal.SVG_ROOT + body[len(crystal.SVG_ROOT_INLINE):], crystal.build(),
                         "the inline bear has drifted from the standalone file")

    def test_every_layer_class_is_present_in_both_outputs(self):
        for label, root in (("svg", svg_root()), ("xml", inline_svg())):
            with self.subTest(output=label):
                found = classes(root)
                flat = set().union(*found)
                for cls in LAYER_CLASSES:
                    self.assertIn(cls, flat, f"{label}: no layer carries the class {cls}")

                def count(*cs):
                    return sum(1 for c in found if set(cs) <= c)

                self.assertEqual(count("afb-facet"), 4)
                self.assertEqual(count("afb-facet", "afb-f1"), 1)
                self.assertEqual(count("afb-facet", "afb-f2"), 2)
                self.assertEqual(count("afb-facet", "afb-f3"), 1)
                self.assertEqual(count("afb-shadow"), 5)
                self.assertEqual(count("afb-shadow", "afb-s1"), 3)
                self.assertEqual(count("afb-shadow", "afb-s2"), 2)
                self.assertEqual(count("afb-branch"), 2)
                for single in ("afb-haze", "afb-body", "afb-base", "afb-headlight",
                               "afb-sheen", "afb-rim", "afb-face", "afb-bush"):
                    self.assertEqual(count(single), 1, f"{label}: {single} is not on exactly one layer")
                face = [el for el in elements(root) if "afb-face" in (el.get("class") or "").split()]
                self.assertEqual(face[0].tag, f"{SVG_NS}g")
                self.assertEqual([el.get("class") for el in face[0]], ["afb-mask", "afb-chin"])

    def test_every_id_is_prefixed_and_every_reference_resolves(self):
        """The inline copy shares the page's id namespace, so a bare id collides."""
        for label, root in (("svg", svg_root()), ("xml", inline_svg())):
            with self.subTest(output=label):
                ids = [el.get("id") for el in elements(root) if el.get("id") is not None]
                self.assertTrue(ids, f"{label}: no ids at all")
                self.assertEqual(len(ids), len(set(ids)), f"{label}: duplicate ids")
                for i in ids:
                    self.assertTrue(i.startswith("afb-"), f"{label}: id {i!r} would collide on the page")
                refs = []
                for el in elements(root):
                    for name, value in el.attrib.items():
                        refs += re.findall(r"url\(#([^)]+)\)", value)
                        if name.endswith("href") and value.startswith("#"):
                            refs.append(value[1:])
                self.assertTrue(refs, f"{label}: no url(#...) references at all")
                for r in refs:
                    self.assertTrue(r.startswith("afb-") and r in ids,
                                    f"{label}: url(#{r}) points at no afb- id")

    def test_the_template_is_plain_markup(self):
        """One template, no QWeb directives, no text: nothing for QWeb to evaluate."""
        root = template_root()
        self.assertEqual(root.tag, "odoo")
        self.assertEqual([t.get("id") for t in root.findall("template")], ["auth_bear"])
        self.assertEqual(len(root.findall(".//template")), 1)
        for el in elements(root):
            for name in el.attrib:
                self.assertFalse(name.startswith("t-"), f"a QWeb directive {name} crept in")
        for el in root.iter():
            if isinstance(el.tag, str):
                self.assertFalse((el.text or "").strip(), f"text inside <{el.tag}>")
            self.assertFalse((el.tail or "").strip(), "text between elements")
        svg = inline_svg()
        self.assertEqual(svg.get("viewBox"), f"0 0 {crystal.W} {crystal.H}")
        self.assertEqual((svg.get("width"), svg.get("height")), (str(crystal.W), str(crystal.H)))
        self.assertEqual(svg.get("class"), "o_afenda_auth_hero")
        self.assertEqual((svg.get("aria-hidden"), svg.get("focusable")), ("true", "false"))
        self.assertIsNone(svg_root().get("aria-hidden"),
                          "the standalone file took the inline-only attributes")

    def test_the_scales_define_every_hue_and_step(self):
        tokens, css = scale_tokens()
        expected = {f"--bear-{h}-{s}" for h in SCALE_HUES for s in SCALE_STEPS} | {"--bear-tenant"}
        self.assertEqual(len(expected), 6 * 11 + 1)
        self.assertEqual(set(tokens), expected)
        declared = re.findall(r"^\s*--bear-", css, re.M)
        self.assertEqual(len(declared), 6 * 11 + 1, "a token is declared twice or malformed")
        self.assertIn(".o_afenda_login {", css)
        self.assertNotIn("url(", css)

    def test_the_tenant_token_is_the_owners_green(self):
        tokens, _css = scale_tokens()
        rgb = crystal.oklch_to_srgb(tokens["--bear-tenant"])
        for got, want in zip(rgb, crystal.BASE):
            self.assertLessEqual(abs(got * 255 - want), 1.0,
                                 f"--bear-tenant is {tuple(round(c * 255, 2) for c in rgb)}, not #1C573E")
        self.assertEqual(tokens["--bear-forest-500"][2], tokens["--bear-tenant"][2],
                         "the forest scale no longer shares the tenant's hue")

    def test_every_scale_colour_is_inside_srgb(self):
        tokens, _css = scale_tokens()
        for name, lch in tokens.items():
            rgb = crystal.oklch_to_srgb(lch)
            self.assertTrue(crystal.in_srgb_gamut(rgb, eps=1e-3),
                            f"{name} {lch} is outside sRGB: {rgb}")

    def test_the_oklab_matrices_match_the_published_reference(self):
        """Ottosson's own worked values, so a mistyped coefficient cannot pass."""
        L, a, b = crystal.srgb_to_oklab((1.0, 1.0, 1.0))
        self.assertAlmostEqual(L, 1.0, places=4)
        self.assertAlmostEqual(a, 0.0, places=4)
        self.assertAlmostEqual(b, 0.0, places=4)
        for got, want in zip(crystal.srgb_to_oklab((1.0, 0.0, 0.0)), (0.62796, 0.22486, 0.12585)):
            self.assertAlmostEqual(got, want, places=4)
        for rgb in ((0.1, 0.34, 0.24), (0.9, 0.2, 0.7), (0.02, 0.5, 0.98)):
            for got, want in zip(crystal.oklab_to_srgb(crystal.srgb_to_oklab(rgb)), rgb):
                self.assertAlmostEqual(got, want, places=6)
