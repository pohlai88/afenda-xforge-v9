"""Bespoke vector geometry for the five Version 3 module icons.

Everything here is authored for this system. No font glyph appears in the
final artwork. Coordinates are in the canonical 1024 artboard; the live area is
``LIVE_AREA`` centred, so a shape that fills it reads at the same optical weight
as its siblings.

Each module contributes two things: the semantic object, and where the xForge
ribbons should cross it. The ribbons themselves are shared - one vocabulary
across all five, which is what keeps the family consistent.
"""
from __future__ import annotations

import math

from .tokens import ARTBOARD, LIVE_AREA, RIBBON_ANGLES, RIBBON_WIDTH


def art_width(small: bool) -> float:
    """Small variants carry a slightly wider ribbon.

    Below 48px a 22% band lands on two or three pixels and dissolves; widening
    it is an optical correction, not a contrast trick.
    """
    return 0.26 if small else RIBBON_WIDTH

C = ARTBOARD / 2          # 512, the artboard centre
M = (ARTBOARD - LIVE_AREA) / 2   # 100, the margin outside the live area


def _d(points, close=True) -> str:
    head = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in points)
    return head + (" Z" if close else "")


# --------------------------------------------------------------- the X ---
def ribbon(angle_deg: float, offset: float = 0.0, width: float = RIBBON_WIDTH,
           cx: float = C, cy: float = C) -> str:
    """One xForge plane: a band at ``angle_deg`` through (cx, cy).

    ``offset`` slides the band along its own normal, which is how a module
    moves the crossing off a feature that must stay clear - the gear's hole,
    a row of faces - without changing the angle and breaking the vocabulary.
    """
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    nx, ny = -dy, dx                       # unit normal
    half = width * LIVE_AREA / 2
    reach = ARTBOARD                       # run well past the board, then clip
    ox, oy = cx + nx * offset, cy + ny * offset
    return _d([
        (ox + dx * reach + nx * half, oy + dy * reach + ny * half),
        (ox - dx * reach + nx * half, oy - dy * reach + ny * half),
        (ox - dx * reach - nx * half, oy - dy * reach - ny * half),
        (ox + dx * reach - nx * half, oy + dy * reach - ny * half),
    ])


def crossing_at(x: float, y: float, cx: float = C, cy: float = C) -> tuple[float, float]:
    """The two offsets that put the ribbons' crossing on (x, y).

    The bands are perpendicular, so the crossing sits at
    ``centre + o1*n1 + o2*n2``; inverting that is what lets a module place the
    intersection deliberately - clear of the accounting rules, inside the gear's
    ring rather than on its rim - instead of discovering where it landed.
    """
    k = 2 ** 0.5 / 2
    dx, dy = x - cx, y - cy
    return ((dy / k - dx / k) / 2, (dy / k + dx / k) / 2)


def ribbons(offsets=(0.0, 0.0), width=RIBBON_WIDTH, cx=C, cy=C) -> tuple[str, str]:
    """The two crossing planes, +45 and -45. Their mutual overlap is plane 3."""
    return (ribbon(RIBBON_ANGLES[0], offsets[0], width, cx, cy),
            ribbon(RIBBON_ANGLES[1], offsets[1], width, cx, cy))


# ------------------------------------------------------------- helpers ---
def _circle(cx, cy, r, reverse=False) -> str:
    """A circle as a polyline, wound clockwise or anticlockwise.

    An anticlockwise contour inside a clockwise one punches a hole under
    even-odd filling, which is how the gear keeps its centre open without a
    second path and a mask.
    """
    n = 96
    step = math.tau / n * (-1 if reverse else 1)
    return _d([(cx + r * math.cos(i * step), cy + r * math.sin(i * step)) for i in range(n)])


def _bar(x0, x1, y, h) -> str:
    """A pill-ended rule, closed so it fills rather than strokes."""
    r = h / 2
    return (f"M{x0 + r:.1f} {y:.1f} H{x1 - r:.1f} Q{x1:.1f} {y:.1f} {x1:.1f} {y + r:.1f} "
            f"Q{x1:.1f} {y + h:.1f} {x1 - r:.1f} {y + h:.1f} H{x0 + r:.1f} "
            f"Q{x0:.1f} {y + h:.1f} {x0:.1f} {y + r:.1f} Q{x0:.1f} {y:.1f} {x0 + r:.1f} {y:.1f} Z")


# ------------------------------------------------------------- modules ---
def accounting(small: bool = False) -> dict:
    """A document: square top-left, folded top-right corner, rounded foot.

    Not a currency symbol - the metaphor is the record, not the money. The
    three rules are the identifying feature, so at small sizes they thicken and
    spread rather than thinning away.
    """
    left, right, top, bot = 232, 792, 134, 890
    fold = 176                      # how far the turned corner reaches
    r = 46                          # foot radius
    body = (f"M{left} {top} H{right - fold} L{right} {top + fold} V{bot - r} "
            f"Q{right} {bot} {right - r} {bot} H{left + r} Q{left} {bot} {left} {bot - r} Z")
    corner = (f"M{right - fold} {top} L{right} {top + fold} H{right - fold + 40} "
              f"Q{right - fold} {top + fold} {right - fold} {top + fold - 40} Z")
    h = 60 if small else 48
    gap = 118 if small else 112
    y0 = 474 if small else 470
    x0 = left + (56 if small else 72)
    rules = " ".join([
        _bar(x0, right - 96, y0, h),
        _bar(x0, right - 60, y0 + gap, h),
        _bar(x0, right - 210, y0 + gap * 2, h),
    ])
    return {"body": body, "detail": rules, "corner": corner,
            "ribbon_offsets": crossing_at(C, 320.0), "ribbon_width": art_width(small)}


def employees(small: bool = False) -> dict:
    """Three figures: a dominant centre, two supporting.

    Each figure is a head and a shoulder block with a deliberate gap between
    neighbours, so the silhouette still counts to three at 16px instead of
    fusing into one lump. The ribbons cross low, through the torso band, which
    the specification requires and which also keeps the faces clear.
    """
    cx = C
    head_c = 126 if small else 118
    head_s = 92 if small else 86
    # the three blocks are kept apart by a visible channel; at 16px a shared
    # edge fuses them into one lump and the icon stops counting to three
    centre = (_circle(cx, 388, head_c) + " " +
              f"M{cx - 168} 906 V700 Q{cx - 168} 548 {cx} 548 "
              f"Q{cx + 168} 548 {cx + 168} 700 V906 Z")
    lx = cx - 274
    left = (_circle(lx, 476, head_s) + " " +
            f"M{lx - 116} 906 V748 Q{lx - 116} 636 {lx} 636 "
            f"Q{lx + 70} 636 {lx + 82} 700 L{lx + 82} 906 Z")
    rx = cx + 274
    right = (_circle(rx, 476, head_s) + " " +
             f"M{rx + 116} 906 V748 Q{rx + 116} 636 {rx} 636 "
             f"Q{rx - 70} 636 {rx - 82} 700 L{rx - 82} 906 Z")
    return {"body": " ".join([left, right, centre]),
            "ribbon_offsets": crossing_at(C, 754.0), "ribbon_width": art_width(small)}


def inventory(small: bool = False) -> dict:
    """A storage cube: top, front-left and right faces with true edges.

    The faces are separate planes so the form reads as a box rather than a gem;
    the right face is what the ribbon plane colours.
    """
    top_y, mid_y, bot_y = 150, 380, 874
    lx, rx = 152, 872
    body = _d([(C, top_y), (rx, mid_y), (rx, bot_y - 116), (C, ARTBOARD - 90),
               (lx, bot_y - 116), (lx, mid_y)])
    top = _d([(C, top_y), (rx, mid_y), (C, 610), (lx, mid_y)])
    right = _d([(C, 610), (rx, mid_y), (rx, bot_y - 116), (C, ARTBOARD - 90)])
    # The crossing sits low on the front-left face. Centred, the X cuts every
    # face at once and the form reads as a gem rather than a box - the faces,
    # not the ribbons, are what say "inventory".
    return {"body": body, "face_top": top, "face_right": right,
            "ribbon_offsets": (-18.0, 18.0),
            "ribbon_width": 0.24 if small else 0.20,
            "ribbon_centre": (C, 700.0)}


def manufacturing(small: bool = False) -> dict:
    """A gear: eight substantial teeth and a large open centre.

    The hole is the recognition cue at 16px, so it is sized generously and the
    ribbons are offset to leave it open.
    """
    teeth = 8
    r_out = 470
    r_in = 366
    r_hole = 196 if small else 182
    span = 0.52                       # tooth occupancy of each step
    pts = []
    step = math.tau / teeth
    half = step * span / 2
    for i in range(teeth):
        a = i * step - math.pi / 2
        pts += [(C + r_out * math.cos(a - half), C + r_out * math.sin(a - half)),
                (C + r_out * math.cos(a + half), C + r_out * math.sin(a + half)),
                (C + r_in * math.cos(a + step / 2 - half), C + r_in * math.sin(a + step / 2 - half)),
                (C + r_in * math.cos(a + step / 2 + half), C + r_in * math.sin(a + step / 2 + half))]
    body = _d(pts) + " " + _circle(C, C, r_hole, reverse=True)
    return {"body": body, "ribbon_offsets": crossing_at(C, 782.0),
            "ribbon_width": art_width(small)}


def crm(small: bool = False) -> dict:
    """Two interlocking chevron ribbons meeting at a relationship point.

    Read as two parties converging and moving forward together. It is not a
    play triangle: the form is two open strokes with a void between them, so
    the silhouette never closes into a solid arrowhead.
    """
    th = 168 if small else 152
    lead = _d([(404, 118), (404 + th, 118), (886, 512), (404 + th, 906),
               (404, 906), (404 + th + 44, 512)], close=True)
    follow = _d([(138, 246), (138 + th, 246), (474, 512), (138 + th, 778),
                 (138, 778), (138 + th + 44, 512)], close=True)
    return {"body": f"{lead} {follow}", "ribbon_offsets": (0.0, 0.0),
            "ribbon_width": art_width(small), "ribbon_centre": (600.0, C)}


BUILDERS = {
    "accounting": accounting,
    "employees": employees,
    "inventory": inventory,
    "manufacturing": manufacturing,
    "crm": crm,
}
