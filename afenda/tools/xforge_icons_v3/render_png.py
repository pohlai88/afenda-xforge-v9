"""Derived raster: the canonical SVG, rasterised.

The build direction is specification -> geometry -> SVG -> PNG. The SVG is the
master and the PNG is its rendering, which is what the reconstruction directive
asks for literally.

An earlier version re-implemented every icon a second time in Pillow polygons,
because there was no SVG rasteriser here - native Cairo on Windows is what the
icon pipeline was built to avoid. That deviation cost more than it saved. Two
implementations of one picture drift: they had already diverged over which
ledger marks to draw at 16 and 24, and a polygon compositor cannot carry a
gradient inside a facet at all, which is the property that separates the
approved board from a flat fill.

``resvg`` replaces it. It is a self-contained wheel with no Python dependencies
and no system libraries, so the reason Cairo was avoided does not apply to it.

Rendering happens at ``SS`` times the target and is reduced back down. resvg
antialiases correctly on its own, but the masters are built for 256 and the
small end of the matrix is 16: supersampling is what keeps a 16px ledger mark
from landing between two pixel centres and disappearing.
"""
from __future__ import annotations

from io import BytesIO

import resvg_py
from PIL import Image, ImageChops

from .render_svg import icon_svg

__all__ = ["icon_png"]

SS = 4


def _reduce(im: Image.Image, size: int) -> Image.Image:
    """Downscale to ``size`` without dragging the transparent ground into the edge.

    Resampling a straight-alpha RGBA resamples colour and alpha independently,
    so every partly-covered pixel on the rim averages in the RGB of pixels that
    are not there. Those pixels are transparent BLACK, and the measured cost is
    not subtle: against a correct reduction the rim of these masters was off by
    a mean of 170 to 237 per pixel, summed across the channels, which reads as a
    dark halo on a light ground.

    The fix is to weight colour by coverage before resampling and divide it back
    out afterwards. BOX is used rather than LANCZOS because ``SS`` is an exact
    integer factor, which makes BOX the true area average - and because LANCZOS
    has negative lobes that overshoot a flat region next to an edge, landing it
    a step above its own colour.

    Only the rim needs dividing back out: at full coverage the weighting is the
    identity, and at zero coverage there is no colour to recover.
    """
    r, g, b, a = im.split()
    weighted = Image.merge("RGBA", tuple(ImageChops.multiply(c, a) for c in (r, g, b)) + (a,))
    small = weighted.resize((size, size), Image.BOX)
    px = small.load()
    for y in range(size):
        for x in range(size):
            cr, cg, cb, ca = px[x, y]
            if ca == 0:
                px[x, y] = (0, 0, 0, 0)
            elif ca < 255:
                px[x, y] = (min(255, (cr * 255 + ca // 2) // ca),
                            min(255, (cg * 255 + ca // 2) // ca),
                            min(255, (cb * 255 + ca // 2) // ca), ca)
    return small


def icon_png(key: str, size: int) -> Image.Image:
    """The icon at ``size``, carrying the material the responsive rule allows."""
    # The tier is chosen from the FINAL size, not the supersampled one, so a
    # 16px icon renders its flat duotone enlarged and then reduced, rather than
    # rendering the crystal material and reducing that to mud.
    svg = icon_svg(key, size)
    raw = resvg_py.svg_to_bytes(svg_string=svg, width=size * SS, height=size * SS)
    return _reduce(Image.open(BytesIO(bytes(raw))).convert("RGBA"), size)
