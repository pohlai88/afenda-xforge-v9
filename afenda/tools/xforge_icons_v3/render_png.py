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

Rendering happens at ``SS`` times the target and is reduced with LANCZOS.
resvg antialiases correctly on its own, but the masters are built for 256 and
the small end of the matrix is 16: supersampling is what keeps a 16px ledger
mark from landing between two pixel centres and disappearing.
"""
from __future__ import annotations

from io import BytesIO

import resvg_py
from PIL import Image

from .render_svg import icon_svg

__all__ = ["icon_png"]

SS = 4


def icon_png(key: str, size: int) -> Image.Image:
    """The icon at ``size``, carrying the material the responsive rule allows."""
    # The tier is chosen from the FINAL size, not the supersampled one, so a
    # 16px icon renders its flat duotone enlarged and then reduced, rather than
    # rendering the crystal material and reducing that to mud.
    svg = icon_svg(key, size)
    side = size * SS
    raw = resvg_py.svg_to_bytes(svg_string=svg, width=side, height=side)
    im = Image.open(BytesIO(bytes(raw))).convert("RGBA")
    return im.resize((size, size), Image.LANCZOS)
