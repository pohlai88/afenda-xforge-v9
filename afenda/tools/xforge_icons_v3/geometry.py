"""Bespoke semantic masters and xForge plane geometry, in the 256 master box.

Every master here is drawn, not borrowed. The manifest specifies every module as
``source: BESPOKE_SVG`` with ``master_requirement: Bespoke master required``, and
the design constitution is explicit that a monochrome silhouette must still say
which module it is. A FontAwesome glyph cannot do that: f0d6 is "a banknote",
not "an invoice ledger"; f0f2 is "a suitcase", not "a relationship pipeline".

The one rule that shapes all five: the semantic object comes first, and the
xForge planes cross THROUGH it. They are not badges placed beside a glyph.
"""
from __future__ import annotations

import math

import pyclipper

from ..xforge_icons.paths import flatten_path
from .spec import LIVE, VIEWBOX

__all__ = ["MASTERS", "PLANES", "plane_points", "master", "soften", "fit",
           "SOFTEN_RADIUS"]

B = VIEWBOX  # 256


# ---------------------------------------------------------------------------
# xForge planes.
#
# The manifest names the plane vocabulary per module (shard-tr, shard-br,
# shard-bl, shard-tl, fold-tr, fold-br, band-diag). The coordinates are the ones
# the V3 handoff defines, in a 0..100 box, scaled here into the master box. They
# run past the edges on purpose: a plane that stops inside the frame shows its
# own end, and a plane with a visible end reads as a sticker rather than as
# structure passing through.
_PLANES_100 = {
    "shard-tr": ((48, -6), (106, -6), (106, 36), (66, 66), (52, 52)),
    "shard-br": ((52, 48), (68, 34), (106, 68), (106, 106), (62, 106)),
    "shard-bl": ((48, 52), (34, 66), (-6, 106), (38, 106), (66, 68)),
    "shard-tl": ((-6, -6), (38, -6), (66, 32), (48, 52), (-6, 36)),
    "fold-tr": ((58, -4), (104, -4), (104, 44), (74, 62), (58, 48)),
    "fold-br": ((58, 52), (76, 40), (104, 60), (104, 104), (60, 104)),
    "band-diag": ((-10, 78), (78, -10), (106, 18), (18, 106)),
}
PLANES = tuple(sorted(_PLANES_100))


def plane_points(name: str) -> tuple[tuple[float, float], ...]:
    """A plane's corners in the master box."""
    u = B / 100.0
    return tuple((round(x * u, 2), round(y * u, 2)) for x, y in _PLANES_100[name])


def _pts(points) -> str:
    return " ".join(f"{x:g},{y:g}" for x, y in points)


def _circle(cx: float, cy: float, r: float, segments: int = 48) -> str:
    """A circle as an explicit path, so every master is one path grammar."""
    out = [f"M{cx + r:g} {cy:g}"]
    for i in range(1, segments + 1):
        a = 2 * math.pi * i / segments
        out.append(f"L{cx + r * math.cos(a):.2f} {cy + r * math.sin(a):.2f}")
    return " ".join(out) + " Z"


# ---------------------------------------------------------------------------
# Soft vertices.
#
# The board rounds its corners consistently; a raw polygon vertex is the single
# cheapest tell that a mark was generated rather than drawn. Rounding is done on
# the geometry, not with an SVG filter, because the material is built from
# geometry and the validator refuses filters outright.
#
# The operation is morphological: erode then dilate rounds every convex corner,
# dilate then erode rounds every concave one, and a gear needs both because its
# tooth tips are convex and its roots are concave. Clipper works on an integer
# lattice, so coordinates are scaled up and the arc tolerance is fixed - without
# a fixed tolerance the number of segments in an arc would vary with the
# geometry and two builds of one commit would not be byte-identical.
CLIP_SCALE = 1000
ARC_TOLERANCE = 0.02
SOFTEN_RADIUS = {"manufacturing": 5.0, "inventory": 7.0}


def _offset(path, delta: float):
    co = pyclipper.PyclipperOffset()
    co.ArcTolerance = ARC_TOLERANCE * CLIP_SCALE
    co.AddPath(path, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    return co.Execute(delta * CLIP_SCALE)


def _largest(paths):
    """The contour carrying the most area; offsetting can shed slivers."""
    return max(paths, key=lambda p: abs(pyclipper.Area(p))) if paths else None


def _round_polygon(points, radius: float):
    path = [(round(x * CLIP_SCALE), round(y * CLIP_SCALE)) for x, y in points]
    for delta in (-radius, radius, radius, -radius):
        path = _largest(_offset(path, delta))
        if not path:
            return points  # the shape is thinner than the radius; leave it alone
    return [(x / CLIP_SCALE, y / CLIP_SCALE) for x, y in path]


def fit(d: str, span: float = LIVE * VIEWBOX) -> str:
    """Scale ``d`` about its own centre until its longer side is ``span``, and
    centre it in the box.

    A diagonal form - a wrench, a tool laid across the frame - measures smaller
    than a rectangle drawn to the same coordinates, because its bounding box is
    the diagonal rather than the shape. Authoring it to look right by eye
    therefore leaves it optically small, and the frame-fill gate catches it:
    the wrench came out at 0.67 of the box against a 0.70 floor.

    Flattening and re-emitting, the same way ``soften`` does, so a scaled master
    and a softened one share one path grammar.
    """
    polys = [p for p in flatten_path(d) if len(p) >= 3]
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    if not xs:
        return d
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    k = span / max(w, h)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    mid = VIEWBOX / 2
    out = []
    for poly in polys:
        pts = [((x - cx) * k + mid, (y - cy) * k + mid) for x, y in poly]
        out.append("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z")
    return " ".join(out)


def soften(d: str, radius: float) -> str:
    """``d`` with every vertex rounded by ``radius`` master-box units."""
    out = []
    for poly in flatten_path(d):
        if len(poly) < 3:
            continue
        rounded = _round_polygon(poly, radius)
        out.append("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in rounded) + " Z")
    return " ".join(out)


# ---------------------------------------------------------------------------
# Accounting - the calibration master.
#
# Upright ledger with a folded upper-right corner and rounded lower corners.
# The fold is a real corner turn, not a printed triangle: the body stops short
# of the corner and the fold is the piece that turned over, which is why the
# silhouette has a cut corner rather than a square one.
# Body 160 x 204 = aspect 0.784 against the board's measured 0.791. Corner
# radius 12 on a 160 width = 7.5%, against the board's 7.8%; an earlier pass used
# 24 (15.8%) and read as a rounded tile rather than a sheet of paper.
_ACC_BODY = ("M60 26 H147 L208 87 V218 Q208 230 196 230 H60 Q48 230 48 218 "
             "V38 Q48 26 60 26 Z")
# The fold turns at 45 degrees and spans 61 of the 160 width = 38%, matching.
_ACC_FOLD = "M147 26 V75 Q147 87 159 87 H208 Z"
# Pitch 27 on a 204 body = 13.2% (board 13.4%); bar height 10 = 4.9% (board 5.0%);
# left edge inset 23 of 160 = 14.4% (board 14.2%).
_ACC_MARKS = (
    "M76 121 H170 Q175 121 175 126 Q175 131 170 131 H76 Q71 131 71 126 Q71 121 76 121 Z "
    "M76 148 H170 Q175 148 175 153 Q175 158 170 158 H76 Q71 158 71 153 Q71 148 76 148 Z "
    "M76 175 H136 Q141 175 141 180 Q141 185 136 185 H76 Q71 185 71 180 Q71 175 76 175 Z")

# Optical correction, 16-24px only. Three 14-unit marks land on under two
# pixels at 16px and grey into a smudge, taking the ledger cue with them. Two
# marks at 22 units survive, and two ruled lines still read as ruled paper. The
# canonical master keeps three; only the smallest raster substitutes this.
_ACC_MARKS_SMALL = (
    "M78 132 H168 Q179 132 179 143 Q179 154 168 154 H78 Q67 154 67 143 Q67 132 78 132 Z "
    "M78 176 H140 Q151 176 151 187 Q151 198 140 198 H78 Q67 198 67 187 Q67 176 78 176 Z")

# ---------------------------------------------------------------------------
# Employees - three figures reading as ONE cluster.
#
# The board's people are a single silhouette: heads sitting ON the shoulders,
# bodies overlapping into one mass, the centre figure plainly nearest. An
# earlier pass left a 20-unit gap under the centre head and 22 under the sides,
# with only 4 units of overlap between neighbouring bodies - which is why it
# read as three separate marks standing in a row rather than as people together.
#
# Every number below is a measured relationship, not a guess: a head's bottom
# sits 2 units INSIDE its own shoulder line, and each side body overlaps the
# centre by 22 units.
EMP_BASE = 230.0


def _dome(cx: float, half: float, top: float, base: float = EMP_BASE) -> str:
    """Head-and-shoulders: a rounded crown over straight sides to the baseline."""
    shoulder = top + half
    return (f"M{cx - half:g} {base:g} V{shoulder:g} "
            f"Q{cx - half:g} {top:g} {cx:g} {top:g} "
            f"Q{cx + half:g} {top:g} {cx + half:g} {shoulder:g} V{base:g} Z")


# centre: head r34 at y80 -> bottom 114; body top 112, so the head is seated.
# Shoulders, not arches. The crown radius has to be a large fraction of the
# body's height or the figure reads as a tombstone: at half 54 over a 118-tall
# body the straight sides ran longer than the curve. Widening to 64 puts the
# curve in charge, which is the proportion the board carries.
_EMP_C_HEAD = _circle(128, 80, 34)
_EMP_C_BODY = _dome(128, 64, 112)
# Sides: smaller and seated LOWER, so the centre plainly dominates. Level with
# the centre they competed with it and the group had no nearest figure.
# head r22 at y116 -> bottom 138; body top 136.
_EMP_L_HEAD = _circle(56, 116, 22)
_EMP_L_BODY = _dome(56, 38, 136)
_EMP_R_HEAD = _circle(200, 116, 22)
_EMP_R_BODY = _dome(200, 38, 136)

_EMP_CENTRE = _EMP_C_BODY + " " + _EMP_C_HEAD
_EMP_LEFT = _EMP_L_BODY + " " + _EMP_L_HEAD
_EMP_RIGHT = _EMP_R_BODY + " " + _EMP_R_HEAD

# ---------------------------------------------------------------------------
# Inventory - a package cube with three explicit faces.
#
# The depth is built from the faces themselves, never from a gradient pretending
# to be a corner. The pale structural strip across the top and left face is a
# named V3 characteristic and is drawn, not filtered.
_TOP, _UR, _LR, _BOT, _LL, _UL = (128, 30), (210, 76), (210, 170), (128, 216), (46, 170), (46, 76)
_MID = (128, 122)
_INV_BODY = f"M{_TOP[0]} {_TOP[1]} L{_UR[0]} {_UR[1]} L{_LR[0]} {_LR[1]} L{_BOT[0]} {_BOT[1]} L{_LL[0]} {_LL[1]} L{_UL[0]} {_UL[1]} Z"
_INV_TOP = f"M{_TOP[0]} {_TOP[1]} L{_UR[0]} {_UR[1]} L{_MID[0]} {_MID[1]} L{_UL[0]} {_UL[1]} Z"
_INV_LEFT = f"M{_UL[0]} {_UL[1]} L{_MID[0]} {_MID[1]} L{_BOT[0]} {_BOT[1]} L{_LL[0]} {_LL[1]} Z"
_INV_RIGHT = f"M{_UR[0]} {_UR[1]} L{_LR[0]} {_LR[1]} L{_BOT[0]} {_BOT[1]} L{_MID[0]} {_MID[1]} Z"
_INV_STRIP = "M62 97 L128 134 L128 160 L62 123 Z"


def _gear(teeth: int = 9, outer: float = 100.0, root: float = 80.0,
          aperture: float = 40.0, cx: float = 128.0, cy: float = 128.0,
          tooth: float = 0.44) -> tuple[str, str]:
    """A gear as (body, aperture).

    Teeth are wide rather than fine: the constitution requires them readable at
    small size, and a narrow tooth is the first thing a downscale destroys. The
    aperture is the recognition cue and is kept large for the same reason.
    """
    step = 2 * math.pi / teeth
    half = step * tooth / 2
    pts = []
    for i in range(teeth):
        a = i * step - math.pi / 2
        for ang, rad in ((a - half, outer), (a + half, outer),
                         (a + step / 2 - half * 0.7, root), (a + step / 2 + half * 0.7, root)):
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    body = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z"
    return body, _circle(cx, cy, aperture)


_MRP_BODY, _MRP_APERTURE = _gear()
# The gear has no accent facet of its own. A square quadrant was tried and cut
# straight across the teeth, so the gold half read as a SECOND gear overlapping
# the first. The board puts the gold on a diagonal shard passing through the
# gear, which is what shard-br already is, so the primary plane carries it.

# ---------------------------------------------------------------------------
# CRM - a forward ribbon.
#
# A chevron, not a play triangle: the notch on the trailing edge is what makes
# it read as motion through a pipeline rather than as a media control. The
# manifest's semantic master is "Relationship pipeline / forward ribbon", and an
# earlier funnel and an earlier suitcase glyph both failed that.
_CRM_BODY = ("M62.9 25.4 L193.1 120.6 Q206 130 193.1 139.4 L62.9 234.6 "
             "Q50 244 50 228 L50 32 Q50 16 62.9 25.4 Z")
# The forward plane: the lower half, which is where the board carries its teal.
_CRM_LEAD = "M50 130 H206 L50 244 Z"


# ---------------------------------------------------------------------------
# hr_expense - a receipt.
#
# The torn foot is the whole recognition cue. A rectangle with ruled lines is a
# document; the tear is what makes it a receipt, and it survives the downscale
# because it changes the SILHOUETTE rather than the interior.
_EXP_BODY = ("M78 24 H178 Q190 24 190 36 V214 L172 230 L153 215 L134 230 "
             "L115 215 L96 230 L78 215 L66 226 V36 Q66 24 78 24 Z")
_EXP_BAND = "M66 36 Q66 24 78 24 H178 Q190 24 190 36 V62 H66 Z"
_EXP_MARKS = (
    "M92 84 H164 Q169 84 169 89 Q169 94 164 94 H92 Q87 94 87 89 Q87 84 92 84 Z "
    "M92 114 H164 Q169 114 169 119 Q169 124 164 124 H92 Q87 124 87 119 Q87 114 92 114 Z "
    "M92 144 H136 Q141 144 141 149 Q141 154 136 154 H92 Q87 154 87 149 Q87 144 92 144 Z")
# At 16-24 three 10-unit rules collapse into one grey smear, the same failure
# Accounting has; two heavier rules keep the object reading as a printed slip.
_EXP_MARKS_SMALL = (
    "M92 96 H166 Q177 96 177 107 Q177 118 166 118 H92 Q81 118 81 107 Q81 96 92 96 Z "
    "M92 140 H140 Q151 140 151 151 Q151 162 140 162 H92 Q81 162 81 151 Q81 140 92 140 Z")

# ---------------------------------------------------------------------------
# contacts - a contact card.
#
# Card plus person, not a person alone: a bare figure is Employees with one
# head, and the two must not collide in the apps menu. The portrait panel is a
# real division of the card, so it can carry its own facet.
_CON_BODY = ("M48 56 H208 Q222 56 222 70 V186 Q222 200 208 200 H48 "
             "Q34 200 34 186 V70 Q34 56 48 56 Z")
_CON_PANEL = "M34 70 Q34 56 48 56 H114 V200 H48 Q34 200 34 186 Z"
_CON_PERSON = (_circle(74, 106, 21) + " M46 170 Q46 140 74 140 Q102 140 102 170 Z")
_CON_LINES = (
    "M134 100 H196 Q201 100 201 105 Q201 110 196 110 H134 Q129 110 129 105 Q129 100 134 100 Z "
    "M134 128 H196 Q201 128 201 133 Q201 138 196 138 H134 Q129 138 129 133 Q129 128 134 128 Z "
    "M134 156 H172 Q177 156 177 161 Q177 166 172 166 H134 Q129 166 129 161 Q129 156 134 156 Z")

# ---------------------------------------------------------------------------
# hr_recruitment - a candidate and an open role.
#
# One figure, not a cluster, and a plus for the seat still to fill. Employees is
# three figures; a single figure plus an explicit opening is the difference the
# silhouette has to carry at 16px.
_REC_PERSON = (_circle(100, 88, 33) + " M38 206 Q38 142 100 142 Q162 142 162 206 Z")
# Placed to OVERLAP the shoulder. Clear of the figure it read as two marks
# side by side rather than as one idea: a candidate and a seat to fill.
_REC_PLUS = "M182 98 H210 V126 H238 V154 H210 V182 H182 V154 H154 V126 H182 Z"

# ---------------------------------------------------------------------------
# hr_skills - a capability badge.
#
# A rosette: disc over two ribbon tails. The tails are what separate it from
# every other round mark in the family.
_SKL_TAILS = "M92 150 V238 L128 212 L164 238 V150 Z"
_SKL_DISC = _circle(128, 108, 68)
_SKL_CHECK = "M106 108 L122 124 L154 90 L168 104 L122 152 L92 122 Z"

# ---------------------------------------------------------------------------
# fleet - a delivery vehicle.
#
# Box, cab and two wheels. The wheels drop below the body line on purpose: they
# are what read as "vehicle" once the interior detail is gone at 16px.
_FLT_BOX = "M38 82 H150 Q162 82 162 94 V166 H26 V94 Q26 82 38 82 Z"
_FLT_CAB = "M162 110 H196 Q203 110 207 116 L228 144 V166 H162 Z"
_FLT_WHEELS = _circle(76, 174, 22) + " " + _circle(192, 174, 22)
_FLT_WINDOW = "M172 120 H194 L210 142 H172 Z"


# ---------------------------------------------------------------------------
# Shared primitives.
#
# Built once because the remaining families repeat the same few forms - a card,
# a sheet, a bubble - and because two icons that should look related must be
# related in the geometry, not by coincidence of hand-drawing.


def _rrect(x0: float, y0: float, x1: float, y1: float, r: float) -> str:
    """A rounded rectangle, corners equal."""
    return (f"M{x0 + r:g} {y0:g} H{x1 - r:g} Q{x1:g} {y0:g} {x1:g} {y0 + r:g} "
            f"V{y1 - r:g} Q{x1:g} {y1:g} {x1 - r:g} {y1:g} "
            f"H{x0 + r:g} Q{x0:g} {y1:g} {x0:g} {y1 - r:g} "
            f"V{y0 + r:g} Q{x0:g} {y0:g} {x0 + r:g} {y0:g} Z")


def _bar(x0: float, x1: float, y: float, h: float) -> str:
    """One ruled mark with round ends - the family's detail vocabulary."""
    r = h / 2
    return (f"M{x0 + r:g} {y:g} H{x1 - r:g} Q{x1:g} {y:g} {x1:g} {y + r:g} "
            f"Q{x1:g} {y + h:g} {x1 - r:g} {y + h:g} H{x0 + r:g} "
            f"Q{x0:g} {y + h:g} {x0:g} {y + r:g} Q{x0:g} {y:g} {x0 + r:g} {y:g} Z")


def _bars(rows) -> str:
    return " ".join(_bar(*r) for r in rows)


# --- Commerce, Procurement, Retail -----------------------------------------
#
# Sales and Purchase are both order documents and must not become the same
# mark. The difference is put in the SILHOUETTE, not the interior: Sales carries
# a seal breaking its lower edge, Purchase an arrow entering from above. At 16px
# the ruled lines are gone and only those two profiles remain.
_SALE_SHEET = _rrect(56, 30, 188, 214, 12)
_SALE_SEAL = _circle(180, 198, 34)
_SALE_MARKS = _bars([(82, 162, 74, 11), (82, 162, 104, 11), (82, 132, 134, 11)])

_PUR_BOX = _rrect(44, 116, 212, 230, 12)
_PUR_ARROW = "M112 26 H144 V96 H176 L128 148 L80 96 H112 Z"
_PUR_SEAM = _bar(70, 186, 160, 12)

_POS_BODY = _rrect(48, 92, 208, 230, 14)
_POS_SLIP = "M78 20 H178 V96 H162 L148 84 L134 96 L120 84 L106 96 L92 84 L78 96 Z"
_POS_KEYS = _bars([(76, 124, 140, 16), (140, 180, 140, 16), (76, 124, 172, 16), (140, 180, 172, 16)])

_BAG_BODY = _rrect(44, 92, 212, 232, 16)
_BAG_HANDLE = ("M92 100 V74 Q92 34 128 34 Q164 34 164 74 V100 H142 V74 "
               "Q142 56 128 56 Q114 56 114 74 V100 Z")

# --- Hospitality and People Services ---------------------------------------
_CLOCHE_DOME = "M40 182 Q40 92 128 92 Q216 92 216 182 Z"
_CLOCHE_KNOB = _circle(128, 80, 16)
_CLOCHE_BASE = _rrect(24, 186, 232, 212, 13)

# The bowl needs a FLAT bottom, not a curve meeting at a point. Drawn as a
# single low point the base sat under it touching at one pixel, and the two read
# as a bowl and an unrelated bar rather than as a bowl on a stand.
_BOWL_BODY = "M34 116 H222 V148 Q222 210 166 210 H90 Q34 210 34 148 Z"
_BOWL_BASE = _rrect(74, 198, 182, 224, 12)

# --- Work and Time ---------------------------------------------------------
#
# The calendar body is shared by Calendar and Holidays on purpose - they are the
# same object in the product - and separated by silhouette: Holidays loses a
# corner to the plane that takes the day away.
def _calendar(x0=40, y0=64, x1=216, y1=222, r=14):
    return _rrect(x0, y0, x1, y1, r)


_CAL_RINGS = _rrect(74, 30, 92, 78, 9) + " " + _rrect(164, 30, 182, 78, 9)
_CAL_BAND = f"M40 78 H216 V112 H40 Z"
_CAL_DAYS = _bars([(70, 110, 136, 16), (128, 168, 136, 16), (70, 110, 170, 16)])
_HOL_BODY = ("M54 64 H216 V166 L160 222 H54 Q40 222 40 208 V78 Q40 64 54 64 Z")
_HOL_CORNER = "M216 166 L160 222 V180 Q160 166 174 166 Z"

_PRJ_SPINE = _rrect(36, 46, 62, 218, 13)
_PRJ_ROWS = (_rrect(76, 56, 220, 96, 12) + " " + _rrect(76, 112, 190, 152, 12)
             + " " + _rrect(76, 168, 148, 208, 12))

_TODO_CARD = _rrect(36, 58, 184, 218, 16)
_TODO_CHECK = "M92 150 L134 192 L232 66 L252 92 L136 236 L70 172 Z"

_ATT_HEAD = _circle(108, 78, 34)
_ATT_BODY = _dome(108, 62, 110, 206)
_ATT_CLOCK = _circle(196, 182, 48)
_ATT_HANDS = "M190 146 H202 V180 H232 V192 H190 Z"

_EVT_BODY = ("M36 60 H220 V108 Q196 108 196 130 Q196 152 220 152 V200 H36 "
             "V152 Q60 152 60 130 Q60 108 36 108 Z")
_EVT_STUB = "M150 60 H162 V200 H150 Z"
_EVT_MARKS = _bars([(72, 132, 106, 12), (72, 112, 142, 12)])


# --- Communication ---------------------------------------------------------
#
# Three modules share a bubble and must not collapse into one mark. Mail is two
# bubbles overlapping, Livechat is one bubble with a live pulse beside it, SMS
# is one bubble broadcasting. The count and the companion carry the difference,
# because at 16px the interior is gone and only the outline speaks.
def _bubble(x0, y0, x1, y1, r, tail=None):
    body = _rrect(x0, y0, x1, y1, r)
    return body if tail is None else body + " " + tail


_MAIL_BACK = _bubble(78, 36, 226, 148, 26)
_MAIL_FRONT = _bubble(30, 88, 178, 200, 26,
                      "M62 196 L62 238 L106 200 Z")
_MAIL_DOTS = (_circle(74, 144, 11) + " " + _circle(104, 144, 11) + " "
              + _circle(134, 144, 11))

_CHAT_BUBBLE = _bubble(30, 44, 196, 170, 28, "M64 166 L64 214 L112 174 Z")
_CHAT_PULSE = _circle(212, 68, 26)
_CHAT_DOTS = (_circle(74, 108, 11) + " " + _circle(108, 108, 11) + " "
              + _circle(142, 108, 11))

_SMS_BUBBLE = _bubble(24, 58, 170, 176, 26, "M56 172 L56 218 L102 180 Z")
_SMS_BEAM = ("M196 60 Q230 108 196 156 L214 172 Q256 110 214 44 Z "
             "M178 88 Q196 108 178 128 L194 142 Q220 108 194 74 Z")

_ENV_BODY = _rrect(28, 68, 228, 200, 16)
_ENV_FLAP = "M28 84 L128 152 L228 84 V106 L128 174 L28 106 Z"

# --- Digital and Knowledge -------------------------------------------------
_WEB_FRAME = _rrect(26, 48, 230, 208, 16)
_WEB_BAR = "M26 64 H230 V96 H26 Z"
_WEB_DOTS = (_circle(50, 80, 9) + " " + _circle(76, 80, 9) + " " + _circle(102, 80, 9))
_WEB_GLOBE = _circle(128, 152, 42)

_BOOK_LEFT = "M28 64 Q78 46 124 64 V202 Q78 184 28 202 Z"
_BOOK_RIGHT = "M132 64 Q178 46 228 64 V202 Q178 184 132 202 Z"
_BOOK_PLAY = "M110 108 L172 140 L110 172 Z"

# --- Equipment -------------------------------------------------------------
#
# Maintenance is a wrench alone. Repair is the same wrench over a part that has
# come apart - the split is the whole difference and it lives in the silhouette.
# An open-ended spanner, drawn head-up. The first attempt laid it diagonally and
# relied on a thin notch for the jaw; softened and scaled it closed to a plain
# tube and stopped reading as a tool at all. The jaw is now a wide bite out of
# the head, which is the one feature that has to survive to 16px.
# Head and handle as two shapes, unioned. Drawn as one outline the jaw ran as
# deep as the handle was wide and the whole thing read as a tuning fork: two
# prongs on a stick. A spanner is a BULB with a bite out of it, carrying a
# narrower handle - the head has to be about three times the handle's width and
# the jaw shallower than the head is tall.
_WRENCH = ("M70 40 H108 V76 H148 V40 H186 V106 Q186 132 160 132 H96 "
           "Q70 132 70 106 Z "
           "M110 124 H146 V212 Q146 236 128 236 Q110 236 110 212 Z")
# A part that has come apart: two halves with the break between them, so Repair
# differs from Maintenance in the silhouette rather than only in an accent.
# One block, broken. The two halves face each other across a jagged break, so
# the pair reads as a thing that came apart rather than as two containers.
_REP_PART_L = "M14 170 H92 L74 198 L92 226 H14 Z"
_REP_PART_R = "M164 170 H242 V226 H164 L182 198 Z"

# --- Insights and Marketing ------------------------------------------------
_SUR_SHEET = _rrect(48, 28, 208, 228, 14)
_SUR_BOXES = (_rrect(72, 62, 104, 94, 7) + " " + _rrect(72, 116, 104, 148, 7)
              + " " + _rrect(72, 170, 104, 202, 7))
_SUR_TICK = "M78 78 L90 90 L118 60 L128 72 L90 112 L66 88 Z"
_SUR_ROWS = _bars([(120, 184, 70, 14), (120, 184, 124, 14), (120, 162, 178, 14)])

_CARD_BACK = _rrect(64, 40, 228, 158, 14)
_CARD_FRONT = _rrect(28, 92, 192, 218, 14)
_CARD_ROWS = _bars([(52, 130, 126, 14), (52, 166, 158, 14), (52, 112, 190, 14)])

# --- System ----------------------------------------------------------------
#
# Recycle: three arrows chasing a block. Drawn as one closed loop with three
# heads rather than three separate chevrons, so a downscale cannot orphan one.
# One loop with one arrowhead, not three chasing chevrons. Three merged into a
# single blob the moment they were softened and reduced; a ring with a gap reads
# as "returns to where it started" at any size. The ring is a real hole, cut
# even-odd by the aperture, the same way the gear's centre is.
_REC_RING = _circle(128, 122, 86)
_REC_HOLE = _circle(128, 122, 52)
_REC_HEAD = "M196 40 L232 106 L160 106 Z"
_REC_BLOCK = _rrect(100, 94, 156, 150, 12)


MASTERS: dict[str, dict[str, str]] = {
    "accounting": {"body": _ACC_BODY, "fold": _ACC_FOLD, "detail": _ACC_MARKS,
                   "detail_small": _ACC_MARKS_SMALL},
    # The body is the union of all three figures, so the silhouette is one mass.
    # Each figure is also named separately, because depth order matters: the
    # centre is drawn last, in front of both neighbours.
    "employees": {"body": " ".join((_EMP_LEFT, _EMP_RIGHT, _EMP_CENTRE)),
                  "centre": _EMP_CENTRE, "left": _EMP_LEFT, "right": _EMP_RIGHT},
    # The cube's OUTER silhouette is softened; its three internal edges are not.
    # That is how the board reads: a solid whose corners catch light, whose face
    # boundaries stay crisp because they are real edges of the form. The faces
    # are clipped to the body at render time, so they follow the softened hull.
    "inventory": {"body": soften(_INV_BODY, SOFTEN_RADIUS["inventory"]),
                  "face_top": _INV_TOP, "face_left": _INV_LEFT,
                  "face_right": _INV_RIGHT, "strip": _INV_STRIP},
    "manufacturing": {"body": soften(_MRP_BODY, SOFTEN_RADIUS["manufacturing"]),
                      "aperture": _MRP_APERTURE},
    "crm": {"body": _CRM_BODY, "lead": _CRM_LEAD},
    "hr_expense": {"body": _EXP_BODY, "band": _EXP_BAND, "detail": _EXP_MARKS,
                   "detail_small": _EXP_MARKS_SMALL},
    "contacts": {"body": _CON_BODY, "panel": _CON_PANEL,
                 "detail": _CON_PERSON + " " + _CON_LINES},
    "hr_recruitment": {"body": _REC_PERSON + " " + _REC_PLUS, "opening": _REC_PLUS},
    "hr_skills": {"body": _SKL_TAILS + " " + _SKL_DISC, "tails": _SKL_TAILS,
                  "detail": _SKL_CHECK},
    # The wheels are named separately as well as unioned into the body: at
    # one colour with the chassis they disappeared and the van read as a box.
    "fleet": {"body": soften(_FLT_BOX + " " + _FLT_CAB + " " + _FLT_WHEELS, 4.0),
              "cab": _FLT_CAB, "wheels": _FLT_WHEELS, "detail": _FLT_WINDOW},

    # --- Commerce, Procurement, Retail, Hospitality, Work and Time ---------
    "sale": {"body": _SALE_SHEET + " " + _SALE_SEAL, "seal": _SALE_SEAL,
             "detail": _SALE_MARKS},
    "purchase": {"body": _PUR_BOX + " " + _PUR_ARROW, "arrow": _PUR_ARROW,
                 "detail": _PUR_SEAM},
    "point_of_sale": {"body": _POS_BODY + " " + _POS_SLIP, "slip": _POS_SLIP,
                      "detail": _POS_KEYS},
    "website_sale": {"body": _BAG_BODY + " " + _BAG_HANDLE, "handle": _BAG_HANDLE},
    "pos_restaurant": {"body": soften(_CLOCHE_DOME + " " + _CLOCHE_BASE, 3.0)
                               + " " + _CLOCHE_KNOB,
                       "base": _CLOCHE_BASE, "knob": _CLOCHE_KNOB},
    "lunch": {"body": soften(_BOWL_BODY + " " + _BOWL_BASE, 3.0), "base": _BOWL_BASE},
    "project": {"body": _PRJ_SPINE + " " + _PRJ_ROWS, "spine": _PRJ_SPINE,
                "rows": _PRJ_ROWS},
    "project_todo": {"body": _TODO_CARD + " " + _TODO_CHECK, "check": _TODO_CHECK,
                     "card": _TODO_CARD},
    "calendar": {"body": _calendar() + " " + _CAL_RINGS, "band": _CAL_BAND,
                 "detail": _CAL_DAYS},
    "hr_holidays": {"body": _HOL_BODY + " " + _CAL_RINGS, "corner": _HOL_CORNER,
                    "band": _CAL_BAND, "detail": _CAL_DAYS},
    "hr_attendance": {"body": _ATT_HEAD + " " + _ATT_BODY + " " + _ATT_CLOCK,
                      "clock": _ATT_CLOCK, "detail": _ATT_HANDS},
    "event": {"body": _EVT_BODY, "stub": _EVT_STUB, "detail": _EVT_MARKS},

    # --- Communication, Digital, Knowledge, Equipment, Insights, System ----
    "mail": {"body": _MAIL_BACK + " " + _MAIL_FRONT, "back": _MAIL_BACK,
             "front": _MAIL_FRONT, "detail": _MAIL_DOTS},
    "im_livechat": {"body": _CHAT_BUBBLE + " " + _CHAT_PULSE, "pulse": _CHAT_PULSE,
                    "detail": _CHAT_DOTS},
    "mass_mailing_sms": {"body": _SMS_BUBBLE + " " + _SMS_BEAM, "beam": _SMS_BEAM},
    "mass_mailing": {"body": _ENV_BODY, "flap": _ENV_FLAP},
    "website": {"body": _WEB_FRAME, "bar": _WEB_BAR, "globe": _WEB_GLOBE,
                "detail": _WEB_DOTS},
    "website_slides": {"body": _BOOK_LEFT + " " + _BOOK_RIGHT, "right": _BOOK_RIGHT,
                       "detail": _BOOK_PLAY},
    "maintenance": {"body": fit(soften(_WRENCH, 3.0)), "tool": _WRENCH},
    "repair": {"body": fit(soften(_WRENCH + " " + _REP_PART_L + " " + _REP_PART_R, 3.0)),
               "partl": _REP_PART_L, "partr": _REP_PART_R},
    "survey": {"body": _SUR_SHEET, "boxes": _SUR_BOXES,
               "detail": _SUR_TICK + " " + _SUR_ROWS},
    "marketing_card": {"body": _CARD_BACK + " " + _CARD_FRONT, "back": _CARD_BACK,
                       "front": _CARD_FRONT, "detail": _CARD_ROWS},
    "data_recycle": {"body": _REC_RING + " " + _REC_HEAD + " " + _REC_BLOCK,
                     "aperture": _REC_HOLE, "block": _REC_BLOCK},
}


def master(key: str) -> dict[str, str]:
    return MASTERS[key]
