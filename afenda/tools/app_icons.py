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
    * and the multiply of A and B wherever the two cross.

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
from pathlib import Path
from typing import NamedTuple

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont

from .brand_images import MARK_SVG_INNER, SS, WHITE, _mark

# The AFENDA tag palette (afenda_brand/brand.py "tags") plus Ledger Blue. No
# hex is invented here; every value below appears in brand.py.
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

GLYPH_SCALE = 0.88  # the glyph's longer dimension, as a share of the short side
SVG_SIDE = 50.0  # every upstream icon.svg is viewBox="0 0 50 50"
MAX_SUPERSAMPLED = 1024  # a few module icons are thousands of pixels wide
ACCENT_CLIP_ID = "afenda-accent"  # the clip path the SVG's multiply layer uses

_REPO = Path(__file__).resolve().parents[2]
FA_TTF = str(_REPO / "addons" / "web" / "static" / "src" / "libs" / "fontawesome" / "fonts" / "fontawesome-webfont.ttf")

# MARK_SVG_INNER draws in brand_images' 64x64 tile space. This is its ink box
# there: the Engineered X is four straight-edged wedges with no stroke, so the
# box is just the extent of their coordinates - a 34.56 square, centred.
# `test_the_mark_box_matches_the_mark` re-derives it from the paths, so a
# redrawn mark fails here instead of silently mis-centring every SVG fallback.
MARK_SVG_BOX = (14.72, 14.72, 49.28, 49.28)

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
}


class Design(NamedTuple):
    """What one icon draws: a glyph in ``glyph``, an accent in ``accent``."""

    code: str | None  # FontAwesome codepoint; None draws the AFENDA mark
    glyph: str  # colour A
    accent: str | None = None  # colour B; None draws the glyph alone
    shape: str | None = None  # a key of ACCENT_SHAPES


# module -> FontAwesome 4 codepoint. Anything absent gets the AFENDA mark.
APP_GLYPHS: dict[str, str] = {
    "account": "f0d6",
    "contacts": "f2b9",
    "crm": "f0f2",
    "sale": "f291",
    "sale_management": "f291",
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
    "point_of_sale": "f0d6",
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
# account/point_of_sale) the accent is what tells them apart; sale and
# sale_management are one app in two packages and deliberately render alike.
ACCENTS: dict[str, tuple[str, str, str]] = {
    # --- money -----------------------------------------------------------
    "account": (LEDGER, TEAL, "disc-br"),
    "point_of_sale": (LEDGER, MUSTARD, "disc-bl"),
    "hr_expense": (LEDGER, OCHRE, "disc-br"),
    "payment": (LEDGER, TEAL, "disc-bl"),
    "payment_custom": (LEDGER, OCHRE, "disc-bl"),
    "payment_demo": (LEDGER, MUSTARD, "disc-br"),
    # --- people ----------------------------------------------------------
    "hr": (PLUM, OCHRE, "disc-bl"),
    "contacts": (PLUM, TEAL, "disc-br"),
    "hr_attendance": (PLUM, TEAL, "disc-br"),
    "hr_holidays": (PLUM, OCHRE, "bar-t"),  # a disc would cover the calendar face
    "hr_recruitment": (PLUM, MUSTARD, "wedge-tr"),
    "hr_skills": (PLUM, MUSTARD, "disc-br"),
    "hr_timesheet": (PLUM, TEAL, "disc-bl"),
    "lunch": (PLUM, MOSS, "disc-br"),
    "gamification": (PLUM, MUSTARD, "disc-bl"),
    # --- operations ------------------------------------------------------
    "stock": (TEAL, OCHRE, "disc-br"),
    "mrp": (TEAL, OCHRE, "disc-bl"),
    "purchase": (TEAL, OCHRE, "disc-tr"),
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
    "website_forum": (INDIGO, MULBERRY, "wedge-tr"),
    # --- market ----------------------------------------------------------
    "crm": (MULBERRY, TEAL, "wedge-tr"),
    "sale": (MULBERRY, OCHRE, "disc-bl"),
    "sale_management": (MULBERRY, OCHRE, "disc-bl"),
    "website": (MULBERRY, TEAL, "disc-br"),
    "website_sale": (MULBERRY, OCHRE, "disc-bl"),
    "website_blog": (MULBERRY, TEAL, "disc-br"),  # f040 runs bl->tr; br is empty
    "website_slides": (MULBERRY, MUSTARD, "disc-br"),
    "survey": (MULBERRY, TEAL, "dot-br"),  # f0cb is a numbered list, all of it
    "utm": (MULBERRY, TEAL, "disc-bl"),
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


def design_for(module: str) -> Design:
    """What ``module``'s icon draws - the AFENDA mark if it has no mapping."""
    code = APP_GLYPHS.get(module)
    if code is None:
        return Design(None, GREY)
    return Design(code, *ACCENTS[module])


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
    """The third colour: what A and B make where the two shapes cross."""
    return tuple(round(x * y / 255) for x, y in zip(a, b))


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
        mask = Image.new("L", (max(1, round(64 * unit)),) * 2, 0)
        _mark(ImageDraw.Draw(mask), unit, 255)
        return mask

    return _ink_layer(render, target / 64.0, target)


def _glyph_alpha(design: Design, side: int) -> Image.Image:
    """The glyph (or the mark), centred, as an alpha mask on a side x side box."""
    target = side * GLYPH_SCALE
    layer = _glyph_layer(design.code, target) if design.code else _mark_layer(target)
    mask = Image.new("L", (side, side), 0)
    mask.paste(layer.getchannel("A"), ((side - layer.width) // 2, (side - layer.height) // 2))
    return mask


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


def icon_png(width: int, height: int, design: Design) -> Image.Image:
    """The free-standing duotone mark, at exactly width x height.

    Colour A carries the glyph, colour B the accent, and their multiply the
    overlap - three opaque colours on transparency, no tile.
    """
    ss = _supersample(width, height)
    w, h = width * ss, height * ss
    side = min(w, h)
    glyph = _glyph_alpha(design, side)
    a = rgb(design.glyph)
    if design.accent:
        b = rgb(design.accent)
        accent = accent_mask(design.shape, side)
        layers = (
            (ImageChops.subtract(accent, glyph), b),
            (ImageChops.subtract(glyph, accent), a),
            (ImageChops.multiply(glyph, accent), multiply(a, b)),
        )
    else:
        layers = ((glyph, a),)
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
    return f'<g transform="{transform}">{MARK_SVG_INNER.format(fg=fill)}</g>'


def _ink_svg(design: Design, fill: str) -> str:
    return _glyph_svg(design.code, fill) if design.code else _mark_svg(fill)


def icon_svg(design: Design) -> str:
    """The same three layers the PNG composites, as vectors.

    Accent in B, glyph in A over it, then the glyph again clipped to the accent
    in the multiply colour - which reproduces exactly what the raster does with
    its intersection mask, without needing a blend mode no SVG renderer owes us.
    """
    side = f"{SVG_SIDE:g}"
    body = _ink_svg(design, design.glyph)
    if design.accent:
        overlap = _hex(multiply(rgb(design.glyph), rgb(design.accent)))
        body = (
            f'<defs><clipPath id="{ACCENT_CLIP_ID}">{_accent_svg(design.shape)}</clipPath></defs>'
            f'{_accent_svg(design.shape, design.accent)}{body}'
            f'<g clip-path="url(#{ACCENT_CLIP_ID})">{_ink_svg(design, overlap)}</g>'
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
        written.extend(_render(png, design_for(module)))
    for stem, design in sorted(BASE_ICONS.items()):
        png = root.joinpath(BASE_DESCRIPTION, f"{stem}.png")
        if png.exists():
            written.extend(_render(png, design))
    return written
