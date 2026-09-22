"""Render an AFENDA app icon over every module icon Odoo ships.

Odoo's 108 module icons are the most visible Odoo artwork left once the logos
are replaced: they fill the apps menu. This redraws each one as a rounded
AFENDA tile with a white FontAwesome glyph, keeping the upstream file name and
pixel size so no manifest, template or menu record has to change.

Modules with no glyph mapping get the AFENDA mark on a graphite tile, so the
technical plumbing recedes behind the real apps.

Run through the image renderer, which calls in here:
    python -m afenda.tools.brand_images
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from .brand_images import BLUE, MARK_SVG_INNER, SS, WHITE, _mark, _rounded

GRAPHITE = (75, 85, 99)
HEX = {BLUE: "#1E3A8A", GRAPHITE: "#4B5563"}

CORNER_RADIUS = 0.20  # of the tile's short side
GLYPH_SCALE = 0.52  # the glyph's longer dimension, as a share of the short side
SVG_SIDE = 50.0  # every upstream icon.svg is viewBox="0 0 50 50"
MAX_SUPERSAMPLED = 1024  # a few module icons are thousands of pixels wide

_REPO = Path(__file__).resolve().parents[2]
FA_TTF = str(_REPO / "addons" / "web" / "static" / "src" / "libs" / "fontawesome" / "fonts" / "fontawesome-webfont.ttf")

# MARK_SVG_INNER draws in brand_images' 64x64 tile space. This is its ink box
# there, including the 2.5-wide stroke around the A: x 14..50 and y 12..56.
MARK_SVG_BOX = (12.75, 10.75, 51.25, 56.0)

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
    "spreadsheet_dashboard": "f0ce",
    "utm": "f0e8",
    "base": "f013",
    "web": "f009",
}


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


def _centre(im: Image.Image, layer: Image.Image) -> None:
    im.alpha_composite(layer, ((im.width - layer.width) // 2, (im.height - layer.height) // 2))


def icon_png(width: int, height: int, code: str | None) -> Image.Image:
    """A rounded brand tile with a white glyph, at exactly width x height."""
    ss = _supersample(width, height)
    w, h = width * ss, height * ss
    side = min(w, h)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    _rounded(draw, (0, 0, w - 1, h - 1), side * CORNER_RADIUS, BLUE if code else GRAPHITE)
    target = side * GLYPH_SCALE
    _centre(im, _glyph_layer(code, target) if code else _mark_layer(target))
    return im if ss == 1 else im.resize((width, height), Image.LANCZOS)


def _glyph_svg(code: str) -> str:
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
    return f'<path d="{pen.getCommands()}" fill="#FFFFFF" transform="{transform}"/>'


def _mark_svg() -> str:
    x0, y0, x1, y1 = MARK_SVG_BOX
    scale = SVG_SIDE * GLYPH_SCALE / max(x1 - x0, y1 - y0)
    half = SVG_SIDE / 2
    transform = (
        f"translate({half:g} {half:g}) scale({scale:.5g}) "
        f"translate({-(x0 + x1) / 2:.5g} {-(y0 + y1) / 2:.5g})"
    )
    return f'<g transform="{transform}">{MARK_SVG_INNER.format(fg="#FFFFFF")}</g>'


def icon_svg(code: str | None) -> str:
    side = f"{SVG_SIDE:g}"
    radius = f"{SVG_SIDE * CORNER_RADIUS:g}"
    fill = HEX[BLUE if code else GRAPHITE]
    inner = _glyph_svg(code) if code else _mark_svg()
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" viewBox="0 0 {side} {side}">'
        f'<rect width="{side}" height="{side}" rx="{radius}" fill="{fill}"/>{inner}</svg>\n'
    )


def render_all(root: Path) -> list[Path]:
    """Redraw every module icon under ``root``; never create one upstream lacks."""
    written: list[Path] = []
    for png in sorted(root.glob("addons/*/static/description/icon.png")):
        module = png.parents[2].name
        code = APP_GLYPHS.get(module)
        with Image.open(png) as src:
            size = src.size
        icon_png(size[0], size[1], code).save(png)
        written.append(png)
        svg = png.with_suffix(".svg")
        if svg.exists():
            svg.write_text(icon_svg(code), encoding="utf-8")
            written.append(svg)
    return written
