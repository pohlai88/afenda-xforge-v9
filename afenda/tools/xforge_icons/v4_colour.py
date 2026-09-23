"""V4 colour: the tonal rules measured from the Version 3 reference board.

Sampling the reference icon by icon gives five findings, and they are what
separate it from a competent flat palette:

1. **Two analogous hues, one distant accent.** Accounting runs 198/180/216 -
   a 36 degree span, no accent at all. Manufacturing runs 198/216 plus amber at
   36. Employees runs 342/288 plus the same amber. The base pair is always
   close; the accent is always far.

2. **A steep share hierarchy.** The dominant family carries 51-84% of the ink,
   the second 15-26%, the third 2-5%. The accent is never more than a quarter.
   Three planes at equal weight is what makes an icon read as a flat diagram.

3. **An enormous tonal range inside ONE hue.** Accounting's azure runs L20 to
   L84 - sixty-four points of lightness in a single hue family. The depth comes
   from tone, not from swapping colours.

4. **Darks stay saturated.** The deepest tones sampled are #00224E and #001B4F,
   both S100 at L15. Nothing is mixed toward grey or black; a neutral dark is
   what makes a palette look cheap.

5. **Lights desaturate.** Employees' violet falls from S42 to S13 at its light
   end; Inventory's teal from S87 to S50. Highlights move toward a hue-tinted
   white, never a saturated pastel and never pure white.

Everything below is those five rules as code.
"""
from __future__ import annotations

import colorsys

# Measured from the board: the span of a single family's tonal ramp.
TONE_DARK_L = 0.19
TONE_MID_L = 0.38
TONE_LIGHT_L = 0.82

# Darks gain a little chroma; lights lose most of theirs.
DARK_SAT_GAIN = 1.06
LIGHT_SAT_KEEP = 0.52


def _hsl(colour: str):
    h = colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh, ss, ll


def _hex(h, s, ll) -> str:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, ll)), max(0.0, min(1.0, s)))
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def tone(colour: str, lightness: float, sat_scale: float = 1.0) -> str:
    """Move a colour along its own tonal ramp, keeping its hue.

    This is the workhorse. Every V4 stop is one hue at a chosen lightness, which
    is what gives a family sixty points of range without drifting off-hue.
    """
    h, s, _ = _hsl(colour)
    return _hex(h, min(1.0, s * sat_scale), lightness)


def deepen(colour: str, amount: float = 0.46) -> str:
    """A saturated deep version of a colour, for a plane's thickness.

    Never toward ink: the reference's darkest sample is S100 at L15. A riser
    mixed toward neutral reads as grime on a gold plane and as soot on a navy
    one, which is exactly what the earlier V4 riser did.
    """
    h, s, ll = _hsl(colour)
    return _hex(h, min(1.0, s * DARK_SAT_GAIN), ll * (1.0 - amount))


def lift(colour: str, amount: float = 0.58) -> str:
    """A desaturated light version, for a leading edge catching light.

    Toward a hue-tinted white rather than white itself: pure white kills the
    family, and a saturated pastel reads as plastic.
    """
    h, s, ll = _hsl(colour)
    return _hex(h, s * LIGHT_SAT_KEEP, ll + (1.0 - ll) * amount)


def family(hue_anchor: str, *, dark=TONE_DARK_L, mid=TONE_MID_L, light=TONE_LIGHT_L):
    """A three-stop ramp in one hue: saturated dark, chromatic mid, tinted light.

    Returns stops in the emitter's (offset, colour, opacity) shape.
    """
    return [("0", tone(hue_anchor, dark, DARK_SAT_GAIN), None),
            (".52", tone(hue_anchor, mid), None),
            ("1", tone(hue_anchor, light, LIGHT_SAT_KEEP), None)]


def plane(hue_anchor: str, *, top: float, bottom: float, o_top: str, o_bottom: str):
    """A translucent plane's ramp: one hue, opening light and closing dark."""
    return [("0", tone(hue_anchor, top, LIGHT_SAT_KEEP + 0.22), o_top),
            (".58", tone(hue_anchor, (top + bottom) / 2), str(round(
                (float(o_top) + float(o_bottom)) / 2, 2))),
            ("1", tone(hue_anchor, bottom, DARK_SAT_GAIN), o_bottom)]


# ---------------------------------------------------------------------------
# The five families, rebuilt on the measured structure.
#
# Each is an analogous BASE pair plus one distant ACCENT. The accent is carried
# by the overlap plane alone - the smallest of the three - so its share lands in
# the reference's 11-23% band instead of competing with the base.
FAMILIES = {
    # 198 azure dominant, 180 cyan secondary, no warm accent: the reference's
    # Accounting is entirely cool, and adding gold here would break it.
    "accounting": {"base": "#1F79A3", "glass": "#33B4B6", "accent": "#0B4E7C"},
    # 288 violet dominant, 342 rose secondary, 36 gold accent.
    "employees": {"base": "#6E347A", "glass": "#CD618D", "accent": "#DBA44B"},
    # 180 teal dominant, 168 sea secondary, 36 amber accent.
    # The board's sea sample is S25, which is a shaded facet rather than the
    # hue itself; taken literally as an anchor the whole family goes grey.
    "inventory": {"base": "#188F8C", "glass": "#2FAE9C", "accent": "#D19B47"},
    # 198 azure dominant, 216 deep blue secondary, 36 amber accent.
    "manufacturing": {"base": "#0C70A8", "glass": "#1BAAD9", "accent": "#C88E3B"},
    # 324 magenta dominant, 300 violet secondary, 186 teal accent.
    # Anchored at L45 rather than the board's L58 highlight sample: an anchor is
    # the family's midtone, and taking a highlight as one lifts the whole ramp.
    "crm": {"base": "#A8357F", "glass": "#6E2A6B", "accent": "#1398A2"},
}


def stops_for(key: str) -> dict:
    """The four gradients a master needs, in the emitter's stop shape."""
    f = FAMILIES[key]
    return {
        # the semantic object: the full sixty-point ramp of the dominant hue
        "base": family(f["base"]),
        # the glass plane: the secondary analogous hue, opening bright
        "glass": plane(f["glass"], top=0.74, bottom=0.30, o_top=".88", o_bottom=".46"),
        # the structural plane: the dominant hue at its deepest, nearly opaque
        "deep": plane(deepen(f["base"], 0.58), top=0.26, bottom=0.13,
                      o_top=".97", o_bottom=".90"),
        # the accent: the distant hue, and the only plane carrying it
        "overlap": plane(f["accent"], top=0.62, bottom=0.34, o_top=".80", o_bottom=".60"),
    }


# ---------------------------------------------------------------------------
# OKLCH scales. These supersede the HSL helpers above for every gradient stop.
#
# HSL was the wrong space: azure at HSL L38 and amber at HSL L55 differ by only
# 17 HSL points but by 18 OKLCH points, so "the same lightness" in HSL is not
# the same perceived lightness at all, and five families defined that way cannot
# read as one system. Tailwind v4 moved its palette to OKLCH for this reason and
# the argument is identical here.
from .oklch import ACCENT_TARGET, contrast, scale, scale_css  # noqa: E402

PAPER = "#FBFAF6"
INK = "#0A1120"


def ramps(key: str) -> dict[int, str]:
    """The dominant family's 50-950 ramp."""
    return scale(FAMILIES[key]["base"])


def stops_oklch(key: str) -> dict:
    """Every gradient a master needs, expressed as steps on the OKLCH scales.

    Naming steps rather than hand-picked hexes is what makes the five families
    comparable: `deep` is 800/900/950 in every module, so the structural plane
    sits at one perceived depth across the set.
    """
    f = FAMILIES[key]
    base, glass = scale(f["base"]), scale(f["glass"])
    # the accent is inlay, not a third field colour: richer chroma, and it
    # only ever appears in the crossing, which is the smallest region
    accent = scale(f["accent"], target=ACCENT_TARGET)
    return {
        # the object: mid, into its depth, opening light again - the shape of
        # the approved master's own base gradient
        "base": [("0", base[500], None), (".47", base[700], None), ("1", base[400], None)],
        # the glass arm: the analogous hue, light and translucent at its head
        "glass": [("0", glass[300], ".88"), (".58", glass[500], ".67"),
                  ("1", glass[700], ".46")],
        # the structural arm: the dominant hue at its deepest, nearly opaque
        "deep": [("0", base[800], ".97"), (".58", base[900], ".94"),
                 ("1", base[950], ".90")],
        # the crossing: the distant accent, and the only place it appears
        "overlap": [("0", accent[500], ".84"), (".58", accent[700], ".76"),
                    ("1", accent[800], ".66")],
    }


def riser_of(anchor: str) -> str:
    """A plane's thickness: step 900 of its own hue, never a shared grey."""
    return scale(anchor)[900]


def edge_of(anchor: str) -> str:
    """A plane's lit leading edge: step 200 of its own hue."""
    return scale(anchor)[200]


def tint_of(key: str) -> str:
    """The family's own near-white, for the rim light and the specular.

    Pure white on a coloured ground is the cheapest-looking thing in a palette;
    step 50 carries the family's hue at almost no chroma instead.
    """
    return scale(FAMILIES[key]["base"])[50]


def tailwind_theme() -> str:
    """The same palette as a Tailwind v4 `@theme` block.

    One source for both surfaces: the icons and the web client cannot drift,
    because a module's 700 is the same colour in an SVG gradient stop and in a
    `bg-accounting-700` utility.
    """
    lines = ['@import "tailwindcss";', "",
             "/* AFENDA xForge module families — generated, do not hand-edit.",
             " * Source: afenda/tools/xforge_icons/v4_colour.py",
             " * Scales are OKLCH so one lightness curve serves every hue. */",
             "@theme {"]
    for key in FAMILIES:
        lines.append(f"  /* {key} */")
        for step, css in scale_css(FAMILIES[key]["base"]).items():
            lines.append(f"  --color-{key}-{step}: {css};")
        lines.append("")
    lines += ["  /* grounds */",
              f"  --color-paper: {PAPER};",
              f"  --color-ink: {INK};",
              "}", ""]
    return "\n".join(lines)


def contrast_report() -> list[tuple[str, int, float, float]]:
    """Each family's steps against paper and ink, for the accessibility gate."""
    out = []
    for key in FAMILIES:
        sc = scale(FAMILIES[key]["base"])
        for step in (400, 500, 600, 700, 800):
            out.append((key, step, contrast(sc[step], PAPER), contrast(sc[step], INK)))
    return out
