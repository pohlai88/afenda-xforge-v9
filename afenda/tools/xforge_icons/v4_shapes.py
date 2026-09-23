"""V4 silhouettes: V3's shapes, with the symbolism sharpened where it was weak.

V3 is frozen, so this module imports its shapes and overrides only the two that
were generic. A silhouette has to name its module on its own, without the label
underneath it - that is the test each override is answering.

  accounting     unchanged. The approved master; a folded record with ruled
                 lines is already unambiguous.
  employees      unchanged. Three figures, one dominant, reads as a team.
  manufacturing  unchanged. A toothed wheel with an open centre is a gear and
                 nothing else.

  inventory      OVERRIDDEN. A bare isometric cube is a gem, a dice, a block -
                 it is only a carton once it has a carton's seam. The top face
                 gets its flap join and the front gets a tape band.
  crm            OVERRIDDEN. A bare funnel is a filter. A pipeline is a funnel
                 with *stages*, so the cone carries two division bands - the
                 thing that makes it a sales pipeline rather than a strainer.
"""
from __future__ import annotations

import math

from .v3_shapes import W, H, _poly, accounting, employees, manufacturing

__all__ = ["SHAPES", "W", "H"]


def inventory(micro: bool = False) -> dict:
    """A shipping carton, built so its own facets carry the form.

    Auditing the reference against the earlier version showed the failure: the
    shared xForge planes were running across all three faces and flattening the
    cube into a hexagon. The reference does the opposite - the object's facets
    are the primary structure and the xForge ribbon lies *over* them - so the
    faces here are explicit, strongly separated in value, and drawn above the
    planes rather than beneath them.

    The vertices are rounded. A mathematically sharp corner reads as a diagram;
    every solid in the reference has a softened one.
    """
    top, mid, low, bot = 34, 116, 248, 330
    lx, rx, cx = 22, 278, 150
    r = 9 if not micro else 6

    def rounded(pts):
        """Close a polygon with a small arc at each vertex."""
        out = []
        n = len(pts)
        for i, (x, y) in enumerate(pts):
            px, py = pts[i - 1]
            nx, ny = pts[(i + 1) % n]
            for (ax, ay), lead in (((px, py), True), ((nx, ny), False)):
                dx, dy = ax - x, ay - y
                d = max(1e-6, (dx * dx + dy * dy) ** 0.5)
                out.append((x + dx / d * r, y + dy / d * r, lead))
        d_ = ""
        for i in range(0, len(out), 2):
            ix, iy, _ = out[i]
            ox, oy, _ = out[i + 1]
            vx, vy = pts[i // 2]
            d_ += (f"{'M' if i == 0 else 'L'}{ix:.1f} {iy:.1f} Q{vx:.1f} {vy:.1f} {ox:.1f} {oy:.1f} ")
        return d_ + "Z"

    body = rounded([(cx, top), (rx, mid), (rx, low), (cx, bot), (lx, low), (lx, mid)])
    face_top = _poly([(cx, top), (rx, mid), (cx, 198), (lx, mid)])
    face_right = _poly([(cx, 198), (rx, mid), (rx, low), (cx, bot)])

    # The lining: the cube's three internal edges, plus its two lit outer edges.
    # This is what the audit found missing - the reference traces every facet
    # boundary with a light line, and it is the single strongest 3D cue.
    lining = (f"M{cx} {top} L{cx} 198 "                      # top-face spine
              f"M{lx} {mid} L{cx} 198 L{rx} {mid} "          # the two upper folds
              f"M{cx} 198 L{cx} {bot}")                      # the front vertical
    lit_edges = f"M{lx} {low} L{lx} {mid} L{cx} {top} L{rx} {mid}"

    if micro:
        return {"body": body, "face_top": face_top, "face_right": face_right,
                "lining": lining, "lit_edges": lit_edges}

    # the xForge ribbon: narrow, and it BENDS at the top-front edge rather than
    # sweeping flat across the form
    ribbon = _poly([(96, 62), (150, 94), (150, 198), (116, 178), (116, 96), (78, 74)])
    band = _poly([(lx, 214), (cx, 258), (cx, 292), (lx, 248)])
    return {"body": body, "face_top": face_top, "face_right": face_right,
            "lining": lining, "lit_edges": lit_edges, "ribbon": ribbon, "band": band}


def crm(micro: bool = False) -> dict:
    """A relationship pipeline: a staged funnel narrowing to a stem.

    Vertical, per the V3 doctrine for this module. The stage bands are what
    separate a pipeline from a kitchen funnel - value enters wide, qualifies
    down through stages, and leaves as a single stream.
    """
    top, neck, foot = 30, 206, 336
    w = 128
    body = _poly([(150 - w, top), (150 + w, top), (150 + w, top + 34),
                  (150 + 30, neck), (150 + 30, foot), (150 - 30, foot),
                  (150 - 30, neck), (150 - w, top + 34)])
    if micro:
        return {"body": body}

    # two stage divisions across the cone. Their widths follow the cone, so they
    # read as stages of one funnel rather than as stripes laid over it.
    def band(y, thickness):
        t = (y - (top + 34)) / (neck - (top + 34))
        half = w - (w - 30) * t
        half2 = w - (w - 30) * ((y + thickness - (top + 34)) / (neck - (top + 34)))
        return _poly([(150 - half, y), (150 + half, y),
                      (150 + half2, y + thickness), (150 - half2, y + thickness)])

    stages = f"{band(96, 11)} {band(150, 11)}"
    return {"body": body, "stages": stages}


SHAPES = {"accounting": accounting, "employees": employees, "inventory": inventory,
          "manufacturing": manufacturing, "crm": crm}
