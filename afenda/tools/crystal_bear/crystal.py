"""The auth page's hero art: the tenant bear, rendered as crystal.

Run after the rebrand script, like every other generated asset:
    python -m afenda.tools.crystal_bear

PROVENANCE, because none of this is derivable from first principles and the
next person to touch it will need all of it.

Geometry
    A one-time vtracer colour-trace of the bear region of the owner's own flat
    layout (their `1.webp`, 800x887 of clean two-ink colour), measured at 0.80%
    pixel mismatch against that source. It is NOT traced from the 164x198 bear
    PNGs: a 2x hero needs roughly 14x their linear detail, and no trace invents
    detail a file does not contain. `colour_trace.svg` and `path_notbear.txt`
    beside this module ARE that trace. They are inputs, not outputs - nothing
    here can regenerate them, and re-tracing would give a marginally different
    path.

Colour
    #1C573E is canonical, by the owner's ruling. Note it is NOT the #006241 in
    the customer's logo: the flat layout had already departed from the logo
    green, and the layout won.

    The ramp is derived from it toward a saturated light green and a near-black
    green. Every colour here is the CUSTOMER'S, not ours. None of it is in
    BRAND and none of it should be - this is tenant hero art carrying their
    identity, so a palette guard has to exempt it deliberately rather than
    happen to miss it. The light end is mixed toward a saturated green rather
    than a mint white for a measured reason: an earlier draft mixed toward a
    near-neutral mint (saturation 0.04) and every light came out grey, 0.203
    against the target's 0.437.

Crop
    The layout crop, by the owner's ruling. The art bleeds off the LEFT and
    BOTTOM by design. The face mask has only 30px of clearance from the left
    edge (bbox 30,210-241,432), so a layout cropping more than about 4% off the
    left cuts the muzzle. Anchor it left and let the right vary.

One rendering trap, recorded because it survived three drafts
    The edge glow is a blurred copy of the silhouette drawn BEHIND the bear,
    and its path carries `fill-rule="evenodd"`. It must not carry `clip-rule`:
    clip-rule is ignored on a filled path - it only binds inside a clipPath -
    so the path fills with the default nonzero rule and tints the ENTIRE canvas
    instead of the bear. That failure is invisible to a colour count and looks
    like a smudge on the paper, and masking it only relocates it.

No raster is generated. The filters here (one Gaussian blur) are rendered
reliably by browsers, the vector is a ninth of the raster's size and scales to
any hero width, and a committed PNG would need a golden test whose result
depends on the installed resvg version rather than on this repo.

Four outputs, all from this module, so none can drift from another
    TARGET           the standalone SVG, exactly as it renders on its own.
    TEMPLATE_TARGET  a QWeb template: the stage, holding the SAME string inline
                     (an <img> is opaque to the page's CSS, and the owner wants
                     CSS to drive the bear's emotion, season and colour) and the
                     season layer beside it. The hero is build() verbatim apart
                     from three attributes on the root, so the two copies
                     cannot disagree.
    SCALES_TARGET    the colour scales that CSS draws from (OKLCH, Tailwind v4
                     step names), and the ink the stage is painted on.
    SEASONS_TARGET   the four-season engine: the season palette as registered
                     custom properties, the 32 s cycle, and the particle motion.

The four seasons (docs/superpowers/specs/2026-09-26-four-season-bear.md). The
bear cycles spring, summer, autumn, winter on a deep ink panel, luminous, its
palette moving with the season, each season with its own weather. The
particles live in a SIBLING svg over the bear, never inside it: anything that
moves inside the bear repaints its 16px blur every frame. So the bear repaints
only while its palette cross-fades, and the weather repaints only itself.

Addressability. Every layer carries an `afb-` class so CSS can reach it, and
every def id carries the same prefix, because the inline copy shares the page's
id namespace: a bare `#bear` or `#haze` would collide with anything else on the
page. The literal fill attributes stay, so the standalone file still renders
exactly as before; a CSS rule on the class overrides a presentation attribute.
"""
from __future__ import annotations

import functools
import math
import pathlib
import random
import re

HERE = pathlib.Path(__file__).resolve().parent
TARGET = "afenda/addons/afenda_brand/static/src/img/auth_hero/crystal_bear.svg"
TEMPLATE_TARGET = "afenda/addons/afenda_brand/views/auth_bear.xml"
SCALES_TARGET = "afenda/addons/afenda_brand/static/src/css/auth_bear_scales.css"
SEASONS_TARGET = "afenda/addons/afenda_brand/static/src/css/auth_bear_seasons.css"
W, H = 800, 887

# The root tag build() emits, and the one the inline copy uses instead. The
# extra attributes belong to the inline copy only: the hero is decoration, so it
# is hidden from assistive tech, and focusable="false" keeps old Edge/IE from
# putting an inline SVG in the tab order.
SVG_ROOT = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
SVG_ROOT_INLINE = SVG_ROOT[:-1] + ' class="o_afenda_auth_hero" aria-hidden="true" focusable="false">'
# The season layer lies over the hero, the stage's full box: 100% rather than
# the art's pixel size, so an absolutely placed layer can never outgrow the
# stage whatever the page's CSS does.
SEASON_ROOT = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="100%"'
               ' class="o_afenda_auth_season" aria-hidden="true" focusable="false">')
GENERATED_BY = "Generated by afenda/tools/crystal_bear (python -m afenda.tools.crystal_bear). Do not edit by hand."

# The flat mark, in the trace's own paint order, by role. The trace has exactly
# these five layers above the body and the page ground; build() refuses to run
# if that stops being true rather than label the wrong path. The mask and the
# chin are grouped as `afb-face`; they keep classes of their own so a rule on
# the group is never applied twice (opacity on both a group and its children
# compounds).
MARK_ROLES = ("afb-bush", "afb-mask", "afb-branch", "afb-branch", "afb-chin")
FACE_ROLES = ("afb-mask", "afb-chin")

BASE = (28, 87, 62)          # #1C573E, the flat bear's own green (owner's ruling)
# The light end is mixed toward a SATURATED green, not toward a near-white
# mint. Measured per luminance band against 2.webp, v5 was under-saturated
# everywhere and worst in the lights: 0.203 against the target's 0.437, less
# than half. The cause was this constant - the old mint sat at saturation 0.04,
# so every mix toward it drained the hue and the lights came out grey. Hue was
# never the problem: v5 ran 150-156 against the target's 150-159.
LIGHT = (111, 199, 155)      # h152 s0.44 - the target's own light-band colour
PALE  = (190, 237, 212)      # h148 s0.20 - its pale band
DEEP  = (8, 36, 26)          # h159 s0.78 - already matches the target's darks

def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

def hexa(c):
    return "#%02X%02X%02X" % c

RAMP = {
    # Measured against the target rather than chosen by eye: 2.webp's bear
    # bottoms out at luminance 29-45, while a flat #1C573E is already 73. The
    # first draft's shadow only reached 66, so the drawing had no dark end at
    # all - every "shadow" was still lighter than the target's mid-tone.
    "shadow": hexa(mix(BASE, DEEP, 0.55)),
    "shadow2": hexa(mix(BASE, DEEP, 0.80)),
    "base":   hexa(BASE),
    "f1":     hexa(mix(BASE, LIGHT, 0.17)),
    "f2":     hexa(mix(BASE, LIGHT, 0.33)),
    "f3":     hexa(mix(BASE, LIGHT, 0.55)),
    "sheen":  hexa(mix(BASE, LIGHT, 0.86)),
    "rim":    hexa(mix(LIGHT, PALE, 0.70)),
    "cream":  "#F7F8F4",
    "paper":  "#F9FAF7",
}

def trace_paths(fn):
    """(fill, transform, d) for every path vtracer emitted, transform kept.

    Keeping the transform is not optional: vtracer emits each layer at its own
    translate, and dropping it collapses the drawing into a wedge at the origin.
    """
    t = (HERE / fn).read_text(encoding="utf-8")
    out = []
    for tag in re.findall(r"<path\b[^>]*>", t):
        d = re.search(r'\bd="([^"]*)"', tag)
        f = re.search(r'\bfill="([^"]*)"', tag)
        tr = re.search(r'\btransform="([^"]*)"', tag)
        if d:
            out.append((f.group(1) if f else None,
                        tr.group(1) if tr else None, d.group(1)))
    return out

def build() -> str:
    notbear = (HERE / "path_notbear.txt").read_text(encoding="utf-8")
    flat = trace_paths("colour_trace.svg")
    # Every mark layer above the body is re-laid over the facets, IN ITS OWN
    # COLOUR. Forcing them all to cream is what dropped the tree's branches on
    # the first pass: the branches are green drawn on top of the cream bush, so
    # a cream-only repaint erased them and left a blank blob. Layer 0 is the
    # body itself and layer 1 is the page ground; everything after is the mark.
    mark = [(f, tr, d) for f, tr, d in flat][2:]
    if len(mark) != len(MARK_ROLES):
        raise ValueError(f"the trace has {len(mark)} mark layers, MARK_ROLES names {len(MARK_ROLES)}")
    for (f, _tr, _d), role in zip(mark, MARK_ROLES):
        if (f.upper() == "#1C573E") != (role == "afb-branch"):
            raise ValueError(f"mark layer filled {f} does not fit the role {role}")

    def g(tr, d, fill, cls):
        t = f' transform="{tr}"' if tr and tr != "translate(0,0)" else ""
        return f'<path class="{cls}"{t} d="{d}" fill="{fill}"/>'

    def paint(f, tr, d, cls):
        return g(tr, d, R['cream'] if f.upper() != '#1C573E' else R['base'], cls)

    # The face (mask and chin) is one group so CSS can change the expression as
    # a unit. The group sits where the mask was, which moves the chin ahead of
    # the branches; the render is unchanged because the chin (y 394-436) and the
    # branches (y >= 559) do not overlap, and a pixel diff proved it at 0.
    R = RAMP
    marks, face_done = [], False
    for (f, tr, d), role in zip(mark, MARK_ROLES):
        if role not in FACE_ROLES:
            marks.append(paint(f, tr, d, role))
        elif not face_done:
            face_done = True
            marks.append('<g class="afb-face">' + ''.join(
                paint(f2, tr2, d2, r2) for (f2, tr2, d2), r2 in zip(mark, MARK_ROLES)
                if r2 in FACE_ROLES) + '</g>')
    return f'''{SVG_ROOT}
<defs>
  <clipPath id="afb-bear" clipPathUnits="userSpaceOnUse">
    <path clip-rule="evenodd" d="M0 0 H{W} V{H} H0 Z {notbear}"/>
  </clipPath>
  <linearGradient id="afb-sheenEdge" gradientUnits="userSpaceOnUse" x1="760" y1="120" x2="470" y2="700">
    <stop offset="0" stop-color="{R['sheen']}" stop-opacity="0.00"/>
    <stop offset="0.30" stop-color="{R['sheen']}" stop-opacity="0.60"/>
    <stop offset="0.70" stop-color="{R['sheen']}" stop-opacity="0.28"/>
    <stop offset="1" stop-color="{R['sheen']}" stop-opacity="0.00"/>
  </linearGradient>
  <!-- The haze fades along a DIAGONAL, so "zero by x=660" is only true on the
       gradient's own axis: at (770,120) it was still at t=0.47 and tinted the
       paper, which is what left an 8-level step at the panel edge. This mask
       fades it by x as well, so the art reaches the edge of its own viewBox at
       exactly the page's colour whatever the diagonal is doing. -->
  <linearGradient id="afb-edgeOut" gradientUnits="userSpaceOnUse" x1="560" y1="0" x2="790" y2="0">
    <stop offset="0" stop-color="#FFFFFF"/>
    <stop offset="1" stop-color="#000000"/>
  </linearGradient>
  <mask id="afb-noSeam" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
    <rect width="{W}" height="{H}" fill="url(#afb-edgeOut)"/>
  </mask>
  <!-- The ear is a narrow protrusion, and a 34px blur around one throws a blob
       that touches no contour - which is why v5 left a smudge on the paper at
       x560-760, y60-300 measuring -5.64 against the target's -0.15. Masking
       the haze by Y as well confines it to the flank, where the target's glow
       actually lives. v5's seam was the same mistake on the other axis: one
       axis constrained, the other assumed. -->
  <linearGradient id="afb-flankFade" gradientUnits="userSpaceOnUse" x1="0" y1="230" x2="0" y2="330">
    <stop offset="0" stop-color="#000000"/>
    <stop offset="1" stop-color="#FFFFFF"/>
  </linearGradient>
  <mask id="afb-flankOnly" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
    <rect width="{W}" height="{H}" fill="url(#afb-flankFade)"/>
  </mask>
  <filter id="afb-haze" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="16"/>
  </filter>
  <linearGradient id="afb-hazeFade" gradientUnits="userSpaceOnUse" x1="300" y1="120" x2="660" y2="600">
    <stop offset="0" stop-color="{R['rim']}" stop-opacity="0"/>
    <stop offset="0.50" stop-color="{R['rim']}" stop-opacity="0.60"/>
    <stop offset="0.80" stop-color="{R['rim']}" stop-opacity="0.35"/>
    <stop offset="1" stop-color="{R['rim']}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="afb-rimGrad" gradientUnits="userSpaceOnUse" x1="430" y1="120" x2="800" y2="620">
    <stop offset="0" stop-color="{R['sheen']}" stop-opacity="0"/>
    <stop offset="0.42" stop-color="{R['sheen']}" stop-opacity="0.35"/>
    <stop offset="0.78" stop-color="{R['rim']}" stop-opacity="0.95"/>
    <stop offset="1" stop-color="{R['rim']}" stop-opacity="0.25"/>
  </linearGradient>
</defs>

<!-- No background rect. Hero art that paints its own paper ends on a visible
     vertical seam wherever the panel stops - the owner's layout is one
     continuous surface, so this composites onto it instead of replacing it. -->

<!-- The haze. In the target the bear does not end on a contour: its lit side
     dissolves into the page. That is a blurred copy of the silhouette sitting
     BEHIND the drawing, gradient-masked so only the lit flank throws it. A
     filter is allowed here - this is the crystal tier, rendered once at hero
     size, not a 16px mark. -->
<g class="afb-haze" mask="url(#afb-noSeam)"><g mask="url(#afb-flankOnly)">
  <g filter="url(#afb-haze)" opacity="0.9">
    <!-- fill-rule, NOT clip-rule. clip-rule is ignored on a filled path - it
         only binds inside a clipPath - so this filled with the default nonzero
         rule and tinted the WHOLE canvas rather than the bear. That is why the
         smudge survived every mask (masking a full-canvas wash just moves the
         part you can see) and why shrinking the blur from 34 to 9 changed the
         strip mean by 0.14. Filling the BEAR and blurring it puts the light
         where a glow actually comes from: just outside the contour, with the
         bear drawn over the top hiding the rest. -->
    <path fill-rule="evenodd" fill="url(#afb-hazeFade)" d="M0 0 H{W} V{H} H0 Z {notbear}"/>
  </g>
</g></g>

<g class="afb-body" clip-path="url(#afb-bear)">
  <rect class="afb-base" width="{W}" height="{H}" fill="{R['base']}"/>

  <!-- Form facets. Each is a whole plane passing through the body, so the
       boundary between two of them is a real edge rather than a blur: that
       edge is what makes the material read as faceted crystal instead of as a
       gradient. Opacity stays low enough that three overlapping planes still
       sit inside the green family. -->
  <!-- Crisper: fewer planes, each carried at a higher opacity so its boundary
       is a definite step rather than a wash. Five overlapping 0.5s average into
       fog; three at 0.8 keep their edges and still stack into depth. -->
  <circle class="afb-facet afb-f1" cx="330" cy="300" r="300" fill="{R['f1']}" opacity="0.92"/>
  <circle class="afb-facet afb-f2" cx="700" cy="330" r="330" fill="{R['f2']}" opacity="0.88"/>
  <circle class="afb-facet afb-f2" cx="620" cy="770" r="400" fill="{R['f2']}" opacity="0.80"/>
  <ellipse class="afb-facet afb-f3" cx="850" cy="560" rx="430" ry="470" fill="{R['f3']}" opacity="0.78"/>

  <!-- Occlusion. The head and ear are the near plane, so what lies behind them
       deepens. Without this the whole silhouette lightens uniformly and the
       depth the facets create is thrown away. -->
  <!-- Measured per region against 2.webp rather than globally, because the
       global mean hid the error: v4 matched overall at -3.6 while the head was
       23.7 too DARK and the lower body 14.8 too LIGHT. Two opposite mistakes
       that cancelled in the average. The head therefore gets much less
       occlusion and the lower body a good deal more. -->
  <circle class="afb-shadow afb-s1" cx="60" cy="90" r="300" fill="{R['shadow']}" opacity="0.42"/>
  <ellipse class="afb-shadow afb-s1" cx="230" cy="0" rx="250" ry="150" fill="{R['shadow']}" opacity="0.22"/>
  <!-- The lower left is SPREAD, not lightened. Measurement contradicted the
       visual note: that area already sits +2.2 lighter than the target on
       average, so the "heavy" reading came from one concentrated blob, not
       from the mean. Widening it and dropping the peak keeps the value and
       removes the mass. -->
  <ellipse class="afb-shadow afb-s2" cx="20" cy="820" rx="470" ry="520" fill="{R['shadow2']}" opacity="0.58"/>
  <ellipse class="afb-shadow afb-s2" cx="380" cy="960" rx="470" ry="300" fill="{R['shadow2']}" opacity="0.62"/>
  <ellipse class="afb-shadow afb-s1" cx="240" cy="660" rx="330" ry="300" fill="{R['shadow']}" opacity="0.22"/>

  <!-- A light facet crossing the head, which the target has and v4 lacked:
       its head is mid-green WITH planes over it, not a shadowed mass. -->
  <circle class="afb-headlight" cx="500" cy="120" r="300" fill="{R['f2']}" opacity="0.34"/>

  <!-- Sheen: a broad wash down the lit flank, then a rim light hugging the
       contour itself. The rim is the silhouette's own edge stroked from the
       inside, gradient-masked so it only lights the right-hand side - the same
       trick the icon lab uses, where a highlight travels along an edge rather
       than sitting on a face. -->
  <path class="afb-sheen" d="M900 -40 C740 220 660 470 600 930 L960 930 L960 -40 Z" fill="url(#afb-sheenEdge)"/>
  <!-- No stroked rim. A stroke along the silhouette reads as an OUTLINE, which
       the brief rules out and which the first draft duly produced around the
       ear. The lit edge here is a plane that happens to reach the contour,
       plus a glow thrown onto the page outside it (below), which is what the
       target actually does. -->
  <ellipse class="afb-rim" cx="880" cy="430" rx="330" ry="520" fill="url(#afb-rimGrad)"/>
</g>

<!-- Flat mark on top: face, nose, tree. -->
{''.join(marks)}
</svg>'''

def build_template() -> str:
    """The QWeb template: the stage, holding the hero and the season layer.

    The hero is build() verbatim with three root attributes, derived from
    build()'s string rather than rendered separately, so the inline bear and
    the standalone file cannot disagree. Each line is indented to sit inside
    the stage; no attribute value spans a line, so indentation only touches
    whitespace between elements and the text of comments, which QWeb drops
    unless a template asks to preserve them. The season layer follows the hero,
    so it paints over it.
    """
    svg = build()
    if svg.count(SVG_ROOT) != 1 or not svg.startswith(SVG_ROOT):
        raise ValueError("build() no longer opens with SVG_ROOT; the inline copy cannot be derived")
    inline = SVG_ROOT_INLINE + svg[len(SVG_ROOT):]

    def indent(text):
        return "\n".join(("            " + line) if line else "" for line in text.split("\n"))

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f"<!-- {GENERATED_BY} -->\n"
        "<odoo>\n"
        '    <template id="auth_bear" name="AFENDA auth hero: crystal bear">\n'
        '        <div class="o_afenda_auth_stage">\n'
        f"{indent(inline)}\n"
        f"{indent(build_season())}\n"
        "        </div>\n"
        "    </template>\n"
        "</odoo>\n"
    )


# ---------------------------------------------------------------------------
# Colour scales: sRGB <-> OKLab <-> OKLCH, the Tailwind v4 method.
#
# Matrices are Bjorn Ottosson's published OKLab ones
# (https://bottosson.github.io/posts/oklab/), sRGB transfer is IEC 61966-2-1.
# ---------------------------------------------------------------------------

def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * math.copysign(abs(c) ** (1 / 2.4), c) - 0.055


def srgb_to_oklab(rgb):
    """``rgb`` as three floats in 0..1 (gamma-encoded sRGB) -> (L, a, b)."""
    r, g, b = (srgb_to_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(x) ** (1 / 3), x) for x in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_srgb(lab):
    """(L, a, b) -> gamma-encoded sRGB floats, NOT clamped (out of gamut shows)."""
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lin = (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )
    return tuple(linear_to_srgb(c) for c in lin)


def oklab_to_oklch(lab):
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def oklch_to_oklab(lch):
    L, C, h = lch
    return L, C * math.cos(math.radians(h)), C * math.sin(math.radians(h))


def oklch_to_srgb(lch):
    return oklab_to_srgb(oklch_to_oklab(lch))


def in_srgb_gamut(rgb, eps: float = 0.0) -> bool:
    return all(-eps <= c <= 1 + eps for c in rgb)


def gamut_map(L: float, C: float, h: float) -> float:
    """The largest chroma <= C at this L and h that is inside sRGB.

    CSS Color 4's own gamut mapping also holds L and h and reduces chroma; this
    is the plain bisection form of it. 40 halvings of 0.4 is far below the
    3-decimal output precision.
    """
    if in_srgb_gamut(oklch_to_srgb((L, C, h))):
        return C
    lo, hi = 0.0, C
    for _ in range(40):
        mid = (lo + hi) / 2
        if in_srgb_gamut(oklch_to_srgb((L, mid, h))):
            lo = mid
        else:
            hi = mid
    return lo


def fmt_oklch(L: float, C: float, h: float) -> str:
    return f"oklch({L * 100:.2f}% {C:.3f} {h:.2f})"


# The tenant, exactly: BASE converted, rounded only by fmt_oklch. It round-trips
# to #1C573E within 1/255 per channel (a test holds that).
TENANT_OKLCH = oklab_to_oklch(srgb_to_oklab(tuple(c / 255 for c in BASE)))

SCALE_STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)

# One lightness ladder for every hue, so a step means the same weight in every
# scale (Tailwind v4's own ladders sit near these: 50 at ~97-98%, 500 at
# ~62-72%, 950 at ~25-28%). The tenant (L ~41%) falls between 700 and 800,
# which is where the art's own mid-tone lives.
SCALE_LIGHTNESS = {
    50: 0.975, 100: 0.950, 200: 0.900, 300: 0.830, 400: 0.740, 500: 0.640,
    600: 0.550, 700: 0.470, 800: 0.390, 900: 0.320, 950: 0.230,
}

# Chroma as a fraction of each hue's peak: full across 500-600, near full at
# 700, tapering hard toward the pale end (a saturated 50 reads as a tint, not a
# paper) and more gently toward the dark end. Gamut mapping then trims whatever
# sRGB cannot hold at that lightness, which bites mostly at the ends. Two hues
# are also trimmed in the middle: sRGB's cusp for teal-cyan and gold sits well
# above L 64%, so aurora and ember reach their largest chroma at 400 and are
# gamut-limited from 500 down. That is sRGB's shape, not the ladder's; Tailwind
# avoids it with per-hue ladders, which this deliberately does not have.
SCALE_CHROMA_SHAPE = {
    50: 0.14, 100: 0.28, 200: 0.50, 300: 0.72, 400: 0.90, 500: 1.00,
    600: 1.00, 700: 0.95, 800: 0.80, 900: 0.64, 950: 0.46,
}

# Brand-token hues: name -> (hue in degrees, peak chroma). Forest IS the tenant:
# its hue and peak chroma are BASE's own, so the forest scale is #1C573E's
# family by construction rather than by eye.
SCALE_FOREST = (round(TENANT_OKLCH[2], 2), round(TENANT_OKLCH[1], 3))
SCALE_AURORA = (195.0, 0.130)   # teal-cyan
SCALE_DUSK = (290.0, 0.170)     # violet
SCALE_EMBER = (75.0, 0.160)     # gold
SCALE_MINT = (165.0, 0.090)     # softer chroma than its neighbours: reads lighter
SCALE_MOSS = (130.0, 0.120)
SCALE_ROSE = (350.0, 0.140)     # blossom pink: spring's light
SCALE_RUST = (45.0, 0.150)      # copper-orange: autumn's leaves
SCALE_HUES = {
    "aurora": SCALE_AURORA,
    "dusk": SCALE_DUSK,
    "ember": SCALE_EMBER,
    "forest": SCALE_FOREST,
    "mint": SCALE_MINT,
    "moss": SCALE_MOSS,
    "rose": SCALE_ROSE,
    "rust": SCALE_RUST,
}

# The panel the bear stands on: the forest hue at L 18%, near-black but still
# the tenant's green. Chroma is gamut-mapped and floored like every scale step.
INK_OKLCH = (0.180, math.floor(round(gamut_map(0.180, 0.034, SCALE_FOREST[0]) * 1000, 6)) / 1000,
             SCALE_FOREST[0])


def scale_colour(name: str, step: int):
    """(L, C, h) for one token, gamut-mapped, C floored to the printed 3 dp.

    Flooring rather than rounding keeps the printed chroma at or below the
    mapped one, so the value a browser reads is never pushed out of gamut by
    the formatting.
    """
    h, peak = SCALE_HUES[name]
    L = SCALE_LIGHTNESS[step]
    C = gamut_map(L, peak * SCALE_CHROMA_SHAPE[step], h)
    return L, math.floor(round(C * 1000, 6)) / 1000, h


def build_scales_css() -> str:
    lines = [
        f"/* {GENERATED_BY}",
        " *",
        " * Colour scales for the auth-page crystal bear, the Tailwind v4 way: OKLCH,",
        " * steps 50-950, one lightness ladder for every hue, chroma peaking at",
        " * 500-700, each colour gamut-mapped into sRGB by reducing chroma.",
        " * --bear-tenant is #1C573E exactly; the forest scale shares its hue.",
        " * --bear-ink is the stage's panel: the forest hue at L 18%.",
        " */",
        ".o_afenda_login {",
        f"    --bear-tenant: {fmt_oklch(*TENANT_OKLCH)};",
        f"    --bear-ink: {fmt_oklch(*INK_OKLCH)};",
    ]
    for name in sorted(SCALE_HUES):
        for step in SCALE_STEPS:
            lines.append(f"    --bear-{name}-{step}: {fmt_oklch(*scale_colour(name, step))};")
    lines.append("}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The four seasons: palette, particles, engine.
#
# docs/superpowers/specs/2026-09-26-four-season-bear.md is binding; the plan
# beside it holds the table and the timing, reproduced here as data.
# ---------------------------------------------------------------------------

SEASON_ORDER = ("spring", "summer", "autumn", "winter")
SEASON_ROLES = ("base", "f1", "f2", "f3", "s1", "s2", "headlight", "sheen", "rim-a", "rim-b", "haze")

# The contrast window. The cream face mask sits on f1, so "lighter facets"
# everywhere would erase the face: the face side stays at step 500-600, dark
# enough for the cream to read on it; the lit side sits at 50-400, light
# enough to glow on the ink. Both sides hold 3:1 (the generator's tests).
FACE_SIDE = ("base", "f1", "s1", "s2", "headlight")

# One bear, four moods (the owner's second-pass guidance): spring rose, soft
# pink and fresh green; summer emerald and warm gold, no cyan; autumn rust,
# amber and copper; winter blue-grey, silver and icy white.
SEASONS = {
    "spring": {
        "base": ("rose", 600), "f1": ("moss", 600), "f2": ("rose", 300), "f3": ("moss", 200),
        "s1": ("rose", 600), "s2": ("moss", 600), "headlight": ("rose", 500),
        "sheen": ("rose", 100), "rim-a": ("rose", 200), "rim-b": ("ember", 50), "haze": ("rose", 200),
    },
    "summer": {
        "base": ("forest", 600), "f1": ("mint", 600), "f2": ("moss", 300), "f3": ("moss", 200),
        "s1": ("forest", 600), "s2": ("moss", 600), "headlight": ("mint", 500),
        "sheen": ("ember", 100), "rim-a": ("ember", 200), "rim-b": ("ember", 50), "haze": ("ember", 100),
    },
    "autumn": {
        "base": ("ember", 600), "f1": ("rust", 600), "f2": ("ember", 300), "f3": ("ember", 200),
        "s1": ("rust", 600), "s2": ("dusk", 600), "headlight": ("ember", 500),
        "sheen": ("rust", 200), "rim-a": ("ember", 100), "rim-b": ("ember", 50), "haze": ("rust", 200),
    },
    "winter": {
        "base": ("aurora", 600), "f1": ("dusk", 600), "f2": ("aurora", 200), "f3": ("dusk", 100),
        "s1": ("dusk", 600), "s2": ("aurora", 600),
        # aurora-500 in the plan's table, moved one step down the face side:
        # against the page's cream (the 50-steps it mixes) it measured 2.99:1.
        "headlight": ("aurora", 600),
        "sheen": ("aurora", 50), "rim-a": ("dusk", 100), "rim-b": ("aurora", 50), "haze": ("aurora", 100),
    },
}

# afb-tone-1, -2, -3 per season, in that order.
PARTICLE_TONES = {
    "spring": (("rose", 200), ("rose", 100), ("rose", 50)),
    "summer": (("ember", 50), ("ember", 100)),
    "autumn": (("rust", 400), ("ember", 400), ("rust", 300)),
    "winter": (("aurora", 50), ("dusk", 50)),
}

# Sizes in user units, times in seconds. One seeded generator walks these in
# this order, so the layer is the same on every run. The counts are restrained
# on purpose: the bear is the subject, the weather about a fifth of the
# attention (the owner's second pass).
PARTICLE_SEED = 20260926
PARTICLES = {
    "spring": {"n": 9, "size": (9, 14), "y": -30, "spacing": 40, "fall": (9, 13), "spin": (4, 7), "sway": (2.6, 3.6)},
    "summer": {"n": 6, "arm": (10, 18), "min_x": 420, "spacing": 60, "twinkle": (2.4, 4.0)},
    "autumn": {"n": 8, "size": (14, 22), "y": -40, "spacing": 40, "fall": (7, 11), "spin": (3, 6), "sway": (2.2, 3.2)},
    "winter": {"n": 16, "stars": 2, "r": (2.5, 6), "star": (7, 10), "spacing": 28, "fall": (10, 16), "drift": (3, 5)},
}

CYCLE_S = 32                       # four seasons of 8 s: a 6 s hold, a 2 s cross-fade
HOLD_PCT = 18.75                   # 6 s of 32
SWELL_HOLD, SWELL_PEAK = "0.85", "1"
FALL_PX = 960                      # from above the canvas to below it: 887 + the tallest start
GLEAM_S = 8
# The gleam sweeps right to left, stopping short of the face: at -360px the
# band's left edge is still at x 260 across the mask's rows (y 210-432).
GLEAM_FROM, GLEAM_TO = 140, -360
GLEAM_PEAK = "0.35"                # the owner's ceiling: a faint reflection, not a flash

# The face mask's box (x0, y0, x1, y1) in the viewBox: glints and the gleam
# never sit over it; fallers may pass through.
FACE_BOX = (30, 210, 241, 432)


def relative_luminance(rgb) -> float:
    """WCAG 2 relative luminance of gamma-encoded sRGB floats (clamped)."""
    r, g, b = (srgb_to_linear(min(1.0, max(0.0, c))) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def scale_hex(hue: str, step: int) -> str:
    """A scale token as #RRGGBB: the fallback paint the layer carries in markup."""
    return hexa(tuple(round(min(1.0, max(0.0, c)) * 255) for c in oklch_to_srgb(scale_colour(hue, step))))


@functools.cache
def bear_polygon():
    """path_notbear.txt flattened to a polygon: 16 points per cubic.

    The file is one subpath of absolute M/C commands closing with Z (the clip
    and the haze read it the same way); anything else is refused rather than
    misread.
    """
    tokens = re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?", (HERE / "path_notbear.txt").read_text(encoding="utf-8"))
    pts, i, cur = [], 0, None
    while i < len(tokens):
        cmd = tokens[i]
        if cmd == "M":
            cur = (float(tokens[i + 1]), float(tokens[i + 2]))
            pts.append(cur)
            i += 3
        elif cmd == "C":
            x1, y1, x2, y2, x, y = (float(v) for v in tokens[i + 1:i + 7])
            for s in range(1, 17):
                u = s / 16
                a, b, c, d = (1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u * u, u ** 3
                pts.append((a * cur[0] + b * x1 + c * x2 + d * x, a * cur[1] + b * y1 + c * y2 + d * y))
            cur = (x, y)
            i += 7
        elif cmd == "Z":
            i += 1
        else:
            raise ValueError(f"path_notbear.txt has a {cmd} command; bear_polygon reads only M, C and Z")
    return tuple(pts)


def in_bear(x: float, y: float) -> bool:
    """Inside the canvas and outside the not-bear region (even-odd, like the clip)."""
    if not (0 <= x <= W and 0 <= y <= H):
        return False
    poly, inside = bear_polygon(), False
    for j in range(len(poly)):
        (x1, y1), (x2, y2) = poly[j], poly[j - 1]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return not inside


def fnum(v: float) -> str:
    """A coordinate or a time to 0.1, without trailing zeros or a negative zero."""
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# Shapes in unit space, drawn pointing up (-y), about their own centre.
# A cherry petal: a narrow base widening to two soft lobes with a shallow notch.
PETAL = (
    ("M", (0.0, -0.50)),
    ("C", (0.24, -0.32), (0.40, 0.06), (0.31, 0.35)),
    ("C", (0.25, 0.50), (0.09, 0.53), (0.0, 0.47)),
    ("C", (-0.09, 0.53), (-0.25, 0.50), (-0.31, 0.35)),
    ("C", (-0.40, 0.06), (-0.24, -0.32), (0.0, -0.50)),
    ("Z",),
)
# An almond leaf with a short stalk, and a midrib cut through it (even-odd):
# the ink shows through the cut, so the vein needs no second colour.
LEAF = (
    ("M", (0.0, -0.50)),
    ("C", (0.28, -0.30), (0.30, 0.16), (0.035, 0.42)),
    ("L", (0.02, 0.56)), ("L", (-0.02, 0.56)), ("L", (-0.035, 0.42)),
    ("C", (-0.26, 0.16), (-0.25, -0.30), (0.0, -0.50)),
    ("Z",),
    ("M", (0.0, -0.34)),
    ("C", (0.02, -0.10), (0.02, 0.20), (0.0, 0.40)),
    ("C", (-0.02, 0.20), (-0.02, -0.10), (0.0, -0.34)),
    ("Z",),
)


def shape_d(shape, cx, cy, size, degrees):
    """A unit shape scaled, rotated and placed, INTO the path data: the season
    layer carries no transform attribute (CSS owns the transform property)."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    out = []
    for cmd, *pts in shape:
        out.append(cmd)
        for x, y in pts:
            out.append(f"{fnum(cx + size * (x * c - y * s))} {fnum(cy + size * (x * s + y * c))}")
    return " ".join(out)


def glint_points(cx, cy, arm):
    """A four-point star: long vertical arms, shorter horizontal ones, sides
    pulled in close to the centre so the points stay needle-crisp."""
    k, h = 0.1 * arm, 0.7 * arm
    return [(cx, cy - arm), (cx + k, cy - k), (cx + h, cy), (cx + k, cy + k), (cx, cy + arm),
            (cx - k, cy + k), (cx - h, cy), (cx - k, cy - k)]


def glint_d(points):
    p = [f"{fnum(x)} {fnum(y)}" for x, y in points]
    return f"M{p[0]} Q{p[1]} {p[2]} Q{p[3]} {p[4]} Q{p[5]} {p[6]} Q{p[7]} {p[0]} Z"


def star_flake_d(cx, cy, radius):
    """Six tapered arms, each with one pair of twigs: a snow crystal that stays
    crisp at 12-18 px. Every bar is wound the same way, so the nonzero fill
    unions them instead of cutting holes where they cross."""
    def bar(x0, y0, x1, y1, w0, w1):
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy)
        nx, ny = -dy / n, dx / n
        pts = [(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1),
               (x1 - nx * w1, y1 - ny * w1), (x0 - nx * w0, y0 - ny * w0)]
        return "M" + " L".join(f"{fnum(x)} {fnum(y)}" for x, y in pts) + " Z"

    bars = []
    for i in range(6):
        a = math.radians(90 + 60 * i)
        ux, uy = math.cos(a), -math.sin(a)
        bars.append(bar(cx, cy, cx + ux * radius, cy + uy * radius, 0.75, 0.4))
        bx, by = cx + ux * radius * 0.55, cy + uy * radius * 0.55
        for side in (-1, 1):
            t = a + side * math.radians(50)
            tx, ty = math.cos(t), -math.sin(t)
            bars.append(bar(bx, by, bx + tx * radius * 0.35, by + ty * radius * 0.35, 0.5, 0.3))
    return " ".join(bars)


def _spaced_xs(rng, n, spacing, lo=20, hi=780):
    xs = []
    for _ in range(20000):
        x = round(rng.uniform(lo, hi), 1)
        if all(abs(x - o) >= spacing for o in xs):
            xs.append(x)
            if len(xs) == n:
                return xs
    raise ValueError(f"cannot place {n} fallers {spacing} apart")


def _dur(rng, bounds):
    return round(rng.uniform(*bounds), 1)


def _style(durations, delays):
    return ("animation-duration:" + ",".join(f"{fnum(d)}s" for d in durations)
            + ";animation-delay:" + ",".join(f"{fnum(d)}s" for d in delays))


def _stratified(rng, i, n, duration):
    """Particle i of n starts (i + jitter)/n of the way through its motion, so
    the layer is evenly populated from the first frame and never in step."""
    return -((i + rng.random()) / n) * duration


def _tone(rng, season):
    k = rng.randrange(len(PARTICLE_TONES[season]))
    return k + 1, scale_hex(*PARTICLE_TONES[season][k])


def season_particles():
    """{season: [markup of each particle]}, from the one seeded generator."""
    rng = random.Random(PARTICLE_SEED)
    out = {}

    def fallers(season, shape, cls):
        spec = PARTICLES[season]
        n, lo, hi = spec["n"], *spec["size"]
        items = []
        for i, x in enumerate(_spaced_xs(rng, n, spec["spacing"])):
            size = rng.uniform(lo, hi)
            d = shape_d(shape, x, spec["y"], size, rng.uniform(0, 360))
            tone, fill = _tone(rng, season)
            depth = (size - lo) / (hi - lo)
            fall, sway, spin = _dur(rng, spec["fall"]), _dur(rng, spec["sway"]), _dur(rng, spec["spin"])
            wrap = _style((fall, sway), (_stratified(rng, i, n, fall), -rng.uniform(0, sway)))
            turn = _style((spin,), (-rng.uniform(0, spin),))
            rule = ' fill-rule="evenodd"' if shape is LEAF else ""
            opacity = fnum(0.78 + 0.22 * depth) if shape is PETAL else "0.92"
            items.append(
                f'<g class="afb-p afb-fall" style="{wrap}">'
                f'<path class="{cls} afb-tone-{tone}" style="{turn}" d="{d}"{rule} fill="{fill}" '
                f'fill-opacity="{opacity}"/></g>')
        return items

    out["spring"] = fallers("spring", PETAL, "afb-petal")

    spec = PARTICLES["summer"]
    glints, centres = [], []
    for _ in range(20000):
        arm = rng.uniform(*spec["arm"])
        cx, cy = round(rng.uniform(spec["min_x"], 760), 1), round(rng.uniform(360, 870), 1)
        pts = [(round(x, 1), round(y, 1)) for x, y in glint_points(cx, cy, arm)]
        if not all(in_bear(x, y) for x, y in pts + [(cx, cy)]):
            continue
        if any(FACE_BOX[0] <= x <= FACE_BOX[2] and FACE_BOX[1] <= y <= FACE_BOX[3] for x, y in pts):
            continue
        if any(math.hypot(cx - ox, cy - oy) < spec["spacing"] for ox, oy in centres):
            continue
        centres.append((cx, cy))
        glints.append(pts)
        if len(glints) == spec["n"]:
            break
    else:
        msg = "cannot place the summer glints on the lit flank"
        raise ValueError(msg)
    out["summer"] = []
    for i, pts in enumerate(glints):
        tone, fill = _tone(rng, "summer")
        dur = _dur(rng, spec["twinkle"])
        out["summer"].append(
            f'<g class="afb-p afb-twinkle" style="{_style((dur,), (_stratified(rng, i, spec["n"], dur),))}">'
            f'<path class="afb-glint afb-tone-{tone}" d="{glint_d(pts)}" fill="{fill}"/></g>')

    out["autumn"] = fallers("autumn", LEAF, "afb-leaf")

    spec = PARTICLES["winter"]
    n, (rlo, rhi) = spec["n"], spec["r"]
    stars = set(rng.sample(range(n), spec["stars"]))
    out["winter"] = []
    for i, x in enumerate(_spaced_xs(rng, n, spec["spacing"])):
        tone, fill = _tone(rng, "winter")
        fall, drift = _dur(rng, spec["fall"]), _dur(rng, spec["drift"])
        wrap = _style((fall, drift), (_stratified(rng, i, n, fall), -rng.uniform(0, drift)))
        if i in stars:
            radius = rng.uniform(*spec["star"])
            y = -(radius + rng.uniform(4, 20))
            shape = (f'<path class="afb-flake afb-tone-{tone}" d="{star_flake_d(x, y, radius)}" '
                     f'fill="{fill}" fill-opacity="0.95"/>')
        else:
            # A soft dot: an opaque core over a faint halo (its own stroke,
            # painted first so the core covers its inner half - a translucent
            # core would show that half as a lighter ring). The larger, nearer
            # flakes are the fainter. No blur filter.
            r = round(rng.uniform(rlo, rhi), 1)
            y = round(-(r + rng.uniform(4, 20)), 1)
            depth = (r - rlo) / (rhi - rlo)
            shape = (f'<circle class="afb-flake afb-tone-{tone}" cx="{fnum(x)}" cy="{fnum(y)}" r="{fnum(r)}" '
                     f'fill="{fill}" stroke="{fill}" stroke-width="{fnum(0.8 * r)}" stroke-opacity="0.3" '
                     f'paint-order="stroke" opacity="{fnum(0.95 - 0.35 * depth)}"/>')
        out["winter"].append(f'<g class="afb-p afb-snow" style="{wrap}">{shape}</g>')
    return out


def gleam_geometry():
    """The band (path data) and its gradient axis: a diagonal sheet of light,
    72 units wide, parallel to nothing in the art so it reads as light, not as
    a facet. It sits right of the flank; CSS sweeps it left across the bear."""
    top, bottom, half = (600.0, -40.0), (820.0, 927.0), 36.0
    dx, dy = bottom[0] - top[0], bottom[1] - top[1]
    n = math.hypot(dx, dy)
    nx, ny = dy / n * half, -dx / n * half
    pts = [(top[0] - nx, top[1] - ny), (top[0] + nx, top[1] + ny),
           (bottom[0] + nx, bottom[1] + ny), (bottom[0] - nx, bottom[1] - ny)]
    d = "M" + " L".join(f"{fnum(x)} {fnum(y)}" for x, y in pts) + " Z"
    mx, my = (top[0] + bottom[0]) / 2, (top[1] + bottom[1]) / 2
    return d, (fnum(mx - nx), fnum(my - ny), fnum(mx + nx), fnum(my + ny))


def build_season() -> str:
    """The season layer: a sibling SVG laid over the hero, the same viewBox.

    The gleam and the summer glints are clipped to the bear (the same not-bear
    even-odd as #afb-bear); the fallers are not - petals, leaves and snow fall
    across the bear and the panel alike. Every shape carries a fallback fill in
    markup; the page's CSS paints it from the scales.
    """
    notbear = (HERE / "path_notbear.txt").read_text(encoding="utf-8")
    parts = season_particles()
    band, (x1, y1, x2, y2) = gleam_geometry()
    light = scale_hex(*SEASONS["spring"]["rim-b"])

    def group(season):
        return (f'<g class="afb-season afb-{season}">\n  '
                + "\n  ".join(parts[season]) + "\n</g>")

    return f'''{SEASON_ROOT}
<defs>
  <clipPath id="afb-seasonClip" clipPathUnits="userSpaceOnUse">
    <path clip-rule="evenodd" d="M0 0 H{W} V{H} H0 Z {notbear}"/>
  </clipPath>
  <linearGradient id="afb-gleamGrad" gradientUnits="userSpaceOnUse" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">
    <stop offset="0" stop-color="{light}" stop-opacity="0"/>
    <stop offset="0.5" stop-color="{light}" stop-opacity="0.7"/>
    <stop offset="1" stop-color="{light}" stop-opacity="0"/>
  </linearGradient>
</defs>
<g class="afb-gleam-clip" clip-path="url(#afb-seasonClip)">
<path class="afb-gleam" d="{band}" fill="url(#afb-gleamGrad)"/>
{group("summer")}
</g>
{group("spring")}
{group("autumn")}
{group("winter")}
</svg>'''


def _pct(v: float) -> str:
    return f"{v:g}%"


def _hold(season, indent):
    pad = " " * indent
    lines = [f"{pad}--afb-s-{role}: var(--bear-{hue}-{step});"
             for role, (hue, step) in SEASONS[season].items()]
    lines += [f"{pad}--afb-on-{s}: {'1' if s == season else '0'};" for s in SEASON_ORDER]
    lines.append(f"{pad}--afb-s-swell: {SWELL_HOLD};")
    return lines


def build_seasons_css() -> str:
    stage = ".o_afenda_login .o_afenda_auth_stage"
    seg = 100 / len(SEASON_ORDER)
    lines = [
        f"/* {GENERATED_BY}",
        " *",
        " * The four-season stage (docs/superpowers/specs/2026-09-26-four-season-bear.md).",
        " * The bear cycles spring, summer, autumn, winter by itself: 8 s a season,",
        " * a 6 s hold and a 2 s cross-fade, a 32 s loop that starts on today's season",
        " * (the art's data-afb-season, from the server's date). The season values are",
        " * registered custom properties, so they interpolate; auth_bear.css derives",
        " * the bear's component tokens from them on the stage.",
        " *",
        " * The one named exception to auth_bear.css's rule that nothing animates at",
        " * rest, confined to the stage: the cycle, the weather (petals, glints,",
        " * leaves, snow) and one gleam. Everything here is scoped under",
        " * .o_afenda_login and the stage, colours come only from the scales, and the",
        " * keyframes move only translate, rotate, scale, transform, opacity and the",
        " * season properties. Reduced motion stops all of it on today's season.",
        " */",
    ]
    for role in SEASON_ROLES:
        lines += [f"@property --afb-s-{role} {{", '    syntax: "<color>";', "    inherits: true;",
                  "    initial-value: transparent;", "}"]
    for season in SEASON_ORDER:
        lines += [f"@property --afb-on-{season} {{", '    syntax: "<number>";', "    inherits: true;",
                  "    initial-value: 0;", "}"]
    lines += ["@property --afb-s-swell {", '    syntax: "<number>";', "    inherits: true;",
              "    initial-value: 1;", "}", ""]

    lines += ["/* The loop, starting on spring; the three blocks after it start it on",
              " * today's season instead, by phase. Each block is also that season's",
              " * still, which is all reduced motion shows. */",
              f"{stage} {{", *_hold("spring", 4),
              f"    animation: afb-season-cycle {CYCLE_S}s ease-in-out infinite;", "}"]
    for k, season in enumerate(SEASON_ORDER[1:], start=1):
        lines += [f'.o_afenda_login .o_afenda_auth_art[data-afb-season="{season}"] .o_afenda_auth_stage {{',
                  *_hold(season, 4), f"    animation-delay: -{k * CYCLE_S // len(SEASON_ORDER)}s;", "}"]
    lines.append("")

    lines.append("@keyframes afb-season-cycle {")
    for k, season in enumerate(SEASON_ORDER):
        start = k * seg
        stops = [_pct(start), _pct(start + HOLD_PCT)] + (["100%"] if season == "spring" else [])
        lines += [f"    {', '.join(stops)} {{", *_hold(season, 8), "    }"]
        lines += [f"    {_pct(start + HOLD_PCT + (seg - HOLD_PCT) / 2)} {{",
                  f"        --afb-s-swell: {SWELL_PEAK};", "    }"]
    lines += ["}", ""]

    lines += [
        "/* Each season's weather shows only while its season does. */",
        *[f"{stage} .afb-{s} {{ opacity: var(--afb-on-{s}); }}" for s in SEASON_ORDER],
        "",
        "/* Particle paint, by tone. The markup's fills are fallbacks only. */",
    ]
    for season in SEASON_ORDER:
        for k, (hue, step) in enumerate(PARTICLE_TONES[season], start=1):
            lines.append(f"{stage} .afb-{season} .afb-tone-{k} {{ fill: var(--bear-{hue}-{step}); }}")
    for k, (hue, step) in enumerate(PARTICLE_TONES["winter"], start=1):
        lines.append(f"{stage} .afb-winter circle.afb-tone-{k} {{ stroke: var(--bear-{hue}-{step}); }}")
    lines += [
        f"{stage} #afb-gleamGrad stop {{ stop-color: var(--afb-s-rim-b); }}",
        "",
        "/* Motion. Durations and delays are per particle, inline in the markup;",
        " * these name the motions. Every mover turns about its own centre. */",
        f"{stage} .afb-p,",
        f"{stage} .afb-p > * {{",
        "    transform-box: fill-box;",
        "    transform-origin: center;",
        "}",
        f"{stage} .afb-fall {{",
        "    animation-name: afb-season-fall, afb-season-sway;",
        "    animation-timing-function: linear, ease-in-out;",
        "    animation-direction: normal, alternate;",
        "    animation-iteration-count: infinite;",
        "}",
        f"{stage} .afb-fall > * {{",
        "    animation-name: afb-season-spin;",
        "    animation-timing-function: linear;",
        "    animation-iteration-count: infinite;",
        "}",
        f"{stage} .afb-fall:nth-child(even) > * {{ animation-direction: reverse; }}",
        f"{stage} .afb-snow {{",
        "    animation-name: afb-season-fall, afb-season-drift;",
        "    animation-timing-function: linear, ease-in-out;",
        "    animation-direction: normal, alternate;",
        "    animation-iteration-count: infinite;",
        "}",
        f"{stage} .afb-twinkle {{",
        "    animation-name: afb-season-twinkle;",
        "    animation-timing-function: ease-in-out;",
        "    animation-iteration-count: infinite;",
        "}",
        f"{stage} .afb-gleam {{ animation: afb-season-gleam {GLEAM_S}s ease-in-out infinite; }}",
        "",
        "@keyframes afb-season-fall {",
        "    from { translate: 0 0; }",
        f"    to {{ translate: 0 {FALL_PX}px; }}",
        "}",
        "/* A pendulum: slow at the ends of each swing, fastest through the middle,",
        " * where the particle turns edge-on (its width narrows) as if tumbling. */",
        "@keyframes afb-season-sway {",
        "    0% { transform: translateX(-12px); scale: 1 1; }",
        "    50% { scale: 0.55 1; }",
        "    100% { transform: translateX(12px); scale: 1 1; }",
        "}",
        "@keyframes afb-season-drift {",
        "    0% { transform: translateX(-7px); }",
        "    100% { transform: translateX(7px); }",
        "}",
        "@keyframes afb-season-spin {",
        "    from { rotate: 0deg; }",
        "    to { rotate: 360deg; }",
        "}",
        "/* Dark for a third of the beat, then a quick flare that turns a little. */",
        "@keyframes afb-season-twinkle {",
        "    0%, 35% { opacity: 0; scale: 0.2; rotate: 0deg; }",
        "    55% { opacity: 1; scale: 1; }",
        "    75%, 100% { opacity: 0; scale: 0.2; rotate: 30deg; }",
        "}",
        "/* One slow, faint sweep per season, mid-hold: 1.6 s to 5.6 s into each 8 s,",
        " * stopping short of the face. */",
        "@keyframes afb-season-gleam {",
        f"    0%, 20% {{ translate: {GLEAM_FROM}px 0; opacity: 0; }}",
        f"    32%, 58% {{ opacity: {GLEAM_PEAK}; }}",
        f"    70%, 100% {{ translate: {GLEAM_TO}px 0; opacity: 0; }}",
        "}",
        "",
        "/* Phones: the art is capped at 28vh there, so the weather is drawn larger. */",
        "@media (max-width: 767.98px) {",
        f"    {stage} .afb-p > * {{ scale: 1.8; }}",
        "}",
        "",
        "/* Reduced motion: no loop and no weather in motion. The stage keeps its",
        " * static block, today's season, fully coloured; the particles hold still. */",
        "@media (prefers-reduced-motion: reduce) {",
        f"    {stage} {{ animation: none !important; }}",
        f"    {stage} .o_afenda_auth_season * {{ animation-play-state: paused !important; }}",
        "}",
    ]
    return "\n".join(lines) + "\n"


def outputs() -> dict[str, str]:
    """Every generated file, relative path -> text."""
    return {
        TARGET: build(),
        TEMPLATE_TARGET: build_template(),
        SCALES_TARGET: build_scales_css(),
        SEASONS_TARGET: build_seasons_css(),
    }


def render_all(root: pathlib.Path) -> list[pathlib.Path]:
    """Write every output under ``root``; returns only what changed on disk."""
    written = []
    for rel, text in outputs().items():
        out = root / rel
        if out.is_file() and out.read_text(encoding="utf-8") == text:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        written.append(out)
    return written


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[3]
    for p in render_all(root):
        print(p.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
