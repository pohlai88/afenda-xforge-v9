"""The crystal material: multi-stop gradients, light direction, and gloss.

A plane filled with two stops reads flat. Real material needs three things the
earlier passes did without:

* **a deep-to-bright sweep**, not two neighbouring hues, so the plane has range;
* **a light direction every plane agrees on**, so the facets read as one solid
  rather than as separate coloured regions;
* **a specular pass** - a narrow bright sweep across the upper shoulder of each
  plane, falling off before the middle.

Everything here is precomputed into explicit stops. The SVG carries the same
stops the rasteriser uses, so nothing depends on a blend mode and the two
outputs cannot disagree.
"""
from __future__ import annotations

import math

from PIL import Image

from .tokens import INK_NAVY, ICE_HIGHLIGHT, hex_of, mix, rgb

# One light, upper-left, shared by every plane and every module. The angle is
# the gradient's own direction in degrees, measured like SVG's x1/y1 -> x2/y2.
LIGHT_ANGLE = 52.0

# How far a plane's low stop is pushed toward the ink, and its high stop toward
# white. Wider than it looks: at less than this the plane reads flat next to the
# reference, which is what browser validation showed.
DEPTH_LOW = 0.30
DEPTH_HIGH = 0.16

GLOSS_ALPHA = 0.26        # peak opacity of the specular sweep
GLOSS_END = 0.46          # where it has fallen to nothing


class Gradient:
    """An ordered list of (offset, rgb) stops plus a direction in degrees."""

    __slots__ = ("stops", "angle")

    def __init__(self, stops, angle=LIGHT_ANGLE):
        self.stops = stops
        self.angle = angle

    @staticmethod
    def _lerp(a, b, t):
        """Length-aware, because the specular gradient's stops are alpha alone
        while a colour gradient's are three channels."""
        return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))

    def at(self, t: float):
        stops = self.stops
        if t <= stops[0][0]:
            return stops[0][1]
        for (o0, c0), (o1, c1) in zip(stops, stops[1:]):
            if t <= o1:
                span = (o1 - o0) or 1.0
                return self._lerp(c0, c1, (t - o0) / span)
        return stops[-1][1]

    def svg_stops(self) -> str:
        return "".join(f'<stop offset="{o:.3g}" stop-color="{hex_of(c)}"/>'
                       for o, c in self.stops)

    def svg_vector(self) -> str:
        a = math.radians(self.angle)
        dx, dy = math.cos(a), math.sin(a)
        # normalise the unit vector into the 0..1 object box SVG expects
        x1, y1 = 0.5 - dx / 2, 0.5 - dy / 2
        x2, y2 = 0.5 + dx / 2, 0.5 + dy / 2
        return f'x1="{x1:.4g}" y1="{y1:.4g}" x2="{x2:.4g}" y2="{y2:.4g}"'


def crystal(lo, hi, *, angle: float = LIGHT_ANGLE) -> Gradient:
    """A plane's fill: deep shoulder, the declared hues through the middle, a
    lifted edge where the light lands."""
    deep = mix(lo, rgb(INK_NAVY), DEPTH_LOW)
    bright = mix(hi, (255, 255, 255), DEPTH_HIGH)
    return Gradient([(0.0, deep), (0.30, lo), (0.66, hi), (1.0, bright)], angle)


def gloss(angle: float = LIGHT_ANGLE) -> Gradient:
    """The specular sweep, as alpha. Colour is the ice highlight throughout."""
    return Gradient([(0.0, (GLOSS_ALPHA,)), (GLOSS_END, (0.0,)), (1.0, (0.0,))], angle)


# ----------------------------------------------------------- rasterising ---
_RAMP_CACHE: dict[tuple[float, int], Image.Image] = {}


def ramp_mask(side: int, angle: float) -> Image.Image:
    """A 0..255 linear ramp across ``side`` at ``angle``, fully covering it."""
    key = (round(angle, 3), side)
    hit = _RAMP_CACHE.get(key)
    if hit is not None:
        return hit
    base = Image.linear_gradient("L")              # 256x256, 0 at top
    rot = base.rotate(-angle - 90, resample=Image.BILINEAR, expand=True)
    w, h = rot.size
    inscribed = int(256 / math.sqrt(2)) if (angle % 90) else 256
    left, top = (w - inscribed) // 2, (h - inscribed) // 2
    out = rot.crop((left, top, left + inscribed, top + inscribed)) \
             .resize((side, side), Image.BILINEAR)
    _RAMP_CACHE[key] = out
    return out


def paint_gradient(side: int, grad: Gradient) -> Image.Image:
    """Render a multi-stop gradient by mapping one ramp through a per-channel LUT.

    A lookup table rather than a per-pixel loop: the gradient is a function of a
    single scalar, so the work is 256 evaluations and three channel maps however
    large the icon gets.
    """
    ramp = ramp_mask(side, grad.angle)
    luts = [[0] * 256 for _ in range(3)]
    for v in range(256):
        c = grad.at(v / 255)
        for ch in range(3):
            luts[ch][v] = max(0, min(255, round(c[ch])))
    bands = [ramp.point(luts[ch]) for ch in range(3)]
    return Image.merge("RGB", bands)


def paint_alpha(side: int, grad: Gradient, scale: float = 1.0) -> Image.Image:
    """An L-mode alpha ramp, for the specular pass."""
    ramp = ramp_mask(side, grad.angle)
    lut = [max(0, min(255, round(grad.at(v / 255)[0] * 255 * scale))) for v in range(256)]
    return ramp.point(lut)


def gloss_layer(side: int, mask: Image.Image, angle: float = LIGHT_ANGLE,
                scale: float = 1.0) -> Image.Image:
    """The specular sweep, already clipped to ``mask``."""
    from PIL import ImageChops
    layer = Image.new("RGBA", (side, side), rgb(ICE_HIGHLIGHT) + (0,))
    layer.putalpha(ImageChops.multiply(paint_alpha(side, gloss(angle), scale), mask))
    return layer
