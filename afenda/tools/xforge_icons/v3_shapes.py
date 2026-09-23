"""Semantic silhouettes for the V3 masters, in the shared 300x365 artboard.

The Accounting silhouette and its fold are transcribed verbatim from the
approved master. The other four are authored to sit in the same box at the same
optical weight: each fills roughly the same share of the live area, and each
keeps its identifying feature clear of where the deep plane crosses.

Every shape returns the same dict so the emitter does not special-case modules:

    body      the silhouette; the clip for all three planes
    detail    marks drawn on top in the palette's detail colour (optional)
    fold      a turned corner, filled with the fold gradient (optional)
    aperture  a hole punched out of the body (optional)
    edge      a hairline that describes the fold or a facet (optional)
"""
from __future__ import annotations

import math

W, H = 300, 365


def _poly(pts):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


def _circle(cx, cy, r, reverse=False):
    n = 72
    step = math.tau / n * (-1 if reverse else 1)
    return _poly([(cx + r * math.cos(i * step), cy + r * math.sin(i * step)) for i in range(n)])


# --------------------------------------------------------------------------
def accounting(micro: bool = False) -> dict:
    """Transcribed from the approved master. Do not restyle."""
    body = "M46 24H183L282 123V304c0 20-16 36-36 36H48c-20 0-36-16-36-36V60c0-20 14-36 34-36Z"
    fold = "M183 24 282 123h-62c-21 0-37-17-37-38Z"
    edge = "M184 24v60c0 21 16 38 37 38h61"
    if micro:
        # Two heavier marks instead of three: at 16px the master's three land on
        # sub-pixel rows and merge into a smear. Two survive as two.
        marks = [("62", "182", "166", "30"), ("62", "150", "232", "30")]
    else:
        marks = [("62", "155", "150", "14"), ("62", "188", "194", "14"),
                 ("62", "149", "238", "14")]
    return {"body": body, "fold": fold, "edge": edge, "marks": marks}


def employees(micro: bool = False) -> dict:
    """Three figures. The deep plane crosses the torso band, never the heads."""
    hr, sr = (52, 38) if not micro else (58, 42)
    cx = 150
    centre = _circle(cx, 118, hr) + " " + \
        f"M{cx - 78} 340 V238 Q{cx - 78} 172 {cx} 172 Q{cx + 78} 172 {cx + 78} 238 V340 Z"
    lx, rx = cx - 88, cx + 88
    left = _circle(lx, 158, sr) + " " + \
        f"M{lx - 56} 340 V252 Q{lx - 56} 202 {lx} 202 Q{lx + 30} 202 {lx + 40} 228 L{lx + 40} 340 Z"
    right = _circle(rx, 158, sr) + " " + \
        f"M{rx + 56} 340 V252 Q{rx + 56} 202 {rx} 202 Q{rx - 30} 202 {rx - 40} 228 L{rx - 40} 340 Z"
    return {"body": " ".join([left, right, centre])}


def inventory(micro: bool = False) -> dict:
    """A package cube. The top face is an explicit facet, not a plane."""
    top, mid, bot = 34, 116, 330
    lx, rx = 22, 278
    body = _poly([(150, top), (rx, mid), (rx, bot - 82), (150, bot), (lx, bot - 82), (lx, mid)])
    facet = _poly([(150, top), (rx, mid), (150, 198), (lx, mid)])
    edge = f"M150 198 V{bot}"
    return {"body": body, "facet": facet, "edge": edge}


def manufacturing(micro: bool = False) -> dict:
    """A gear. The aperture is the recognition cue, so it grows at micro size."""
    teeth, ro, ri = 8, 140, 110
    hole = 62 if not micro else 70
    cx, cy = 150, 182
    pts, step = [], math.tau / teeth
    half = step * 0.5 / 2
    for i in range(teeth):
        a = i * step - math.pi / 2
        pts += [(cx + ro * math.cos(a - half), cy + ro * math.sin(a - half)),
                (cx + ro * math.cos(a + half), cy + ro * math.sin(a + half)),
                (cx + ri * math.cos(a + step / 2 - half), cy + ri * math.sin(a + step / 2 - half)),
                (cx + ri * math.cos(a + step / 2 + half), cy + ri * math.sin(a + step / 2 + half))]
    return {"body": _poly(pts), "aperture": _circle(cx, cy, hole, reverse=True)}


def crm(micro: bool = False) -> dict:
    """A vertical relationship funnel: a wide intake narrowing to a stem.

    Vertical, per the V3 doctrine for this module - not a chevron and not a
    forward arrow, both of which read as playback rather than pipeline.
    """
    top, neck, foot = 30, 206, 336
    w = 128
    body = _poly([(150 - w, top), (150 + w, top), (150 + w, top + 34),
                  (150 + 30, neck), (150 + 30, foot), (150 - 30, foot),
                  (150 - 30, neck), (150 - w, top + 34)])
    edge = f"M{150 - w + 14} {top + 44} L{150 + w - 14} {top + 44}"
    return {"body": body, "edge": edge}


SHAPES = {"accounting": accounting, "employees": employees, "inventory": inventory,
          "manufacturing": manufacturing, "crm": crm}
