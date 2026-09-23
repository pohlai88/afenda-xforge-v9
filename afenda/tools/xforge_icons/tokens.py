"""Design tokens for the AFENDA xForge Application Icon System, Version 3.

These are renderer inputs, not UI tokens. They live here rather than in
``afenda_brand.brand`` for the reason stated in ``.claude/odoo-agent-rules.md``:
a colour that exists only inside a drawn mark is a renderer input, and putting
it in ``brand.py`` would advertise it as a colour the web client may use.

Every value below is quoted from the Version 3 specification. Adjust only when
visual QA proves it necessary, and say so in the commit.
"""
from __future__ import annotations

# --- palette ---------------------------------------------------------------
INK_NAVY = "#0B2442"
DEEP_NAVY = "#073B66"
OCEAN_BLUE = "#087FAE"
SIGNAL_CYAN = "#16B6D9"
CRYSTAL_AQUA = "#64DDD4"
CORE_TEAL = "#16AAA8"

DEEP_PLUM = "#542260"
ROYAL_PURPLE = "#74307E"
XFORGE_MAGENTA = "#C72D7A"
CRYSTAL_ROSE = "#E86A9C"

FORGE_OCHRE = "#C8891C"
FORGE_GOLD = "#F1B94E"

ICE_HIGHLIGHT = "#E9FBFF"
COOL_SILVER = "#B5BFCC"
CLOUD_WHITE = "#F6F8FB"

PALETTE = {
    "ink_navy": INK_NAVY, "deep_navy": DEEP_NAVY, "ocean_blue": OCEAN_BLUE,
    "signal_cyan": SIGNAL_CYAN, "crystal_aqua": CRYSTAL_AQUA, "core_teal": CORE_TEAL,
    "deep_plum": DEEP_PLUM, "royal_purple": ROYAL_PURPLE,
    "xforge_magenta": XFORGE_MAGENTA, "crystal_rose": CRYSTAL_ROSE,
    "forge_ochre": FORGE_OCHRE, "forge_gold": FORGE_GOLD,
    "ice_highlight": ICE_HIGHLIGHT, "cool_silver": COOL_SILVER,
    "cloud_white": CLOUD_WHITE,
}

# --- canvas ----------------------------------------------------------------
ARTBOARD = 1024          # canonical SVG artboard, transparent
LIVE_AREA = 824          # usable live area, optically centred
LARGE_SIZES = (64, 128, 256, 512)
SMALL_SIZES = (16, 24, 32, 48)
ALL_SIZES = SMALL_SIZES + LARGE_SIZES

# Below this, gradients are flattened, the highlight is dropped and the
# intersection is driven to its solid value. Above it, the full material runs.
SMALL_THRESHOLD = 48
SHADOW_THRESHOLD = 48    # "a very soft grounding shadow only at 48px and larger"

# --- the xForge X ----------------------------------------------------------
# Two crossing ribbons at +/-45 degrees. Width is a share of the live area; the
# specification asks for 20-28%. 22% keeps the semantic object dominant, which
# the specification also requires - at 24% the ribbons read as the subject.
#
# The ribbon plane is drawn TRANSLUCENT over the base rather than in the third
# hue at full strength: "controlled translucent layering", and it is what stops
# the X reading as a sticker pasted over the object.
RIBBON_WIDTH = 0.22
RIBBON_ANGLES = (45.0, -45.0)
RIBBON_ALPHA = 0.88   # ribbon hue over the base plane
# 0.88, not lower: at 0.74 a gold ribbon over a teal base blends to olive, and
# "deep black or muddy brown intersections" is on the specification's avoid
# list. Translucency here is structural - it ties the plane to the object -
# but it must not eat the hue that makes the plane legible.


class Family:
    """One module's three dominant hues plus its deliberate intersection.

    ``base`` and ``base_hi`` carry the semantic object, ``ribbon`` the xForge
    planes, and ``intersect`` the crossing - explicit rather than blended, so
    the exported SVG and PNG agree without relying on the renderer.
    """

    __slots__ = ("key", "label", "base", "base_hi", "ribbon", "ribbon_hi", "intersect")

    def __init__(self, key, label, base, base_hi, ribbon, ribbon_hi, intersect):
        self.key, self.label = key, label
        self.base, self.base_hi = base, base_hi
        self.ribbon, self.ribbon_hi = ribbon, ribbon_hi
        self.intersect = intersect

    def as_dict(self):
        return {"key": self.key, "label": self.label, "base": self.base,
                "base_hi": self.base_hi, "ribbon": self.ribbon,
                "ribbon_hi": self.ribbon_hi, "intersection": self.intersect}


FAMILIES = {
    "accounting": Family(
        "accounting", "Accounting",
        OCEAN_BLUE, SIGNAL_CYAN, CORE_TEAL, CRYSTAL_AQUA, DEEP_NAVY),
    "employees": Family(
        "employees", "Employees",
        ROYAL_PURPLE, XFORGE_MAGENTA, FORGE_OCHRE, FORGE_GOLD, DEEP_PLUM),
    "inventory": Family(
        "inventory", "Inventory",
        CORE_TEAL, CRYSTAL_AQUA, FORGE_OCHRE, FORGE_GOLD, DEEP_NAVY),
    "manufacturing": Family(
        "manufacturing", "Manufacturing",
        OCEAN_BLUE, SIGNAL_CYAN, FORGE_OCHRE, FORGE_GOLD, DEEP_NAVY),
    "crm": Family(
        "crm", "CRM",
        ROYAL_PURPLE, XFORGE_MAGENTA, CORE_TEAL, SIGNAL_CYAN, DEEP_PLUM),
}

ORDER = ("accounting", "employees", "inventory", "manufacturing", "crm")

RENDERER_VERSION = "xforge-v3.0"


def rgb(colour: str) -> tuple[int, int, int]:
    h = colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hex_of(c) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in c))


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _lin(v: int) -> float:
    x = v / 255
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def luminance(c) -> float:
    return 0.2126 * _lin(c[0]) + 0.7152 * _lin(c[1]) + 0.0722 * _lin(c[2])
