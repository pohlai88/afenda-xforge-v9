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
# The standard library, not lxml: the tools suite runs in CI on
# afenda/tools/requirements.txt alone, which has no lxml, and a module that
# fails to import takes all its tests out of the count with it.
import xml.etree.ElementTree as etree
from pathlib import Path

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
# The season layer's classes, the plan's name contract, spelled out for the
# same reason. The hero list above is unchanged: the seasons live in a sibling
# SVG, never inside the bear.
SEASON_CLASSES = (
    "afb-gleam-clip", "afb-gleam", "afb-season", "afb-spring", "afb-summer",
    "afb-autumn", "afb-winter", "afb-p", "afb-fall", "afb-snow", "afb-twinkle",
    "afb-petal", "afb-leaf", "afb-flake", "afb-glint", "afb-tone-1", "afb-tone-2",
    "afb-tone-3",
)
SEASONS = ("spring", "summer", "autumn", "winter")
SCALE_HUES = ("aurora", "dusk", "ember", "forest", "mint", "moss", "rose", "rust")
SCALE_STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
TOKEN = re.compile(r"^\s*(--bear-[a-z0-9-]+):\s*oklch\(([\d.]+)% ([\d.]+) ([\d.]+)\);$", re.M)
# The contract every line of the page's bear CSS keeps (auth_bear.css header).
COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(")
ANIMATABLE = re.compile(r"^(?:translate|rotate|scale|transform|opacity|--afb-s-[a-z0-9-]+|--afb-on-[a-z]+)$")
HOLD_START = {"spring": 0.0, "summer": 25.0, "autumn": 50.0, "winter": 75.0}


def svg_root():
    return etree.fromstring(crystal.build().encode("utf-8"))


def template_root():
    return etree.fromstring((ROOT / crystal.TEMPLATE_TARGET).read_bytes())


def stage():
    divs = [el for el in template_root().iter("div") if el.get("class") == "o_afenda_auth_stage"]
    assert len(divs) == 1, f"expected one stage, found {len(divs)}"
    return divs[0]


def inline_svg():
    """The hero: the stage's first SVG, the bear."""
    return stage()[0]


def season_svg():
    """The season layer: the stage's second SVG, the particles."""
    return stage()[1]


def season_css():
    return (ROOT / crystal.SEASONS_TARGET).read_text(encoding="utf-8")


def css_blocks(css):
    """(selector, body) for every innermost block, comments stripped, at-rule
    heads kept apart: good enough for a flat generated file, and it refuses
    the nesting it cannot read rather than misreading it."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, stack, buf = [], [], ""
    for ch in css:
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            head = stack.pop()
            if buf.strip():
                out.append((head, buf.strip(), tuple(stack)))
            buf = ""
        else:
            buf += ch
    return out


def declarations(body):
    return {k.strip(): v.strip() for k, v in
            (d.split(":", 1) for d in body.split(";") if ":" in d)}


def keyframes(css, name):
    """{stop percentage: {property: value}} for one @keyframes block."""
    frames = {}
    for sel, body, outer in css_blocks(css):
        if outer and outer[-1] == f"@keyframes {name}":
            for stop in sel.split(","):
                stop = stop.strip()
                pct = {"from": 0.0, "to": 100.0}.get(stop)
                pct = float(stop.rstrip("%")) if pct is None else pct
                frames.setdefault(pct, {}).update(declarations(body))
    return frames


def contrast(a, b):
    return crystal.contrast_ratio(crystal.oklch_to_srgb(a), crystal.oklch_to_srgb(b))


def elements(root):
    """Real elements only, never a comment node, whichever parser built the tree."""
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

    def test_the_standalone_carries_no_season(self):
        """The four seasons belong to the page; the standalone file is the bear."""
        svg = crystal.build()
        for name in ("afb-season", "afb-gleam", "o_afenda_auth_stage", "o_afenda_auth_season", "afb-p "):
            self.assertNotIn(name, svg, f"the standalone bear took the season layer's {name}")

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

    def test_the_committed_seasons_are_what_the_generator_produces(self):
        committed = (ROOT / crystal.SEASONS_TARGET).read_text(encoding="utf-8")
        self.assertEqual(crystal.build_seasons_css(), committed,
                         "auth_bear_seasons.css is not what the generator produces; regenerate with "
                         "`python -m afenda.tools.crystal_bear`")

    def test_the_committed_scales_are_what_the_generator_produces(self):
        committed = (ROOT / crystal.SCALES_TARGET).read_text(encoding="utf-8")
        self.assertEqual(crystal.build_scales_css(), committed,
                         "auth_bear_scales.css is not what the generator produces; regenerate with "
                         "`python -m afenda.tools.crystal_bear`")

    def test_the_inline_bear_is_the_standalone_bear_verbatim(self):
        """Undo the indent and the root attributes and it must be build() exactly."""
        text = (ROOT / crystal.TEMPLATE_TARGET).read_text(encoding="utf-8")
        indent = " " * 12
        start = text.index(indent + "<svg ")
        end = text.index("</svg>", start) + len("</svg>")
        body = "\n".join(line[12:] if line.startswith(indent) else line
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
                self.assertFalse(flat & set(SEASON_CLASSES) - {"afb-p"},
                                 f"{label}: a season class reached the bear itself")

    def test_every_season_class_is_present_on_the_season_layer(self):
        found = classes(season_svg())
        flat = set().union(*found)
        for cls in SEASON_CLASSES:
            self.assertIn(cls, flat, f"no season-layer element carries the class {cls}")
        groups = [c for c in found if "afb-season" in c]
        self.assertEqual(sorted(tuple(sorted(c - {"afb-season"})) for c in groups),
                         [(f"afb-{s}",) for s in sorted(SEASONS)],
                         "the season layer is not one group per season")
        clip = [el for el in elements(season_svg()) if el.get("class") == "afb-gleam-clip"]
        self.assertEqual(len(clip), 1)
        self.assertEqual(clip[0].get("clip-path"), "url(#afb-seasonClip)")
        self.assertEqual(sum(1 for c in found if "afb-gleam" in c), 1, "not exactly one gleam")

    def test_every_id_is_prefixed_and_every_reference_resolves(self):
        """The inline copy shares the page's id namespace, so a bare id collides."""
        every = []
        for label, root in (("svg", svg_root()), ("xml", inline_svg()), ("season", season_svg())):
            with self.subTest(output=label):
                ids = [el.get("id") for el in elements(root) if el.get("id") is not None]
                if label != "svg":
                    every += ids
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
        self.assertEqual(len(every), len(set(every)), "the hero and the season layer share an id on the page")

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
        # One stage, the template's only child, holding exactly the two SVGs:
        # the hero, then the season layer drawn over it.
        tpl = root.find("template")
        self.assertEqual([el.tag for el in tpl], ["div"])
        self.assertEqual(tpl[0].get("class"), "o_afenda_auth_stage")
        self.assertEqual([el.tag for el in stage()], [f"{SVG_NS}svg", f"{SVG_NS}svg"])
        self.assertEqual(len(root.findall(f".//{SVG_NS}svg")), 2)
        svg = inline_svg()
        self.assertEqual(svg.get("viewBox"), f"0 0 {crystal.W} {crystal.H}")
        self.assertEqual((svg.get("width"), svg.get("height")), (str(crystal.W), str(crystal.H)))
        self.assertEqual(svg.get("class"), "o_afenda_auth_hero")
        self.assertEqual((svg.get("aria-hidden"), svg.get("focusable")), ("true", "false"))
        season = season_svg()
        self.assertEqual(season.get("viewBox"), f"0 0 {crystal.W} {crystal.H}")
        self.assertEqual(season.get("class"), "o_afenda_auth_season")
        self.assertEqual((season.get("aria-hidden"), season.get("focusable")), ("true", "false"))
        self.assertIsNone(svg_root().get("aria-hidden"),
                          "the standalone file took the inline-only attributes")

    def test_the_scales_define_every_hue_and_step(self):
        tokens, css = scale_tokens()
        expected = ({f"--bear-{h}-{s}" for h in SCALE_HUES for s in SCALE_STEPS}
                    | {"--bear-tenant", "--bear-ink"})
        self.assertEqual(len(expected), 90)
        self.assertEqual(set(tokens), expected)
        declared = re.findall(r"^\s*--bear-", css, re.M)
        self.assertEqual(len(declared), 90, "a token is declared twice or malformed")
        self.assertEqual(tokens["--bear-ink"][2], tokens["--bear-tenant"][2],
                         "the ink panel is no longer the tenant's own hue")
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


class CrystalBearSeasonLayerTests(unittest.TestCase):
    """The particles: counts, placement, determinism, and nothing the page's
    CSS cannot move without touching layout."""

    def particles(self, season):
        group = next(el for el in elements(season_svg())
                     if f"afb-{season}" in (el.get("class") or "").split())
        return [el for el in group if "afb-p" in (el.get("class") or "").split()]

    def test_the_particle_counts_are_the_plan_and_deterministic(self):
        want = {"spring": ("afb-petal", 9), "summer": ("afb-glint", 6),
                "autumn": ("afb-leaf", 8), "winter": ("afb-flake", 16)}
        for season, (shape, n) in want.items():
            with self.subTest(season=season):
                ps = self.particles(season)
                self.assertEqual(len(ps), n)
                for p in ps:
                    self.assertEqual(len(p), 1, "a particle wrapper holds one shape")
                    self.assertIn(shape, p[0].get("class").split())
                    self.assertRegex(p.get("style"), r"^animation-duration:[\d.,s]+;animation-delay:[-\d.,s]+$")
        stars = [p for p in self.particles("winter") if p[0].tag == f"{SVG_NS}path"]
        self.assertEqual(len(stars), 2, "not two six-arm star flakes")
        self.assertEqual(crystal.build_season(), crystal.build_season(), "the season layer is not deterministic")

    def test_the_season_layer_has_no_transform_attribute(self):
        """CSS moves the particles; a transform attribute IS the CSS transform
        property in SVG 2, so one here would be overwritten by the sway."""
        for el in elements(season_svg()):
            self.assertIsNone(el.get("transform"), f"<{el.tag}> carries a transform attribute")

    def test_fallers_start_above_the_canvas_and_glints_sit_inside_the_bear(self):
        num = re.compile(r"-?\d+(?:\.\d+)?")
        for season in ("spring", "autumn", "winter"):
            for p in self.particles(season):
                shape = p[0]
                if shape.tag == f"{SVG_NS}circle":
                    xs, ys = [float(shape.get("cx"))], [float(shape.get("cy")) + float(shape.get("r"))]
                else:
                    vals = [float(v) for v in num.findall(shape.get("d"))]
                    xs, ys = vals[0::2], vals[1::2]
                self.assertLess(max(ys), 0, f"{season}: a faller starts on the canvas")
                self.assertTrue(0 <= sum(xs) / len(xs) <= crystal.W, f"{season}: a faller is off the canvas")
        for p in self.particles("summer"):
            vals = [float(v) for v in num.findall(p[0].get("d"))]
            tips = list(zip(vals[0::2], vals[1::2]))
            for x, y in tips:
                self.assertTrue(crystal.in_bear(x, y), f"a glint point ({x}, {y}) is off the bear")
            self.assertGreaterEqual(min(x for x, _ in tips), 400, "a glint is off the lit flank")

    def test_glints_and_the_gleam_keep_off_the_face(self):
        """The face is the bear's; the light never crosses it. Fallers may."""
        x0, y0, x1, y1 = crystal.FACE_BOX
        num = re.compile(r"-?\d+(?:\.\d+)?")
        for p in self.particles("summer"):
            vals = [float(v) for v in num.findall(p[0].get("d"))]
            for x, y in zip(vals[0::2], vals[1::2]):
                self.assertFalse(x0 <= x <= x1 and y0 <= y <= y1, f"a glint point ({x}, {y}) is on the face")
        frames = keyframes(season_css(), "afb-season-gleam")
        shifts = [float(f["translate"].split()[0].removesuffix("px")) for f in frames.values() if "translate" in f]
        peak = max(float(f["opacity"]) for f in frames.values() if "opacity" in f)
        self.assertLessEqual(peak, 0.35, "the gleam is brighter than the owner's ceiling")
        band = next(el for el in elements(season_svg()) if el.get("class") == "afb-gleam")
        vals = [float(v) for v in num.findall(band.get("d"))]
        pts = list(zip(vals[0::2], vals[1::2]))
        # The band moves left only, so its left edge at its furthest-left shift
        # decides it; the edge is straight, so its ends over the face rows do.
        (ax, ay), (bx, by) = pts[0], pts[3]
        for y in (y0, y1):
            left = ax + (bx - ax) * (y - ay) / (by - ay) + min(shifts)
            self.assertGreater(left, x1, f"the gleam reaches the face at y {y} (x {left:.1f})")

    def test_in_bear_knows_inside_from_outside(self):
        self.assertTrue(crystal.in_bear(135, 321), "the muzzle is not in the bear")
        self.assertFalse(crystal.in_bear(790, 20), "the top-right paper is in the bear")
        self.assertFalse(crystal.in_bear(780, 870), "the bottom-right paper is in the bear")
        self.assertFalse(crystal.in_bear(-1, 400), "a point left of the canvas is in the bear")

    def test_particle_fallbacks_are_not_brand_colours(self):
        """Fallback fills are the season scales' own colours, never AFENDA's."""
        from afenda.tools.rules import load_brand
        ours = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", repr(load_brand()))}
        fills = set()
        for el in elements(season_svg()):
            for name in ("fill", "stroke", "stop-color"):
                value = el.get(name) or ""
                if value.startswith("#"):
                    fills.add(value.upper())
        self.assertGreaterEqual(len(fills), 8, "the particles lost their fallback fills")
        self.assertEqual(fills & ours, set(), "a season fallback is a BRAND colour")


class CrystalBearSeasonStyleTests(unittest.TestCase):
    """auth_bear_seasons.css: the palette, the engine, the contract."""

    def test_the_palette_stands_off_the_ink_and_the_cream(self):
        """3:1, the spec's design target, on the printed tokens.

        Every body role and every particle tone against the ink panel; the
        face-side roles against the cream mark as well, measured against the
        darkest cream the page can draw it in (the art's own cream and the two
        50-steps the page's cream mixes).
        """
        tokens, _css = scale_tokens()
        ink = tokens["--bear-ink"]
        creams = [crystal.oklab_to_oklch(crystal.srgb_to_oklab(
            tuple(int(crystal.RAMP["cream"][i:i + 2], 16) / 255 for i in (1, 3, 5))))]
        creams += [tokens["--bear-forest-50"], tokens["--bear-moss-50"]]
        for season, roles in crystal.SEASONS.items():
            for role, (hue, step) in roles.items():
                lch = tokens[f"--bear-{hue}-{step}"]
                with self.subTest(season=season, role=role):
                    self.assertGreaterEqual(contrast(lch, ink), 3.0, f"{hue}-{step} on the ink")
                    if role in crystal.FACE_SIDE:
                        self.assertGreaterEqual(step, 500, "a face-side role left the window")
                        for cream in creams:
                            self.assertGreaterEqual(contrast(lch, cream), 3.0, f"{hue}-{step} under the cream")
                    else:
                        self.assertLessEqual(step, 400, "a lit-side role left the window")
            for hue, step in crystal.PARTICLE_TONES[season]:
                with self.subTest(season=season, tone=f"{hue}-{step}"):
                    self.assertGreaterEqual(contrast(tokens[f"--bear-{hue}-{step}"], ink), 3.0)

    def test_the_cycle_is_32s_with_the_planned_stops(self):
        css = season_css()
        frames = keyframes(css, "afb-season-cycle")
        holds = sorted(HOLD_START.values()) + [100.0]
        swell = [21.875, 46.875, 71.875, 96.875]
        self.assertEqual(sorted(frames), sorted(holds + [h + 18.75 for h in holds[:-1]] + swell))
        for season, start in HOLD_START.items():
            for pct in (start, start + 18.75) + ((100.0,) if season == "spring" else ()):
                f = frames[pct]
                self.assertEqual(f["--afb-s-swell"], "0.85")
                for other in SEASONS:
                    self.assertEqual(f[f"--afb-on-{other}"], "1" if other == season else "0",
                                     f"{pct}%: --afb-on-{other}")
                for role, (hue, step) in crystal.SEASONS[season].items():
                    self.assertEqual(f[f"--afb-s-{role}"], f"var(--bear-{hue}-{step})")
        for pct in swell:
            self.assertEqual(frames[pct], {"--afb-s-swell": "1"})
        stage = [b for s, b, o in css_blocks(css) if s == ".o_afenda_login .o_afenda_auth_stage" and not o]
        self.assertEqual(len(stage), 1)
        self.assertEqual(declarations(stage[0])["animation"], "afb-season-cycle 32s ease-in-out infinite")

    def test_the_static_blocks_are_the_hold_values_and_the_phase(self):
        """The loop starts on today's season, and reduced motion shows only it."""
        css = season_css()
        blocks = {s: declarations(b) for s, b, o in css_blocks(css) if not o}
        for season, start in HOLD_START.items():
            sel = (".o_afenda_login .o_afenda_auth_stage" if season == "spring" else
                   f'.o_afenda_login .o_afenda_auth_art[data-afb-season="{season}"] .o_afenda_auth_stage')
            with self.subTest(season=season):
                block = blocks[sel]
                hold = keyframes(css, "afb-season-cycle")[start]
                for prop, value in hold.items():
                    self.assertEqual(block[prop], value, f"{season}: static {prop} is not the hold value")
                if season != "spring":
                    self.assertEqual(block["animation-delay"], f"-{int(start * 32 / 100)}s")
        motion = [(s, b) for s, b, o in css_blocks(css) if o == ("@media (prefers-reduced-motion: reduce)",)]
        rules = {s: re.sub(r"\s+", " ", b) for s, b in motion}
        self.assertEqual(rules.get(".o_afenda_login .o_afenda_auth_stage"), "animation: none !important;")
        self.assertEqual(rules.get(".o_afenda_login .o_afenda_auth_stage .o_afenda_auth_season *"),
                         "animation-play-state: paused !important;")

    def test_the_seasons_stylesheet_keeps_the_page_contract(self):
        """Scoped, literal-free, and it animates only what the compositor can."""
        css = season_css()
        self.assertTrue(css.startswith(f"/* {crystal.GENERATED_BY}"))
        self.assertNotIn("url(", css)
        bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        # Values only: a selector such as #afb-gleamGrad is an id, not a colour.
        for _sel, body, _outer in css_blocks(css):
            for prop, value in declarations(body).items():
                self.assertIsNone(COLOUR_LITERAL.search(value), f"a colour literal in {prop}: {value}")
        for at in re.findall(r"@([a-z-]+)", bare):
            self.assertIn(at, ("property", "keyframes", "media"))
        names = set(re.findall(r"@keyframes\s+([\w-]+)", bare))
        self.assertEqual(names, {"afb-season-cycle", "afb-season-fall", "afb-season-sway", "afb-season-drift",
                                 "afb-season-spin", "afb-season-twinkle", "afb-season-gleam"})
        for sel, body, outer in css_blocks(css):
            if outer and outer[-1].startswith("@keyframes"):
                for prop in declarations(body):
                    self.assertRegex(prop, ANIMATABLE, f"{outer[-1]} animates {prop}")
            elif sel.startswith("@property"):
                self.assertRegex(sel, r"^@property --afb-(?:s-[a-z0-9-]+|on-[a-z]+)$")
            else:
                for part in sel.split(","):
                    self.assertTrue(part.strip().startswith(".o_afenda_login .o_afenda_auth_") and
                                    ".o_afenda_auth_stage" in part, f"unscoped selector {part!r}")
                for value in declarations(body).values():
                    for var in re.findall(r"var\((--[\w-]+)\)", value):
                        self.assertRegex(var, r"^--(?:bear-(?:[a-z]+-\d+|ink)|afb-(?:s|on)-[a-z0-9-]+)$")
                if "animation" in body:
                    for name in re.findall(r"afb-[\w-]+", declarations(body).get("animation-name", "")
                                           + declarations(body).get("animation", "")):
                        self.assertIn(name, names)
