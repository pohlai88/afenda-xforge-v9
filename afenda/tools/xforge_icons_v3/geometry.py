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
from .spec import VIEWBOX

__all__ = ["MASTERS", "PLANES", "plane_points", "master", "soften", "SOFTEN_RADIUS"]

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
}


def master(key: str) -> dict[str, str]:
    return MASTERS[key]
