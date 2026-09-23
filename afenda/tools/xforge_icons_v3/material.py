"""Crystal Duotone V3.1 - the material, and the responsive rule.

The material is a hierarchy, not a pile of layers:

    base structural body
    -> object facets (the form's own planes)
    -> primary translucent xForge plane
    -> controlled overlap where they cross
    -> restrained edge highlight

Five steps, in that order, and no more. The constitution asks for restraint:
few excellent planes rather than many decorative ones.

The responsive rule is part of the material, not an afterthought applied to the
output. The manifest states it for every module: flat duotone at 16-24, reduced
material at 32, crystal material at 48-128.
"""
from __future__ import annotations

import colorsys

__all__ = ["Tier", "tier_for", "TIERS", "controlled_overlap", "structural_dark",
           "facet_stops", "shift", "rgb", "hex_of", "mix"]

# Measured off the approved board: every dark on it is a fully saturated deep
# hue. #003060, #004060, #004070 and #004050 all sample at saturation 1.00, and
# nothing anywhere on the board is mixed toward grey or black. Mixing toward
# black is what made an earlier pass read as soot on the gear and as a heavy
# corner on the ledger.
STRUCTURAL_L = 0.19   # the lightness those samples share
STRUCTURAL_SAT_GAIN = 1.15


def rgb(colour: str) -> tuple[int, int, int]:
    h = colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hex_of(c) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in c))


def mix(a, b, t: float):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def structural_dark(colour, lightness: float = STRUCTURAL_L,
                    sat_gain: float = STRUCTURAL_SAT_GAIN) -> tuple[int, int, int]:
    """A plane's shadow tone: the same hue, driven down in lightness, not toward ink.

    Keeping chroma is the whole point. A dark mixed toward black loses its hue
    and reads as dirt; the board's own darks hold saturation 1.00 at this
    lightness.
    """
    r, g, b = (v / 255 for v in colour)
    h, _l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, lightness, min(1.0, s * sat_gain))
    return (round(r * 255), round(g * 255), round(b * 255))


# Shading INSIDE a facet, which is what separates the board from a flat fill.
# Measured on the approved board, each icon carries 15,700-22,300 distinct
# colours; a family of flat-filled facets produces 587-1,014, and almost all of
# those are edge antialiasing rather than modelling. One ramp across the whole
# body cannot supply that, because every facet drawn on top of it is constant.
# So each facet gets its own ramp across its own bounding box.
FACET_LIFT = 0.17
FACET_DROP = 0.15


# Where the light pools along the ramp. Two stops describe a flat plane tilted
# in a uniform field, which is why a two-stop facet still read as a panel: the
# value walks from one edge to the other at a constant rate and the eye reads
# the constancy. A real surface carries a bright region that falls away, so the
# third stop sits early and close to the lit end.
FACET_POOL = 0.42
FACET_POOL_SHARE = 0.18


def shift(colour, delta: float) -> str:
    """``colour`` moved ``delta`` in lightness, hue and chroma held.

    The family ramp needs this at both ends. Measured on the board, an icon's
    body runs from a near-white highlight to a deep saturated foot - a far wider
    travel than the declared base/base_hi pair alone, which lands entirely in
    the middle third of the value range and is why an earlier pass read as pale.
    """
    r, g, b = (v / 255 for v in (rgb(colour) if isinstance(colour, str) else colour))
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    rr, gg, bb = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l + delta)), sat)
    return hex_of((rr * 255, gg * 255, bb * 255))


def facet_stops(colour, lift: float = FACET_LIFT,
                drop: float = FACET_DROP) -> tuple[tuple[float, str], ...]:
    """One facet's own ramp as ``(offset, hex)`` stops, lit end first.

    Hue and chroma are held and only lightness travels, for the same reason
    ``structural_dark`` holds them: a ramp that drifts toward grey reads as
    dirt on the facet rather than as light falling across it.
    """
    r, g, b = (v / 255 for v in colour)
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    def at(delta: float) -> str:
        rr, gg, bb = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l + delta)), s)
        return hex_of((rr * 255, gg * 255, bb * 255))

    return ((0.0, at(lift)),
            (FACET_POOL, at(lift * FACET_POOL_SHARE)),
            (1.0, at(-drop)))


def _luminance(c) -> float:
    def f(v):
        x = v / 255
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = map(f, c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# A straight multiply of two mid-dark brand colours lands near black, and a
# near-black intersection reads as a hole punched through the icon rather than
# as two planes crossing. Below this luminance the multiply is pulled back
# toward the midpoint until it carries colour again.
MIN_OVERLAP_LUMINANCE = 0.055


def controlled_overlap(a, b):
    """The colour where two planes cross: a multiply that is not allowed to die."""
    raw = tuple(round(x * y / 255) for x, y in zip(a, b))
    return mix(raw, mix(a, b, 0.5), 0.24) if _luminance(raw) < MIN_OVERLAP_LUMINANCE else raw


class Tier:
    """One step of the responsive rule."""

    __slots__ = ("name", "gradients", "accent_alpha", "overlap_alpha",
                 "highlight_alpha", "detail", "detail_small", "sheen", "blur")

    def __init__(self, name, gradients, accent_alpha, overlap_alpha,
                 highlight_alpha, detail, detail_small=False,
                 sheen=0.0, blur=0.0):
        self.name = name
        self.gradients = gradients
        self.accent_alpha = accent_alpha
        self.overlap_alpha = overlap_alpha
        self.highlight_alpha = highlight_alpha
        self.detail = detail  # draw the object's fine marks (ledger lines, strip)
        # At the smallest sizes a master's fine marks are replaced by an
        # optically equivalent reduction rather than dropped: losing them
        # entirely costs the object its recognition cue.
        self.detail_small = detail_small
        # The glassy pool of light the board carries on every icon. A radial
        # sheen, not a linear ramp: light falls on a surface from a point.
        self.sheen = sheen
        # Edge softening, in master-box units, for the brand planes only.
        # Filters are permitted HERE and nowhere else - see the tier table.
        self.blur = blur


TIERS = {
    # 16-24: flat duotone. No gradient survives two pixels, and a translucent
    # plane at this size turns both colours to mud, so the accent goes opaque.
    "flat": Tier("flat", gradients=False, accent_alpha=1.00, overlap_alpha=1.00,
                 highlight_alpha=0.0, detail=True, detail_small=True,
                 sheen=0.0, blur=0.0),
    # 32: reduced material. Gradients return; highlight and shadow do not,
    # because at 32 both land on fewer than two pixels and only blur the edge.
    "reduced": Tier("reduced", gradients=True, accent_alpha=0.92, overlap_alpha=0.96,
                    highlight_alpha=0.0, detail=True,
                    sheen=0.09, blur=0.0),
    # 48-128: the full crystal material.
    # 48-128: the full crystal material, and the ONLY tier allowed a filter.
    # A blur rasterises differently between engines and falls apart below about
    # 32px, so it is confined to the sizes where it is both safe and the whole
    # point: the board's planes do not end on a hard line, they give way.
    # highlight_alpha is 0: it stroked the primary plane's outline in white,
    # which drew a visible diamond line across the people cluster. The board has
    # no such line - its planes show as a change of colour, not an edge - and
    # the crystal tier's blur now does the job that stroke was standing in for.
    "crystal": Tier("crystal", gradients=True, accent_alpha=0.82, overlap_alpha=0.80,
                    highlight_alpha=0.0, detail=True,
                    sheen=0.17, blur=4.5),
}


def tier_for(size: int) -> Tier:
    """The material a given output size is allowed to carry."""
    if size < 32:
        return TIERS["flat"]
    if size < 48:
        return TIERS["reduced"]
    return TIERS["crystal"]
