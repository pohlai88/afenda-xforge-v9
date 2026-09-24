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

Only the SVG is generated. The filters here (one Gaussian blur) are rendered
reliably by browsers, the vector is a ninth of the raster's size and scales to
any hero width, and a committed PNG would need a golden test whose result
depends on the installed resvg version rather than on this repo.
"""
from __future__ import annotations

import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
TARGET = "afenda/addons/afenda_brand/static/src/img/auth_hero/crystal_bear.svg"
W, H = 800, 887

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

    def g(tr, d, fill, extra=""):
        t = f' transform="{tr}"' if tr and tr != "translate(0,0)" else ""
        return f'<path{t} d="{d}" fill="{fill}"{extra}/>'

    R = RAMP
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
  <clipPath id="bear" clipPathUnits="userSpaceOnUse">
    <path clip-rule="evenodd" d="M0 0 H{W} V{H} H0 Z {notbear}"/>
  </clipPath>
  <linearGradient id="sheenEdge" gradientUnits="userSpaceOnUse" x1="760" y1="120" x2="470" y2="700">
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
  <linearGradient id="edgeOut" gradientUnits="userSpaceOnUse" x1="560" y1="0" x2="790" y2="0">
    <stop offset="0" stop-color="#FFFFFF"/>
    <stop offset="1" stop-color="#000000"/>
  </linearGradient>
  <mask id="noSeam" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
    <rect width="{W}" height="{H}" fill="url(#edgeOut)"/>
  </mask>
  <!-- The ear is a narrow protrusion, and a 34px blur around one throws a blob
       that touches no contour - which is why v5 left a smudge on the paper at
       x560-760, y60-300 measuring -5.64 against the target's -0.15. Masking
       the haze by Y as well confines it to the flank, where the target's glow
       actually lives. v5's seam was the same mistake on the other axis: one
       axis constrained, the other assumed. -->
  <linearGradient id="flankFade" gradientUnits="userSpaceOnUse" x1="0" y1="230" x2="0" y2="330">
    <stop offset="0" stop-color="#000000"/>
    <stop offset="1" stop-color="#FFFFFF"/>
  </linearGradient>
  <mask id="flankOnly" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
    <rect width="{W}" height="{H}" fill="url(#flankFade)"/>
  </mask>
  <filter id="haze" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="16"/>
  </filter>
  <linearGradient id="hazeFade" gradientUnits="userSpaceOnUse" x1="300" y1="120" x2="660" y2="600">
    <stop offset="0" stop-color="{R['rim']}" stop-opacity="0"/>
    <stop offset="0.50" stop-color="{R['rim']}" stop-opacity="0.60"/>
    <stop offset="0.80" stop-color="{R['rim']}" stop-opacity="0.35"/>
    <stop offset="1" stop-color="{R['rim']}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="rimGrad" gradientUnits="userSpaceOnUse" x1="430" y1="120" x2="800" y2="620">
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
<g mask="url(#noSeam)"><g mask="url(#flankOnly)">
  <g filter="url(#haze)" opacity="0.9">
    <!-- fill-rule, NOT clip-rule. clip-rule is ignored on a filled path - it
         only binds inside a clipPath - so this filled with the default nonzero
         rule and tinted the WHOLE canvas rather than the bear. That is why the
         smudge survived every mask (masking a full-canvas wash just moves the
         part you can see) and why shrinking the blur from 34 to 9 changed the
         strip mean by 0.14. Filling the BEAR and blurring it puts the light
         where a glow actually comes from: just outside the contour, with the
         bear drawn over the top hiding the rest. -->
    <path fill-rule="evenodd" fill="url(#hazeFade)" d="M0 0 H{W} V{H} H0 Z {notbear}"/>
  </g>
</g></g>

<g clip-path="url(#bear)">
  <rect width="{W}" height="{H}" fill="{R['base']}"/>

  <!-- Form facets. Each is a whole plane passing through the body, so the
       boundary between two of them is a real edge rather than a blur: that
       edge is what makes the material read as faceted crystal instead of as a
       gradient. Opacity stays low enough that three overlapping planes still
       sit inside the green family. -->
  <!-- Crisper: fewer planes, each carried at a higher opacity so its boundary
       is a definite step rather than a wash. Five overlapping 0.5s average into
       fog; three at 0.8 keep their edges and still stack into depth. -->
  <circle cx="330" cy="300" r="300" fill="{R['f1']}" opacity="0.92"/>
  <circle cx="700" cy="330" r="330" fill="{R['f2']}" opacity="0.88"/>
  <circle cx="620" cy="770" r="400" fill="{R['f2']}" opacity="0.80"/>
  <ellipse cx="850" cy="560" rx="430" ry="470" fill="{R['f3']}" opacity="0.78"/>

  <!-- Occlusion. The head and ear are the near plane, so what lies behind them
       deepens. Without this the whole silhouette lightens uniformly and the
       depth the facets create is thrown away. -->
  <!-- Measured per region against 2.webp rather than globally, because the
       global mean hid the error: v4 matched overall at -3.6 while the head was
       23.7 too DARK and the lower body 14.8 too LIGHT. Two opposite mistakes
       that cancelled in the average. The head therefore gets much less
       occlusion and the lower body a good deal more. -->
  <circle cx="60" cy="90" r="300" fill="{R['shadow']}" opacity="0.42"/>
  <ellipse cx="230" cy="0" rx="250" ry="150" fill="{R['shadow']}" opacity="0.22"/>
  <!-- The lower left is SPREAD, not lightened. Measurement contradicted the
       visual note: that area already sits +2.2 lighter than the target on
       average, so the "heavy" reading came from one concentrated blob, not
       from the mean. Widening it and dropping the peak keeps the value and
       removes the mass. -->
  <ellipse cx="20" cy="820" rx="470" ry="520" fill="{R['shadow2']}" opacity="0.58"/>
  <ellipse cx="380" cy="960" rx="470" ry="300" fill="{R['shadow2']}" opacity="0.62"/>
  <ellipse cx="240" cy="660" rx="330" ry="300" fill="{R['shadow']}" opacity="0.22"/>

  <!-- A light facet crossing the head, which the target has and v4 lacked:
       its head is mid-green WITH planes over it, not a shadowed mass. -->
  <circle cx="500" cy="120" r="300" fill="{R['f2']}" opacity="0.34"/>

  <!-- Sheen: a broad wash down the lit flank, then a rim light hugging the
       contour itself. The rim is the silhouette's own edge stroked from the
       inside, gradient-masked so it only lights the right-hand side - the same
       trick the icon lab uses, where a highlight travels along an edge rather
       than sitting on a face. -->
  <path d="M900 -40 C740 220 660 470 600 930 L960 930 L960 -40 Z" fill="url(#sheenEdge)"/>
  <!-- No stroked rim. A stroke along the silhouette reads as an OUTLINE, which
       the brief rules out and which the first draft duly produced around the
       ear. The lit edge here is a plane that happens to reach the contour,
       plus a glow thrown onto the page outside it (below), which is what the
       target actually does. -->
  <ellipse cx="880" cy="430" rx="330" ry="520" fill="url(#rimGrad)"/>
</g>

<!-- Flat mark on top: face, nose, tree. -->
{''.join(g(tr, d, R['cream'] if f.upper() != '#1C573E' else R['base']) for f, tr, d in mark)}
</svg>'''

def render_all(root: pathlib.Path) -> list[pathlib.Path]:
    """Write the hero art under ``root``; returns what changed on disk."""
    out = root / TARGET
    out.parent.mkdir(parents=True, exist_ok=True)
    svg = build()
    if out.is_file() and out.read_text(encoding="utf-8") == svg:
        return []
    out.write_text(svg, encoding="utf-8", newline="\n")
    return [out]


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[3]
    for p in render_all(root):
        print(p.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
