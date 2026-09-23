"""Render an AFENDA app icon over every module icon Odoo ships.

Odoo's 108 module icons are the most visible Odoo artwork left once the logos
are replaced: they fill the apps menu. This redraws each one as a free-standing
duotone mark, keeping the upstream file name and pixel size so no manifest,
template or menu record has to change.

The construction, and why it is this one
----------------------------------------
Odoo's own icons are not flat silhouettes: they are 40-69% transparent, carry
three or more colours, and get their depth from two shapes crossing. A flat
brand tile with a white glyph reads as one app repeated 108 times at apps-menu
size. So each icon here is built the way Odoo's are:

    * a FontAwesome glyph in colour A,
    * a geometric accent shape in colour B overlapping it,
    * and a controlled darkening of A and B wherever the two cross.

There is no container tile. The mark stands free on transparency, which is what
makes a row of them legible: the silhouettes differ, not just their contents.

Colour A is the module's functional family (money, people, operations, time and
delivery, communication, market, equipment, system); colour B and the accent
shape are chosen per module. The one rule the shape has to obey: it must not
land on the glyph's identifying feature - not a bar across a list, not a disc
over a calendar's face. A corner disc in empty space is the safe default.

Modules with no glyph mapping get the AFENDA mark in grey with no accent, so
the technical plumbing recedes behind the real apps.

Run through the image renderer, which calls in here:
    python -m afenda.tools.brand_images
"""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha1
from pathlib import Path
from typing import Iterable, NamedTuple

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from .brand_images import BOXED_INK, MARK_BOX, MARK_FRAME, SS, WHITE, arms_in, draw_mark, mark_svg
from .xforge_icons.paths import bounds, flatten_path, scale_polygons
from .xforge_icons.v4_shapes import SHAPES as AUTHORED_SHAPES

# The AFENDA tag palette (afenda_brand/brand.py "tags") plus Ledger Blue. Every
# hex in this block appears in brand.py and is mirrored into SCSS, because these
# are interface colours: they land on an icon a user reads as a category.
#
# The mark imported from brand_images above is the exception the rules allow
# (.claude/odoo-agent-rules.md, the identity-artwork carve-out). Its shades exist
# only inside the drawn mark, are deliberately absent from brand.py and SCSS, and
# must not be reused as UI tokens.
LEDGER = "#1E3A8A"
SLATE = "#3B6EA8"
INDIGO = "#3448A8"
TEAL = "#2F8F8A"
MOSS = "#4C8A56"
PLUM = "#7C4F7F"
MULBERRY = "#A8447A"
OCHRE = "#B5651D"
MUSTARD = "#A16207"
BRICK = "#A33A3A"
CLAY = "#9A6B4F"
VIOLET = "#6B5FA8"
GREY = "#9CA3AF"

GLYPH_SCALE = 0.84  # the glyph's longer dimension, as a share of the short side
SVG_SIDE = 50.0  # every upstream icon.svg is viewBox="0 0 50 50"
MAX_SUPERSAMPLED = 1024  # a few module icons are thousands of pixels wide

# How much of the glyph's ink the accent may cover.
#
# OVERLAP_BAND is what the design wants: enough crossing to make a third colour
# and some depth, not so much that the accent becomes the larger shape. It is
# REPORTED, never enforced - see `overlap_report` and the test that prints it.
# Two thirds of the mapped set sits above it today, and turning it into a gate
# would bulk-reassign accents that were each placed by eye. MAX_OVERLAP is the
# gate: past half the glyph the accent reads as a stain.
#
# GLYPH_SCALE moved 0.88 -> 0.84 in V2, which changes every one of these
# numbers (a smaller glyph leaves more of a fixed accent outside it). Re-measure
# before anyone argues for tightening the gate toward the band.
OVERLAP_BAND = (0.08, 0.29)
TARGET_OVERLAP = 0.20
MAX_OVERLAP = 0.50

# The intersection colour must stay this luminous. Raw RGB multiply of two
# mid-dark brand colours lands near black - Ledger Blue x Ochre is the worst -
# and a near-black intersection reads as a hole punched in the mark rather than
# as two shapes crossing. See `controlled_overlap_colour`.
MIN_OVERLAP_LUMINANCE = 0.045

# Weights for `accent_score`, which only ever runs for a module with no accent
# shape of its own. Nothing in ACCENTS reaches it.
CENTRE_PENALTY = 2.4  # covering the glyph's middle costs more than its corners
OVERLAP_PENALTY = 5.0  # distance from TARGET_OVERLAP
EMPTY_ACCENT_PENALTY = 1.5  # an accent that barely touches the glyph is decoration
AUTO_SCORE_SIDE = 256  # the scorer rasterises here, so its answer is size-independent
AUTO = "auto"  # a Design.shape asking to be scored, like a shape of None

_REPO = Path(__file__).resolve().parents[2]
FA_TTF = str(_REPO / "addons" / "web" / "static" / "src" / "libs" / "fontawesome" / "fonts" / "fontawesome-webfont.ttf")

# The mark's ink box, in the frame brand_images draws it in. Imported rather
# than measured: the Engineered X is four straight-edged wedges with no stroke,
# so the box is just the extent of their coordinates, and the one place those
# coordinates live is brand_images.MARK_ARMS.
MARK_SVG_BOX = MARK_BOX

# Accent geometry, in a 0..100 box over the icon's SHORT side, so it holds for
# the handful of non-square icons too. Shapes run off the edge on purpose: a
# mark that bleeds reads as a shape, one that is inset reads as a sticker.
#   circle: (cx, cy, r)   polygon: ((x, y), ...)   rect: (x0, y0, x1, y1, r)
# "disc-*" crosses the glyph; "dot-*" only clips a corner, for glyphs whose
# whole area is load-bearing (lists, tables, grids).
ACCENT_SHAPES: dict[str, tuple[str, tuple]] = {
    "disc-br": ("circle", (70, 70, 34)),
    "disc-bl": ("circle", (30, 70, 34)),
    "disc-tr": ("circle", (72, 28, 34)),
    "dot-br": ("circle", (82, 82, 24)),
    "dot-bl": ("circle", (18, 82, 24)),
    "dot-tr": ("circle", (82, 18, 24)),
    "wedge-tr": ("polygon", ((46, -4), (104, -4), (104, 58))),
    "bar-b": ("rect", (6, 68, 94, 96, 13)),
    "bar-t": ("rect", (6, 4, 94, 32, 13)),
    # "shard-*" are the xForge accents: a clipped directional plane with one
    # angled edge, the same idea as the Engineered X's wedges, rather than a
    # disc. They are the candidates `choose_accent_shape` picks from for a
    # module nobody has art-directed. No entry in ACCENTS names one - reassigning
    # a shape that was placed by eye is a separate decision from offering a
    # better default.
    "shard-tr": ("polygon", ((48, -6), (106, -6), (106, 39), (71, 66))),
    "shard-br": ("polygon", ((71, 34), (106, 61), (106, 106), (48, 106))),
    "shard-bl": ("polygon", ((29, 34), (-6, 61), (-6, 106), (52, 106))),
    "shard-tl": ("polygon", ((52, -6), (-6, -6), (-6, 39), (29, 66))),
}

# The xForge band: a 45 degree plane crossing the icon, in the 0..100 box the
# accents use. It is never an accent in its own right - nothing in ACCENTS names
# one - it is the SECOND plane. It exists because the accent, once clipped to the
# body, leaves two colours where the design promises three: crossing the clipped
# accent with this band puts the third colour back, and puts it where V3 and V4
# put theirs, at the intersection of two planes inside the silhouette.
#
# A FIXED band does not work, and the measurement is worth keeping: with one
# band across every icon, 17 of the 50 lost a plane - the accent either missed
# it entirely (crossing 0.000 on project, purchase, survey) or sat wholly inside
# it (colour B at 0.001 on web, crm, board). So the band is PLACED per icon, the
# same principle V3's geometry states for its crossing: a module places its
# intersection, it does not discover where it fell.
BAND_WIDTH = 24.0  # perpendicular, in box units: V3's ribbon band is 20-28%
BAND_OFFSETS = tuple(range(-64, 65, 4))  # perpendicular shift from centre
BAND_SCORE_SIDE = 128  # the band is scored here, so its answer is size-independent
# What the crossing should take of the accent. Half would make the two planes
# the same size and read as a bisected accent; a third keeps the accent legible
# as one shape with a corner cut by the band.
BAND_TARGET = 0.34

# What `choose_accent_shape` may pick. Shards first because they carry the
# brand; discs cross too much of a glyph to be a safe default, so only the
# gentler "dot-*" and the two bars back the shards up.
AUTO_ACCENT_CANDIDATES: tuple[str, ...] = (
    "shard-tr", "shard-br", "shard-bl", "shard-tl",
    "dot-tr", "dot-br", "dot-bl", "bar-t", "bar-b",
)


class Design(NamedTuple):
    """What one icon draws: a glyph in ``glyph``, an accent in ``accent``."""

    code: str | None  # FontAwesome codepoint; None draws the AFENDA mark
    glyph: str  # colour A
    accent: str | None = None  # colour B; None draws the glyph alone
    shape: str | None = None  # a key of ACCENT_SHAPES
    art: str | None = None  # a key of AUTHORED_SHAPES; overrides the glyph
    band: tuple[int, int] | None = None  # (sign, offset) of the xForge band


# module -> FontAwesome 4 codepoint. Anything absent gets the AFENDA mark.
APP_GLYPHS: dict[str, str] = {
    "account": "f0d6",
    "contacts": "f2b9",
    "crm": "f0f2",
    "sale": "f290",
    "sale_management": "f290",
    "purchase": "f0d1",
    "stock": "f1b2",
    "mrp": "f085",
    "project": "f0ae",
    "project_todo": "f046",
    "hr": "f0c0",
    "hr_holidays": "f073",
    "hr_attendance": "f017",
    "hr_expense": "f09d",
    "hr_recruitment": "f0b1",
    "hr_timesheet": "f1da",
    "hr_skills": "f0a3",
    "calendar": "f133",
    "mail": "f075",
    "board": "f0e4",
    "website": "f0ac",
    "website_sale": "f07a",
    "website_blog": "f040",
    "website_slides": "f19d",
    "website_forum": "f086",
    "point_of_sale": "f291",
    "event": "f145",
    "im_livechat": "f27a",
    "lunch": "f0f5",
    "fleet": "f1b9",
    "maintenance": "f0ad",
    "mass_mailing": "f0e0",
    "mass_mailing_sms": "f10b",
    "sms": "f10b",
    "survey": "f0cb",
    "repair": "f1b3",
    "gamification": "f091",
    "data_recycle": "f1b8",
    "payment": "f09d",
    "payment_custom": "f19c",  # wire transfer: the one provider icon Odoo drew itself
    "payment_demo": "f0c3",  # the test provider
    "spreadsheet_dashboard": "f0ce",
    "utm": "f0e8",
    "base": "f013",
    "web": "f009",
}

# module -> (colour A, colour B, accent shape). One entry per APP_GLYPHS key;
# test_every_mapped_module_has_an_accent holds the two dicts together.
#
# Colour A is the family. Colour B and the shape are per module, picked so the
# accent lands in empty space rather than over the part of the glyph that says
# which app this is. Where two modules share a glyph (sms/mass_mailing_sms,
# sms/mass_mailing_sms) the accent is what tells them apart. sale and
# sale_management are one app in two packages, so they keep one glyph and
# differ by accent, the same way the two payment providers do.
ACCENTS: dict[str, tuple[str, str, str]] = {
    # --- money -----------------------------------------------------------
    "account": (LEDGER, TEAL, "disc-br"),
    "point_of_sale": (LEDGER, MUSTARD, "dot-br"),
    # Sales is money, not market: it was mulberry with the basket the till
    # now carries, and its disc sat straight through the basket's slats.
    "sale_management": (LEDGER, OCHRE, "dot-br"),
    "sale": (LEDGER, TEAL, "dot-bl"),
    "purchase": (LEDGER, OCHRE, "dot-br"),
    "hr_expense": (LEDGER, OCHRE, "disc-br"),
    "payment": (LEDGER, TEAL, "disc-bl"),
    "payment_custom": (LEDGER, OCHRE, "disc-bl"),
    "payment_demo": (LEDGER, MUSTARD, "disc-tr"),
    # --- people ----------------------------------------------------------
    "hr": (PLUM, OCHRE, "disc-bl"),
    "contacts": (PLUM, TEAL, "disc-br"),
    "hr_attendance": (PLUM, TEAL, "disc-br"),
    "hr_holidays": (PLUM, OCHRE, "bar-t"),  # a disc would cover the calendar face
    # wedge-tr met only 3.6% of the briefcase - it was nearly all outside the
    # glyph, which the renderer used to paint. Clipped to the body it all but
    # disappeared, taking the third colour with it. The scorer ranks the shards
    # higher, but the shards are the auto vocabulary and no ACCENTS entry names
    # one, so this takes the best shape outside that set: a bottom-left dot at
    # 17.3%, inside OVERLAP_BAND, clear of the handle the briefcase is read by.
    "hr_recruitment": (PLUM, MUSTARD, "dot-bl"),
    "hr_skills": (PLUM, MUSTARD, "disc-br"),
    "hr_timesheet": (PLUM, TEAL, "disc-bl"),
    "lunch": (PLUM, MOSS, "disc-br"),
    "gamification": (PLUM, MUSTARD, "disc-bl"),
    # --- operations ------------------------------------------------------
    "stock": (TEAL, OCHRE, "disc-br"),
    "mrp": (TEAL, OCHRE, "disc-bl"),
    "fleet": (TEAL, PLUM, "disc-br"),
    # --- equipment and upkeep --------------------------------------------
    "maintenance": (SLATE, TEAL, "disc-bl"),
    "repair": (SLATE, OCHRE, "disc-br"),
    # --- time and delivery -----------------------------------------------
    "calendar": (MOSS, OCHRE, "bar-t"),  # the bar rides the header, not the face
    "project": (MOSS, OCHRE, "dot-br"),  # every row of f0ae is load-bearing
    "project_todo": (MOSS, OCHRE, "disc-bl"),
    # --- communication ---------------------------------------------------
    "mail": (INDIGO, MULBERRY, "disc-br"),
    "im_livechat": (INDIGO, MULBERRY, "disc-bl"),
    "mass_mailing": (INDIGO, MULBERRY, "disc-br"),
    "mass_mailing_sms": (INDIGO, MULBERRY, "disc-bl"),
    "sms": (INDIGO, TEAL, "disc-br"),
    "website_forum": (INDIGO, MULBERRY, "bar-t"),  # wedge-tr fell to 0.0%
    # overlap at GLYPH_SCALE 0.84 - two colours in a three-colour family.
    # --- market ----------------------------------------------------------
    "crm": (MULBERRY, TEAL, "wedge-tr"),
    "website": (MULBERRY, TEAL, "disc-br"),
    "website_sale": (MULBERRY, OCHRE, "disc-bl"),
    "website_blog": (MULBERRY, TEAL, "disc-br"),  # f040 runs bl->tr; br is empty
    "website_slides": (MULBERRY, MUSTARD, "disc-br"),
    "survey": (MULBERRY, TEAL, "dot-br"),  # f0cb is a numbered list, all of it
    "utm": (MULBERRY, TEAL, "bar-t"),  # f0e8 fans out downward; the top is clear
    "event": (MULBERRY, OCHRE, "disc-tr"),
    # --- system ----------------------------------------------------------
    # A cog, a 2x2 grid and a dial are read by their negative space, and the
    # accent fills whatever it crosses: a disc closes the cog's hole and the
    # grid's gutters outright. Corner dots keep the counters open.
    "base": (GREY, LEDGER, "dot-br"),
    "web": (GREY, LEDGER, "dot-bl"),
    "board": (GREY, SLATE, "dot-tr"),
    "spreadsheet_dashboard": (GREY, LEDGER, "dot-br"),
    "data_recycle": (GREY, MOSS, "disc-br"),
}

# Modules whose icon is a third party's mark, not Odoo's. Do not brand these.
#
# `addons/payment/data/payment_provider_data.xml` loads each one into
# `payment.provider.image_128`, and those blobs are what the provider form
# (`payment_provider_views.xml:34`) and kanban (`:153`) show: a screen whose whole
# job is telling Adyen from Stripe from PayPal. Branding them removes no Odoo
# identity and destroys the only thing distinguishing twenty-odd rows. The
# pos_* entries are the same story for cash-handling and terminal vendors.
# Customer-facing checkout is unaffected either way - it draws from
# `payment/static/img/`, which this generator never touches.
#
# If you are here to "finish the job", don't: these are deliberate.
THIRD_PARTY: frozenset[str] = frozenset({
    "payment_adyen",
    "payment_aps",
    "payment_asiapay",
    "payment_authorize",
    "payment_buckaroo",
    "payment_dpo",
    "payment_ecpay",
    "payment_flutterwave",
    "payment_iyzico",
    "payment_mercado_pago",
    "payment_mollie",
    "payment_nuvei",
    "payment_paymob",
    "payment_paypal",
    "payment_payu",
    "payment_razorpay",
    "payment_redsys",
    "payment_stripe",
    "payment_toss_payments",
    "payment_worldline",
    "payment_xendit",
    "pos_cashdro",
    "pos_cashmatic",
    "pos_glory_cash",
    "pos_mollie",
})

# odoo/addons/base ships artwork no `addons/*` glob reaches:
# `get_module_icon` (odoo/modules/module.py:380-396) falls back to
# base/static/description/icon.png for every module without one of its own, and
# base/views/base_menus.xml points the Settings, Apps and Tests root menus at
# settings.png, modules.png and exception.png. Leaving these Odoo's teal hexagon
# would brand every app in the menu except the ones an admin opens first.
BASE_DESCRIPTION = "odoo/addons/base/static/description"
BASE_ICONS: dict[str, Design] = {
    # The fallback IS the generic case, so it gets the generic treatment: the
    # AFENDA mark in grey with no accent, exactly like an unmapped module.
    # Giving it the f013 cog instead made it byte-identical to settings.png
    # below, so the Settings root menu looked like the mark ~530 modules show.
    "icon": Design(None, GREY),  # the fallback icon of ~530 module records
    "settings": Design(APP_GLYPHS["base"], *ACCENTS["base"]),  # Settings root menu
    "modules": Design(APP_GLYPHS["web"], *ACCENTS["web"]),  # Apps root menu
    "board": Design(APP_GLYPHS["board"], *ACCENTS["board"]),  # the dashboard
    # Warning triangle: the Tests menu and modules in error. Brick is the
    # brand's error colour; the accent sits on the upper slope, clear of the
    # exclamation mark the triangle is read by.
    "exception": Design("f071", BRICK, OCHRE, "disc-tr"),
}


# module -> a silhouette in afenda/tools/xforge_icons/v4_shapes.py.
#
# These five are the only modules whose shape was drawn rather than borrowed
# from FontAwesome, and they are the five the icon specification names. A glyph
# is a generic symbol that happens to be near the subject - f0f6 is "a page", not
# "an invoice"; f0b1 is "a briefcase", not "a pipeline". An authored silhouette
# says the module. Everything else about the icon - the accent, the band, the
# three planes, the colours - is identical either way, which is the point: this
# is one pipeline with two sources of geometry, not two icon systems.
#
# Drawing the long tail is incremental and needs no further code: add a shape
# to v4_shapes.SHAPES and a line here.
AUTHORED_ART: dict[str, str] = {
    "account": "accounting",
    "crm": "crm",
    "hr": "employees",
    "stock": "inventory",
    "mrp": "manufacturing",
}


def design_for(module: str) -> Design:
    """What ``module``'s icon draws - the AFENDA mark if it has no mapping."""
    art = AUTHORED_ART.get(module)
    code = APP_GLYPHS.get(module)
    if code is None:
        return Design(None, GREY, art=art)
    return Design(code, *ACCENTS[module], art=art)


@lru_cache(maxsize=1)
def _fa() -> TTFont:
    return TTFont(FA_TTF)


def glyph_name(code: str) -> str:
    """Name of the FontAwesome glyph for a codepoint, or raise."""
    cmap = _fa().getBestCmap()
    point = int(code, 16)
    if point not in cmap:
        raise KeyError(f"U+{code.upper()} is not in {FA_TTF}")
    return cmap[point]


def rgb(colour: str) -> tuple[int, int, int]:
    """``"#1E3A8A"`` -> ``(30, 58, 138)``."""
    h = colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def multiply(a: tuple[int, int, int], b: tuple[int, int, int]) -> tuple[int, int, int]:
    """Plain RGB multiply. Not the drawn colour - see `controlled_overlap_colour`."""
    return tuple(round(x * y / 255) for x, y in zip(a, b))


def _linear_channel(c: int) -> float:
    x = c / 255.0
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def relative_luminance(colour: tuple[int, int, int]) -> float:
    """WCAG relative luminance, 0.0 (black) to 1.0 (white)."""
    r, g, b = (_linear_channel(v) for v in colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def controlled_overlap_colour(a: tuple[int, int, int], b: tuple[int, int, int]) -> tuple[int, int, int]:
    """The third colour: what A and B make where the two shapes cross.

    Multiply is the right *cue* - the crossing has to read as darker than both
    shapes, the way two inks overprint - but raw multiply is not a colour
    anybody chose. Ledger Blue x Ochre multiplies to (21, 23, 16): a near-black
    that reads as a hole rather than as an overlap, and that is the same
    near-black plum x teal and indigo x mulberry collapse to, so the family
    loses the distinctions the second colour was there to make.

    So: mostly multiply, a little of the arithmetic midpoint, and then eased
    further toward the midpoint until the result clears MIN_OVERLAP_LUMINANCE.
    The darkening survives; the mud does not.
    """
    midpoint = tuple(round((x + y) / 2) for x, y in zip(a, b))
    colour = _lerp(multiply(a, b), midpoint, 0.28)
    # Ease, don't jump: the first pair that clears the floor keeps as much of
    # the multiply as it can. The loop bound is a guard, not a policy - it stops
    # at the midpoint, which is the lightest this is allowed to go. A pair whose
    # own midpoint is below the floor would leave here still below it, and
    # test_the_overlap_colour_clears_the_luminance_floor is what catches that.
    for _ in range(64):
        if relative_luminance(colour) >= MIN_OVERLAP_LUMINANCE:
            break
        eased = _lerp(colour, midpoint, 0.16)
        if eased == colour:
            break
        colour = eased
    return colour


def _mask_area(mask: Image.Image) -> float:
    """Alpha-weighted area of an L mask, in whole pixels."""
    return sum(level * count for level, count in enumerate(mask.histogram())) / 255.0


def _mask_intersection(a: Image.Image, b: Image.Image) -> Image.Image:
    """A and B: the alpha product, which is what coverage actually composes as."""
    return ImageChops.multiply(a, b)


def _mask_only(a: Image.Image, b: Image.Image) -> Image.Image:
    """A outside B: A * (1 - B).

    Not ``ImageChops.subtract``. Subtract is right only where both masks are 0
    or 255; on the antialiased rim where the glyph and the accent both sit at,
    say, half coverage, it yields 0 for both "only" layers and half for the
    intersection - so the three layers add up to half the coverage the union
    has, and the seam between glyph and accent renders as a translucent halo.
    The product form is exact: A*(1-B) + A*B == A at every alpha.
    """
    return ImageChops.multiply(a, ImageOps.invert(b))


def _central_identity_mask(side: int) -> Image.Image:
    """The glyph's middle, which an auto-placed accent is penalised for covering.

    This knows nothing about icon semantics. It encodes one default: the centre
    of a glyph carries more of what the glyph says than its corners do. Every
    module in ACCENTS names its own shape and never consults this.
    """
    mask = Image.new("L", (side, side), 0)
    p = side * 0.28
    ImageDraw.Draw(mask).rounded_rectangle((p, p, side - p, side - p), radius=side * 0.09, fill=255)
    return mask


def _supersample(width: int, height: int) -> int:
    """Antialias small icons without building a 30000px canvas for a big one."""
    return max(1, min(SS, MAX_SUPERSAMPLED // max(width, height)))


def _ink_layer(render, probe: float, target: float) -> Image.Image:
    """Render white ink at exactly ``target`` px on its longer side, cropped tight.

    ``render(scale)`` draws the shape on an L mask. Nominal size is not ink size
    - FontAwesome glyphs fill very different parts of their em box - so measure
    the ink at a probe scale, rescale, and crop to what was actually drawn. That
    keeps every icon's ink the same size and exactly centred.
    """
    box = render(probe).getbbox()
    if box is None:
        raise ValueError("nothing was drawn")
    ink = max(box[2] - box[0], box[3] - box[1])
    mask = render(max(1.0, probe * target / ink))
    glyph = mask.crop(mask.getbbox())
    layer = Image.new("RGBA", glyph.size, WHITE + (0,))
    layer.putalpha(glyph)
    return layer


def _glyph_layer(code: str, target: float) -> Image.Image:
    """One FontAwesome glyph as white ink, ``target`` px on its longer side."""
    char = chr(int(code, 16))
    glyph_name(code)  # refuse a codepoint the font does not have

    def render(size: float) -> Image.Image:
        size = max(1, round(size))
        font = ImageFont.truetype(FA_TTF, size)
        mask = Image.new("L", (size * 3, size * 3), 0)
        ImageDraw.Draw(mask).text((size, size), char, font=font, fill=255)
        return mask

    return _ink_layer(render, max(8.0, target), target)


def _mark_layer(target: float) -> Image.Image:
    """The AFENDA mark as white ink, ``target`` px on its longer side."""

    def render(unit: float) -> Image.Image:
        side = max(1, round(MARK_FRAME * unit))
        mask = Image.new("L", (side,) * 2, 0)
        draw_mark(ImageDraw.Draw(mask), arms_in(side, BOXED_INK), [255] * 4)
        return mask

    return _ink_layer(render, target / MARK_FRAME, target)


def _glyph_alpha(design: Design, side: int) -> Image.Image:
    """The glyph (or the mark), centred, as an alpha mask on a side x side box."""
    target = side * GLYPH_SCALE
    layer = _glyph_layer(design.code, target) if design.code else _mark_layer(target)
    mask = Image.new("L", (side, side), 0)
    mask.paste(layer.getchannel("A"), ((side - layer.width) // 2, (side - layer.height) // 2))
    return mask


@lru_cache(maxsize=None)
def _authored_alpha(art: str, side: int) -> Image.Image:
    """An authored silhouette, scaled and centred on a side x side box.

    Filled even-odd, so a shape whose contours nest - the gear's teeth around
    its open centre - keeps its hole, while a shape whose contours are disjoint
    - the three figures - unions them. That is the rule the SVG masters are
    authored against, so the PNG and the master agree by construction.

    The mask is binary. It is drawn at the supersampled side and resampled once
    by the caller, exactly like ``accent_mask``; antialiasing it here would
    antialias twice.
    """
    shape = AUTHORED_SHAPES[art](False)
    body = flatten_path(shape["body"])
    contours = list(body)
    if "aperture" in shape:
        contours.extend(flatten_path(shape["aperture"]))

    # Fit the body's own ink, not the nominal artboard: the authored shapes sit
    # in a 300x365 box with uneven margins, and centring on the box would put
    # every one of them off-centre in a square icon.
    x0, y0, x1, y1 = bounds(body)
    target = side * GLYPH_SCALE
    k = min(target / (x1 - x0), target / (y1 - y0))
    dx = (side - (x1 - x0) * k) / 2.0 - x0 * k
    dy = (side - (y1 - y0) * k) / 2.0 - y0 * k

    mask = Image.new("L", (side, side), 0)
    for poly in scale_polygons(contours, k, k, dx, dy):
        layer = Image.new("L", (side, side), 0)
        ImageDraw.Draw(layer).polygon(poly, fill=255)
        mask = ImageChops.difference(mask, layer)  # XOR on a binary mask
    return mask


def body_alpha(design: Design, side: int) -> Image.Image:
    """The icon's silhouette: its authored shape, or its glyph.

    The one place the two geometry sources meet. Everything downstream - the
    accent clip, the band, the three planes - is written against this and does
    not know or care which source it got.
    """
    if design.art:
        return _authored_alpha(design.art, side)
    return _glyph_alpha(design, side)


def accent_mask(shape: str, side: int) -> Image.Image:
    """Alpha mask for the overlapping accent shape, on a side x side box."""
    kind, geom = ACCENT_SHAPES[shape]
    mask = Image.new("L", (side, side), 0)
    draw = ImageDraw.Draw(mask)
    u = side / 100.0
    if kind == "circle":
        cx, cy, r = (v * u for v in geom)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    elif kind == "polygon":
        draw.polygon([(x * u, y * u) for x, y in geom], fill=255)
    elif kind == "rect":
        x0, y0, x1, y1, r = geom
        draw.rounded_rectangle((x0 * u, y0 * u, x1 * u, y1 * u), radius=r * u, fill=255)
    else:
        raise ValueError(kind)
    return mask


def band_points(band: tuple[int, int]) -> tuple[tuple[float, float], ...]:
    """The xForge band as four corners in the 0..100 box.

    ``sign`` is the diagonal - +1 rises to the right, -1 falls to the right -
    and ``offset`` shifts the band along its own normal, so the pair names one
    plane out of the two-by-N family the scorer chooses from. The band runs well
    past the box on both ends on purpose: a plane that stops inside the icon
    would show its own end, and a plane with a visible end is a stripe.
    """
    sign, offset = band
    k = 2 ** 0.5 / 2
    dx, dy = (k, -k) if sign > 0 else (k, k)
    nx, ny = -dy, dx
    cx, cy = 50.0 + nx * offset, 50.0 + ny * offset
    hw = BAND_WIDTH / 2.0
    far = 160.0
    return (
        (cx + nx * hw + dx * far, cy + ny * hw + dy * far),
        (cx + nx * hw - dx * far, cy + ny * hw - dy * far),
        (cx - nx * hw - dx * far, cy - ny * hw - dy * far),
        (cx - nx * hw + dx * far, cy - ny * hw + dy * far),
    )


def band_mask(band: tuple[int, int], side: int) -> Image.Image:
    """Alpha mask for the xForge band, on a side x side box."""
    mask = Image.new("L", (side, side), 0)
    u = side / 100.0
    ImageDraw.Draw(mask).polygon([(x * u, y * u) for x, y in band_points(band)], fill=255)
    return mask


def band_svg(band: tuple[int, int], fill: str | None = None) -> str:
    """The band as one SVG element, in the same box as ``_accent_svg``."""
    u = SVG_SIDE / 100.0
    points = " ".join(f"{x * u:g},{y * u:g}" for x, y in band_points(band))
    return f'<polygon points="{points}"{f" fill={fill!r}" if fill else ""}/>'.replace("'", '"')


def choose_band(accent: Image.Image, side: int) -> tuple[int, int]:
    """Where to put the band so it takes BAND_TARGET of this accent.

    Scored against the accent ALREADY CLIPPED to the body, because that is the
    shape the crossing is cut out of. Scoring against the unclipped accent would
    place the band by an area the icon never shows.
    """
    area = max(_mask_area(accent), 1.0)
    best, best_score = (1, 0), None
    for sign in (1, -1):
        for offset in BAND_OFFSETS:
            ratio = _mask_area(_mask_intersection(accent, band_mask((sign, offset), side))) / area
            score = abs(ratio - BAND_TARGET)
            if best_score is None or score < best_score:
                best, best_score = (sign, offset), score
    return best


def accent_score(glyph: Image.Image, accent: Image.Image) -> float:
    """How bad this accent is on this glyph. Lower is better.

    A placement engine for modules nobody has looked at, not a replacement for
    looking. It wants a deliberate crossing near TARGET_OVERLAP, it protects the
    glyph's middle, and it rejects an accent that only decorates the canvas.
    """
    glyph_area = max(_mask_area(glyph), 1.0)
    accent_area = max(_mask_area(accent), 1.0)
    overlap = _mask_intersection(glyph, accent)
    overlap_area = _mask_area(overlap)
    ratio = overlap_area / glyph_area
    low, high = OVERLAP_BAND

    score = abs(ratio - TARGET_OVERLAP) * OVERLAP_PENALTY
    score += _mask_area(_mask_intersection(overlap, _central_identity_mask(glyph.width))) / glyph_area * CENTRE_PENALTY
    if ratio < low:
        score += (low - ratio) * 8.0
    if ratio > high:
        score += (ratio - high) * 12.0
    # An accent mostly off in empty space is a sticker, not an overlap.
    score += max(0.0, 0.16 - overlap_area / accent_area) * EMPTY_ACCENT_PENALTY
    return score


def choose_accent_shape(glyph: Image.Image, side: int,
                        candidates: Iterable[str] = AUTO_ACCENT_CANDIDATES) -> str:
    """The least-bad accent for a glyph with no art direction of its own."""
    ranked = sorted((accent_score(glyph, accent_mask(shape, side)), shape) for shape in candidates)
    if not ranked:
        raise ValueError("no accent candidates")
    return ranked[0][1]


@lru_cache(maxsize=None)
def resolve_design(design: Design) -> Design:
    """``design`` with a real accent shape, scoring one if the mapping left it open.

    Every module in ACCENTS names its shape and comes back untouched. A shape of
    None or "auto" alongside an accent is a new or unmapped module asking to be
    placed; it is scored once, here, at a fixed size, so the PNG and the SVG
    cannot land on different answers.
    """
    if not design.accent:
        return design
    if not design.shape or design.shape == AUTO:
        design = design._replace(
            shape=choose_accent_shape(body_alpha(design, AUTO_SCORE_SIDE), AUTO_SCORE_SIDE))
    if design.band is None:
        clipped = _mask_intersection(accent_mask(design.shape, BAND_SCORE_SIDE),
                                     body_alpha(design, BAND_SCORE_SIDE))
        design = design._replace(band=choose_band(clipped, BAND_SCORE_SIDE))
    return design


def accent_overlap(design: Design, side: int = AUTO_SCORE_SIDE) -> float:
    """Share of the glyph's ink the accent covers, 0.0 if there is no accent."""
    design = resolve_design(design)
    if not design.accent:
        return 0.0
    body = body_alpha(design, side)
    ink = _mask_area(body)
    if not ink:
        return 0.0
    return _mask_area(_mask_intersection(body, accent_mask(design.shape, side))) / ink


def overlap_report() -> list[tuple[str, float]]:
    """(module, overlap share) for every mapped module, worst last.

    Reported, not enforced: see OVERLAP_BAND. The contact sheet and
    test_the_accent_overlap_band_is_reported both read this.
    """
    return sorted(((m, accent_overlap(design_for(m))) for m in ACCENTS), key=lambda r: r[1])


def plane_masks(design: Design, side: int) -> tuple[tuple[Image.Image, tuple[int, int, int]], ...]:
    """The icon as (mask, colour) planes on a side x side box, back to front.

    Three planes, and the silhouette is the body:

        1  body minus the accent                    colour A
        2  body and accent, minus the band          colour B
        3  body and accent and band                 the crossing colour

    The accent is CLIPPED to the body. Before this it was not, and the part of
    it hanging outside was painted too, so an icon's true silhouette was its
    glyph union a disc or a bar floating in empty space. Every icon had that,
    and at apps-menu size it read as a rendering fault rather than as design.

    Clipping alone would leave two colours - an accent wholly inside the body
    has no outside part to carry colour B - which is why the band exists. The
    three masks partition the body exactly:

        body\\accent  +  accent\\band  +  accent&band  ==  body

    and they are alpha-correct, so they sum to the body's coverage at every
    alpha and the seams carry no halo.
    """
    design = resolve_design(design)
    body = body_alpha(design, side)
    a = rgb(design.glyph)
    if not design.accent:
        return ((body, a),)
    b = rgb(design.accent)
    raw = accent_mask(design.shape, side)
    accent = _mask_intersection(raw, body)  # the accent, clipped to the body
    band = band_mask(design.band, side)
    # Plane 1 subtracts the RAW accent, not the clipped one. Both give the same
    # picture where coverage is full, and they differ along every antialiased
    # rim: body*(1 - body*accent) leaves a sliver of colour A under the accent's
    # own soft edge, and the three planes then sum to more than the body - 1.003
    # of it on hr_holidays, which is a bright halo traced around the accent.
    # body*(1 - accent) is the exact complement of the other two planes.
    return (
        (_mask_only(body, raw), a),
        (_mask_only(accent, band), b),
        (_mask_intersection(accent, band), controlled_overlap_colour(a, b)),
    )


def icon_png(width: int, height: int, design: Design) -> Image.Image:
    """The free-standing mark, at exactly width x height.

    Colour A carries the body, colour B the accent inside it, and
    `controlled_overlap_colour` where the accent crosses the xForge band -
    three opaque colours on transparency, no tile. See `plane_masks`.
    """
    design = resolve_design(design)
    ss = _supersample(width, height)
    w, h = width * ss, height * ss
    side = min(w, h)
    layers = plane_masks(design, side)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    offset = ((w - side) // 2, (h - side) // 2)
    for mask, colour in layers:
        layer = Image.new("RGBA", (side, side), colour + (0,))
        layer.putalpha(mask)
        im.alpha_composite(layer, offset)
    return im if ss == 1 else im.resize((width, height), Image.LANCZOS)


def _hex(colour: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*colour)


def _accent_svg(shape: str, fill: str | None = None) -> str:
    """The accent shape as one SVG element, in the same 0..100 box as the mask."""
    kind, geom = ACCENT_SHAPES[shape]
    u = SVG_SIDE / 100.0
    attr = f' fill="{fill}"' if fill else ""
    if kind == "circle":
        cx, cy, r = (f"{v * u:g}" for v in geom)
        return f'<circle cx="{cx}" cy="{cy}" r="{r}"{attr}/>'
    if kind == "polygon":
        points = " ".join(f"{x * u:g},{y * u:g}" for x, y in geom)
        return f'<polygon points="{points}"{attr}/>'
    if kind == "rect":
        x0, y0, x1, y1, r = geom
        return (f'<rect x="{x0 * u:g}" y="{y0 * u:g}" width="{(x1 - x0) * u:g}" '
                f'height="{(y1 - y0) * u:g}" rx="{r * u:g}"{attr}/>')
    raise ValueError(kind)


def _glyph_svg(code: str, fill: str) -> str:
    font = _fa()
    glyphs = font.getGlyphSet()
    glyph = glyphs[glyph_name(code)]
    bounds = BoundsPen(glyphs)
    glyph.draw(bounds)
    if bounds.bounds is None:
        raise ValueError(f"U+{code.upper()} has no outline")
    x0, y0, x1, y1 = bounds.bounds
    pen = SVGPathPen(glyphs)
    glyph.draw(pen)
    scale = SVG_SIDE * GLYPH_SCALE / max(x1 - x0, y1 - y0)
    half = SVG_SIDE / 2
    # The font's y axis points up and SVG's points down, hence the negative scale.
    transform = (
        f"translate({half:g} {half:g}) scale({scale:.5g} {-scale:.5g}) "
        f"translate({-(x0 + x1) / 2:.5g} {-(y0 + y1) / 2:.5g})"
    )
    return f'<path d="{pen.getCommands()}" fill="{fill}" transform="{transform}"/>'


def _mark_svg(fill: str) -> str:
    x0, y0, x1, y1 = MARK_SVG_BOX
    scale = SVG_SIDE * GLYPH_SCALE / max(x1 - x0, y1 - y0)
    half = SVG_SIDE / 2
    transform = (
        f"translate({half:g} {half:g}) scale({scale:.5g}) "
        f"translate({-(x0 + x1) / 2:.5g} {-(y0 + y1) / 2:.5g})"
    )
    return f'<g transform="{transform}">{mark_svg((fill,) * 4)}</g>'


def _authored_svg(art: str, fill: str) -> str:
    """An authored silhouette as one path, fitted the way the mask fits it.

    The path data goes out verbatim - the curves are not flattened here. The
    raster flattens because Pillow has to; the vector has no reason to, and
    shipping the authored curves means the SVG is the master rather than a
    polygonal trace of it.
    """
    shape = AUTHORED_SHAPES[art](False)
    d = shape["body"] + ((" " + shape["aperture"]) if "aperture" in shape else "")
    x0, y0, x1, y1 = bounds(flatten_path(shape["body"]))
    scale = SVG_SIDE * GLYPH_SCALE / max(x1 - x0, y1 - y0)
    half = SVG_SIDE / 2
    # Both axes written out, and POSITIVE on y. The glyph path comes from a font,
    # whose y axis points up, so it needs a negative y scale to land upright;
    # this path is authored in SVG coordinates and is already the right way up.
    # Writing scale(k k) rather than scale(k) keeps one transform grammar in the
    # file for anything reading these back.
    transform = (
        f"translate({half:g} {half:g}) scale({scale:.5g} {scale:.5g}) "
        f"translate({-(x0 + x1) / 2:.5g} {-(y0 + y1) / 2:.5g})"
    )
    return f'<path d="{d}" fill="{fill}" fill-rule="evenodd" transform="{transform}"/>'


def _ink_svg(design: Design, fill: str) -> str:
    if design.art:
        return _authored_svg(design.art, fill)
    return _glyph_svg(design.code, fill) if design.code else _mark_svg(fill)


def svg_clip_id(design: Design) -> str:
    """A clip-path id no other icon will use.

    A constant id is fine while every icon.svg is its own image resource, and
    wrong the moment two of them are inlined into one document - the second
    icon's clip silently resolves to the first icon's path, because ids are
    document-global and the first one wins. Derived from what the icon draws, so
    it is stable across renders and shows up in diffs only when the icon changes.
    """
    payload = f"{design.code}|{design.glyph}|{design.accent}|{design.shape}|{design.art}"
    return "afenda-accent-" + sha1(payload.encode("utf-8")).hexdigest()[:10]


def icon_svg(design: Design) -> str:
    """The same three planes the PNG composites, as vectors.

    The body in A, the accent over it clipped to the body in B, then the accent
    again clipped to the body AND the band in the crossing colour. Each layer is
    opaque and lies inside the one before it, so painting them in order gives
    the same picture as the raster's partition, without a blend mode no SVG
    renderer owes us - and the silhouette is the body, because nothing is ever
    painted outside the body clip.

    The shape has to be resolved already: scoring it here would mean rasterising
    inside the vector path, and a second chance for the PNG and the SVG to
    disagree. `render_all` resolves once and hands the concrete design to both.
    """
    side = f"{SVG_SIDE:g}"
    body = _ink_svg(design, design.glyph)
    if design.accent:
        if not design.shape or design.shape == AUTO:
            raise ValueError(f"{design.code}: an auto accent must be resolved before it is serialised")
        clip = svg_clip_id(design)
        overlap = _hex(controlled_overlap_colour(rgb(design.glyph), rgb(design.accent)))
        # The body is PAINTED and the accent CLIPS it, never the other way
        # round. Painting the accent and clipping it to the body would draw the
        # same picture, but it would need the body's path a second time inside a
        # clipPath, and a second copy of a path is a second thing to get wrong.
        # This way the only shape ever painted is the body, so the silhouette is
        # the body by construction rather than by agreement.
        body = (
            f'<defs>'
            f'<clipPath id="{clip}-accent">{_accent_svg(design.shape)}</clipPath>'
            f'<clipPath id="{clip}-band">{band_svg(design.band)}</clipPath>'
            f'</defs>'
            f'{body}'
            f'<g clip-path="url(#{clip}-accent)">{_ink_svg(design, design.accent)}</g>'
            f'<g clip-path="url(#{clip}-accent)"><g clip-path="url(#{clip}-band)">'
            f'{_ink_svg(design, overlap)}</g></g>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" '
        f'viewBox="0 0 {side} {side}">{body}</svg>\n'
    )


def _render(png: Path, design: Design) -> list[Path]:
    """Redraw ``png`` and, only if upstream ships one, the SVG beside it."""
    written = [png]
    with Image.open(png) as src:
        width, height = src.size
    icon_png(width, height, design).save(png)
    svg = png.with_suffix(".svg")
    if svg.exists():
        svg.write_text(icon_svg(design), encoding="utf-8")
        written.append(svg)
    return written


def render_all(root: Path) -> list[Path]:
    """Redraw every module icon under ``root``; never create one upstream lacks."""
    written: list[Path] = []
    for png in sorted(root.glob("addons/*/static/description/icon.png")):
        module = png.parents[2].name
        if module in THIRD_PARTY:
            continue
        written.extend(_render(png, resolve_design(design_for(module))))
    for stem, design in sorted(BASE_ICONS.items()):
        png = root.joinpath(BASE_DESCRIPTION, f"{stem}.png")
        if png.exists():
            written.extend(_render(png, resolve_design(design)))
    return written
