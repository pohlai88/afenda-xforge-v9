"""OKLCH colour, and a Tailwind-v4-shaped tonal scale built on it.

The V4 palette was built in HSL, and HSL lies about lightness: gold at L50 and
azure at L50 are nowhere near the same perceived brightness, so a family whose
ramps are defined in HSL cannot cohere no matter how carefully the numbers are
chosen. Tailwind v4 moved its whole default palette to OKLCH for this reason,
and the same argument applies to an icon family.

In OKLCH:

* **L** is perceptual lightness. L 0.62 looks equally light whether the hue is
  amber or navy, which is what lets five module families share one ramp.
* **C** is chroma, and its ceiling depends on hue - a saturated yellow can reach
  far higher chroma than a saturated blue at the same L. Asking for more than
  the hue can carry is what produces the flat, clipped colours that read as
  cheap, so ``fit_chroma`` walks it down until the colour is in gamut.
* **H** is hue in degrees, stable across the ramp.

No dependency: the sRGB <-> OKLab matrices are small and exact.
"""
from __future__ import annotations

import math

# --- sRGB <-> OKLab -------------------------------------------------------
def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex_to_oklch(colour: str) -> tuple[float, float, float]:
    h = colour.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (v ** (1 / 3) if v > 0 else -((-v) ** (1 / 3)) for v in (l, m, s))
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def oklch_to_rgb(L: float, C: float, H: float) -> tuple[float, float, float]:
    a = C * math.cos(math.radians(H))
    b = C * math.sin(math.radians(H))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return tuple(_linear_to_srgb(v) for v in (r, g, bl))


def in_gamut(L: float, C: float, H: float) -> bool:
    return all(-0.0005 <= v <= 1.0005 for v in oklch_to_rgb(L, C, H))


def fit_chroma(L: float, C: float, H: float) -> float:
    """The most chroma this hue can carry at this lightness.

    Binary search rather than clipping RGB: clipping shifts the hue, which is
    how a family's dark end drifts off-colour. Walking chroma down keeps the hue
    exact and only gives up saturation, which is the tradeoff that looks right.
    """
    if in_gamut(L, C, H):
        return C
    lo, hi = 0.0, C
    for _ in range(24):
        mid = (lo + hi) / 2
        if in_gamut(L, mid, H):
            lo = mid
        else:
            hi = mid
    return lo


def oklch_hex(L: float, C: float, H: float) -> str:
    C = fit_chroma(L, C, H)
    r, g, b = oklch_to_rgb(L, C, H)
    return "#{:02X}{:02X}{:02X}".format(
        *(max(0, min(255, round(v * 255))) for v in (r, g, b)))


def oklch_css(L: float, C: float, H: float) -> str:
    """The same colour as a Tailwind-v4-style token value."""
    return f"oklch({L * 100:.1f}% {fit_chroma(L, C, H):.3f} {H:.1f})"


# --- the scale ------------------------------------------------------------
# Tailwind's steps. The lightness curve is perceptual, so one curve serves every
# hue: that is the whole point of moving off HSL.
STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)

_L = {50: 0.971, 100: 0.936, 200: 0.885, 300: 0.828, 400: 0.746, 500: 0.657,
      600: 0.578, 700: 0.497, 800: 0.420, 900: 0.348, 950: 0.262}

# Chroma peaks LOW, not in the middle. Expensive palettes carry their richness
# at 600-700 and let the light end go quiet; a curve peaking at 500 reads as
# poster colour rather than pigment.
_C_CURVE = {50: 0.12, 100: 0.22, 200: 0.40, 300: 0.58, 400: 0.76, 500: 0.90,
            600: 1.00, 700: 1.00, 800: 0.90, 900: 0.76, 950: 0.60}

# Chroma is spent as an ABSOLUTE target, the same for every family, and
# fit_chroma lowers it for any hue that cannot reach it.
#
# The first attempt here used an equal FRACTION OF EACH HUE'S CEILING, on the
# reasoning that it would equalise the families. Measuring it showed the
# opposite: the spread went from 1.75x to 2.82x. OKLCH chroma is already
# perceptually uniform, so an equal fraction hands magenta - ceiling 0.306 -
# nearly three times the chroma of teal at 0.113, which maximises the difference
# rather than removing it. Equal perceived saturation means equal C, full stop.
#
# 0.092 is reachable by all five hues at their peak steps and sits below where
# every family previously sat. Restraint is the cue: a jewel tone is deep, not
# loud.
CHROMA_TARGET = 0.092
ACCENT_TARGET = 0.125      # the inlay may be richer than the field

# Darks drift cooler, lights warmer, inside one family. Small, and the standard
# move that reads as depth: a ramp at one exact hue is correct and inert.
TEMP_SHIFT = 4.0
COOL_HUE, WARM_HUE = 258.0, 74.0


def _rotate(h: float, target: float, degrees: float) -> float:
    """Rotate h toward target by `degrees`, the short way round."""
    d = (target - h + 540) % 360 - 180
    return (h + (degrees if d > 0 else -degrees)) % 360


def _temp_hue(h: float, L: float) -> float:
    """The family's hue, warmed at the light end and cooled at the dark end."""
    t = (L - 0.5) * 2                      # -1 at the darkest, +1 at the lightest
    target = WARM_HUE if t > 0 else COOL_HUE
    return _rotate(h, target, TEMP_SHIFT * abs(t))


def _ceiling(L: float, h: float) -> float:
    return fit_chroma(L, 0.4, h)


def scale(anchor: str, *, target: float = CHROMA_TARGET) -> dict[int, str]:
    """A full 50-950 ramp from one anchor, in its own hue.

    Every step asks for the same absolute chroma, which in OKLCH means the same
    perceived saturation, so the five families land at one intensity however
    different their hues. A hue that cannot reach it is fitted down.
    """
    _, _, h0 = hex_to_oklch(anchor)
    out = {}
    for s in STEPS:
        L = _L[s]
        h = _temp_hue(h0, L)
        out[s] = oklch_hex(L, target * _C_CURVE[s], h)
    return out


def scale_css(anchor: str, *, target: float = CHROMA_TARGET) -> dict[int, str]:
    _, _, h0 = hex_to_oklch(anchor)
    out = {}
    for s in STEPS:
        L = _L[s]
        h = _temp_hue(h0, L)
        out[s] = oklch_css(L, target * _C_CURVE[s], h)
    return out


# --- contrast -------------------------------------------------------------
def relative_luminance(colour: str) -> float:
    h = colour.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio, for checking a family against its grounds."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
