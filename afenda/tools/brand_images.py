"""Render AFENDA images over the paths where Odoo ships its own logos.

Keeping Odoo's file names means the 300 templates that reference them
need no change. Run after the rebrand script:
    python -m afenda.tools.brand_images

Everything drawn here comes from two declarations and nothing else: the
Engineered X's geometry (``MARK_ARMS``) and the three approved colourways
(``PRIMARY``, ``LIGHT``, ``IN_PRODUCT``). Which surface gets which colourway is
the ``TARGETS`` table's job and only its job -- see "The usage contract" below.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

WHITE = (255, 255, 255)
SS = 8  # supersampling factor

# Renderer input, deliberately NOT under afenda_brand/static/: Odoo serves that
# tree over HTTP whatever the manifest says, so a typeface left there is
# reachable at a URL and ships in every deployment. The lockup bakes the
# wordmark to outlines, so nothing downstream needs the face either. See
# fonts/README.md.
FONTS = Path(__file__).resolve().parent / "fonts"


# ---------------------------------------------------------------------------
# The Engineered X
# ---------------------------------------------------------------------------
# Two halves meeting at a diamond void, four tapered wedges each ending in one
# flat cut. These are the identity's own coordinates, transcribed from the
# signed-off artwork without reprojection: a 100-unit frame, ink box 23..77
# square (54% occupancy), each wedge 16.8 wide at the frame and sqrt(18) at the
# tip, symmetric about both diagonals. Every renderer below scales THIS tuple;
# there is no second copy of the shape anywhere in the repo, and the tests in
# MarkGeometryTests pin the numbers against a second hand transcription.
MARK_FRAME = 100.0
MARK_ARMS: tuple[tuple[tuple[float, float], ...], ...] = (
    ((23, 23), (39.8, 23), (49.25, 46.25), (46.25, 49.25)),  # NW
    ((23, 77), (39.8, 77), (49.25, 53.75), (46.25, 50.75)),  # SW
    ((77, 23), (60.2, 23), (50.75, 46.25), (53.75, 49.25)),  # NE
    ((77, 77), (60.2, 77), (50.75, 53.75), (53.75, 50.75)),  # SE
)
MARK_BOX = (23.0, 23.0, 77.0, 77.0)  # the wedges' extent; they carry no stroke
MARK_SIDE = MARK_BOX[2] - MARK_BOX[0]

# How much of a square the mark's ink occupies. Boxed is the artwork's own
# 54% inside a tile; bare is the larger free-standing size used where there is
# no tile to sit in.
BOXED_INK = 0.54
BARE_INK = 0.75


def arms_at(side: float, x: float = 0.0, y: float = 0.0):
    """``MARK_ARMS`` with its ink box scaled to ``side`` and placed at ``x, y``."""
    s = side / MARK_SIDE
    return tuple(
        tuple(((px - MARK_BOX[0]) * s + x, (py - MARK_BOX[1]) * s + y) for px, py in arm)
        for arm in MARK_ARMS
    )


def arms_in(frame: float, ink: float):
    """``MARK_ARMS`` centred in a ``frame``-unit square at ``ink`` occupancy."""
    side = frame * ink
    return arms_at(side, (frame - side) / 2, (frame - side) / 2)


# ---------------------------------------------------------------------------
# The colourways
# ---------------------------------------------------------------------------
class Colourway(NamedTuple):
    """One approved rendering of the badge: a ground, four fills, a radius.

    ``fills`` is per wedge in ``MARK_ARMS`` order -- NW, SW, NE, SE -- which is
    what makes the mark two-tone: the western half steps one value, the eastern
    half steps another, each pair ~13.5 dE apart so the taper reads at 16px.
    """

    ground: str
    fills: tuple[str, str, str, str]
    radius: float  # corner radius as a share of the tile's side
    edge: str | None = None  # hairline, where the ground is too pale to end itself


class Wordmark(NamedTuple):
    """The three colours the lockup's typography takes."""

    label: str  # AFENDA, the small tracked line
    accent: str  # the x of xForge
    word: str  # Forge


# The badge as it stands on its own ground: app icon, store listing, install
# icon, login. Signal Blue east, steel west, on near-black.
PRIMARY = Colourway("#09111F", ("#D9DEE5", "#AAB3C0", "#659CFF", "#1F6FFF"), 0.225)

# The same badge where the surface underneath is already white and a dark tile
# would read as a sticker. The hairline is what ends the tile.
LIGHT = Colourway("#FFFFFF", ("#6C7581", "#464F5A", "#1F6FFF", "#0049C1"), 0.225, edge="#E3E8EF")

# Inside the product. One fill, on Ledger Blue -- the UI's own blue, so the
# chrome does not carry a second brand colour. Tighter radius than the badge.
IN_PRODUCT = Colourway("#1E3A8A", ("#FFFFFF",) * 4, 0.20)

# Wordmark pairings. The dark one is the artwork's; the light one transposes it
# for paper (report headers, the company logo) by swapping the two neutrals for
# their light-ground equivalents and leaving the accent alone, exactly as LIGHT
# does for the wedges.
PRIMARY_WORD = Wordmark(label="#94A3B8", accent="#1F6FFF", word="#FFFFFF")
LIGHT_WORD = Wordmark(label="#4B5563", accent="#1F6FFF", word="#0F172A")

# The bare mark on transparency, where there is no ground to hold a two-tone
# step -- a four-fill mark on an unknown background is not a mark, it is a
# gradient. Ledger Blue, one fill.
BARE_FILL = "#1E3A8A"


# ---------------------------------------------------------------------------
# The lockup
# ---------------------------------------------------------------------------
# Metrics transcribed from the artwork's 430x136 lockup: a free-standing mark
# inset 24 with an 88-unit ink box, the tracked label on the 58 baseline and the
# wordmark on the 104 baseline, both starting at x=140.
LOCKUP_HEIGHT = 136.0
LOCKUP_MARGIN = 24.0  # the inset the mark, the cap line and the baseline all sit on
LOCKUP_MARK = (24.0, 24.0, 88.0)  # x, y, ink side
LOCKUP_TEXT_X = 140.0
LABEL = ("Geist-Medium.ttf", 15.0, 3.3, 58.0)  # font, size, tracking, baseline
WORD = ("Geist-Semibold.ttf", 54.0, -1.62, 104.0)

# Alpha kept by the report background watermark (Odoo ships its own at 25/255).
WATERMARK_OPACITY = 0.12


# ---------------------------------------------------------------------------
# The usage contract
# ---------------------------------------------------------------------------
# Every generated file names the colourway it is allowed to carry, once, here.
#
#   badge_*   PRIMARY. Surfaces that stand outside the running application and
#             answer to nobody: the installed PWA and home-screen icons, the
#             store listing, the addon's own icon set.
#   tile_*    IN_PRODUCT. Anything a signed-in user sees while working -- the
#             browser tab, the apps menu, the bot avatar, report artwork. The
#             artwork is explicit that the two-tone mark never has to survive a
#             16px favicon, so the favicon is in-product, not badge.
#   mark_*    BARE_FILL on transparency, no tile.
#   lockup_*  The mark plus the wordmark; light for paper, dark for dark ground.
TARGETS: dict[str, str] = {
    "addons/web/static/img/favicon.ico": "tile_ico",
    "addons/web/static/img/odoo-icon-192x192.png": "badge_png",
    "addons/web/static/img/odoo-icon-512x512.png": "badge_png",
    "addons/web/static/img/odoo-icon-ios.png": "badge_png",
    "addons/web/static/img/odoo-icon.svg": "tile_svg",
    "addons/web/static/img/odoo_logo.svg": "lockup_svg",
    "addons/web/static/img/odoo_logo_dark.svg": "lockup_dark_svg",
    "addons/web/static/img/odoo_logo_tiny.png": "lockup_png",
    "addons/web/static/img/logo.png": "lockup_png",
    "addons/web/static/img/logo2.png": "lockup_png",
    "addons/mail/static/src/img/odoobot.png": "tile_png",
    "addons/mail/static/src/img/odoobot_transparent.png": "mark_png",
    "addons/mail/static/src/img/odoo_o.png": "mark_png",
    "addons/account/static/src/img/Odoo_logo_O.svg": "tile_svg",
    "odoo/addons/base/static/img/res_company_logo.png": "lockup_png",
    "addons/web/static/img/nologo.png": "lockup_png",
    "addons/web/static/img/logo_inverse_white_206px.png": "lockup_white_png",
    "addons/web/static/img/default_icon_app.png": "tile_png",
    "addons/web/static/img/enterprise_upgrade.jpg": "blank_jpg",
    "odoo/addons/base/static/img/logo_white.png": "lockup_white_png",
    "odoo/addons/base/static/img/demo_logo_report.png": "lockup_faint_png",
}

# afenda_brand's own assets. These are not upstream paths, so they were never
# in TARGETS -- and nothing else generated them either, so they sat at whatever
# an earlier identity pass left on disk while every upstream surface moved on.
# Two of them are load-bearing: logo.png is the res.company.logo default
# (models/res_company.py) and favicon.ico is the hard fallback in
# views/webclient_templates.xml. Wired here so the next mark change reaches
# them without anyone remembering to.
#
# The icon set is the addon's badge -- it is what hooks.py hands to the web
# manifest as pwa_icon -- so it takes PRIMARY. The favicon beside it stays
# in-product for the same reason the upstream one does.
ADDON: str = "afenda/addons/afenda_brand/static"
ADDON_TARGETS: dict[str, str] = {
    f"{ADDON}/img/logo.png": "lockup_png",
    f"{ADDON}/img/logo_dark.png": "lockup_dark_png",
    f"{ADDON}/img/logo_email_2x.png": "lockup_png",
    f"{ADDON}/img/favicon.ico": "tile_ico",
    f"{ADDON}/img/mark.png": "mark_png",
    f"{ADDON}/img/icon.png": "badge_png",
    f"{ADDON}/description/icon.png": "badge_png",
    **{f"{ADDON}/img/icon-{n}.png": "badge_png" for n in (16, 32, 48, 64, 128, 192, 256, 512)},
}

SIZES: dict[str, tuple[int, int]] = {
    f"{ADDON}/img/logo.png": (1200, 300),
    f"{ADDON}/img/logo_dark.png": (1200, 300),
    f"{ADDON}/img/logo_email_2x.png": (128, 32),
    f"{ADDON}/img/mark.png": (512, 512),
    f"{ADDON}/img/icon.png": (512, 512),
    f"{ADDON}/description/icon.png": (512, 512),
    **{f"{ADDON}/img/icon-{n}.png": (n, n) for n in (16, 32, 48, 64, 128, 192, 256, 512)},
    "addons/web/static/img/odoo-icon-192x192.png": (192, 192),
    "addons/web/static/img/odoo-icon-512x512.png": (512, 512),
    "addons/web/static/img/odoo-icon-ios.png": (512, 512),
    "addons/web/static/img/odoo_logo_tiny.png": (186, 60),  # Odoo ships 62x20; 3x for retina, templates set height 1em
    "addons/web/static/img/logo.png": (180, 79),
    "addons/web/static/img/logo2.png": (300, 131),
    "addons/mail/static/src/img/odoobot.png": (512, 512),
    "addons/mail/static/src/img/odoobot_transparent.png": (512, 512),
    "addons/mail/static/src/img/odoo_o.png": (100, 100),
    "odoo/addons/base/static/img/res_company_logo.png": (450, 120),
    "addons/web/static/img/nologo.png": (180, 79),
    "addons/web/static/img/logo_inverse_white_206px.png": (627, 206),
    "addons/web/static/img/default_icon_app.png": (180, 180),
    # Nothing references this upstream screenshot, but keep its real dimensions:
    # a blank JPEG this size is a few KB, and any consumer an upstream merge adds
    # later gets the box it expects instead of a silently stretched pixel.
    "addons/web/static/img/enterprise_upgrade.jpg": (2378, 1306),
    "odoo/addons/base/static/img/logo_white.png": (600, 194),
    "odoo/addons/base/static/img/demo_logo_report.png": (621, 196),
}

# kind -> the colourway it is contracted to. Read by the tests, which is how a
# surface cannot quietly change which mark it carries.
CONTRACT: dict[str, Colourway] = {
    "badge_png": PRIMARY,
    "tile_png": IN_PRODUCT,
    "tile_ico": IN_PRODUCT,
    "tile_svg": IN_PRODUCT,
}


def rgb(colour: str) -> tuple[int, int, int]:
    """``"#1E3A8A"`` -> ``(30, 58, 138)``."""
    h = colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Drawing the mark
# ---------------------------------------------------------------------------
def mark_svg(fills: tuple[str, str, str, str]) -> str:
    """The four wedges as SVG paths, in the artwork's own 100-unit frame."""
    return "".join(
        '<path d="M {} Z" fill="{}"/>'.format(" L ".join(f"{x:g} {y:g}" for x, y in arm), fill)
        for arm, fill in zip(MARK_ARMS, fills)
    )


def draw_mark(d: ImageDraw.ImageDraw, arms, fills) -> None:
    """Fill ``arms`` (from ``arms_at``) with ``fills``, wedge for wedge."""
    for arm, fill in zip(arms, fills):
        d.polygon(list(arm), fill=fill)


def tile_svg(cw: Colourway = IN_PRODUCT) -> str:
    edge = f' stroke="{cw.edge}"' if cw.edge else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
        f'<rect width="100" height="100" rx="{cw.radius * 100:g}" fill="{cw.ground}"{edge}/>'
        + mark_svg(cw.fills)
        + "</svg>\n"
    )


def tile_png(size: int, cw: Colourway = IN_PRODUCT) -> Image.Image:
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(
        (0, 0, big - 1, big - 1),
        radius=big * cw.radius,
        fill=rgb(cw.ground),
        outline=rgb(cw.edge) if cw.edge else None,
        width=max(1, round(big / MARK_FRAME)),
    )
    draw_mark(d, arms_in(big, BOXED_INK), [rgb(f) for f in cw.fills])
    return im.resize((size, size), Image.LANCZOS)


def mark_png(size: int, fill: str = BARE_FILL) -> Image.Image:
    """The mark alone on transparency, one fill, at the free-standing size."""
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw_mark(ImageDraw.Draw(im), arms_in(big, BARE_INK), [rgb(fill)] * 4)
    return im.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Drawing the wordmark
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _ttf(name: str) -> TTFont:
    return TTFont(str(FONTS / name))


def _run(text: str, name: str, size: float, tracking: float):
    """``(glyph name, pen x)`` per character, from advance widths plus tracking.

    Deliberately no kerning: the PNG draws character by character and the SVG
    places outlines at these same offsets, so both renderers agree to the pixel.
    At +3.3 on six capitals and -1.62 on a six-letter wordmark, tracking is the
    fit; kern pairs would only make the two paths disagree.
    """
    font = _ttf(name)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    out, x = [], 0.0
    for ch in text:
        glyph = cmap[ord(ch)]
        out.append((ch, glyph, x))
        x += hmtx[glyph][0] * size / upem + tracking
    return out


def _text_svg(text, spec, x: float, y: float, colours) -> str:
    """One text run as outlines, so the lockup needs no font at display time."""
    name, size, tracking, _ = spec
    font = _ttf(name)
    glyphs = font.getGlyphSet()
    s = size / font["head"].unitsPerEm
    parts = []
    for (ch, glyph, dx), fill in zip(_run(text, name, size, tracking), colours):
        pen = SVGPathPen(glyphs)
        glyphs[glyph].draw(pen)
        d = pen.getCommands()
        if not d:  # a space has no outline
            continue
        # The font's y axis points up and SVG's points down, hence -s.
        parts.append(
            f'<path d="{d}" fill="{fill}" '
            f'transform="translate({x + dx:g} {y:g}) scale({s:.6g} {-s:.6g})"/>'
        )
    return "".join(parts)


def _text_png(d: ImageDraw.ImageDraw, text, spec, x: float, y: float, colours, scale: float):
    name, size, tracking, _ = spec
    font = ImageFont.truetype(str(FONTS / name), max(1, round(size * scale)))
    for (ch, _glyph, dx), fill in zip(_run(text, name, size, tracking), colours):
        d.text(((x + dx) * scale, y * scale), ch, font=font, fill=rgb(fill), anchor="ls")


def _wordmark_colours(wm: Wordmark) -> list[str]:
    """xForge: the x carries the accent, Forge carries the word colour."""
    return [wm.accent] + [wm.word] * 5


def _advance(text: str, spec) -> float:
    """Where the pen ends after ``text``, tracking on the last glyph removed."""
    name, size, tracking, _ = spec
    ch, glyph, x = _run(text, name, size, tracking)[-1]
    return x + _ttf(name)["hmtx"][glyph][0] * size / _ttf(name)["head"].unitsPerEm


def lockup_size() -> tuple[float, float]:
    """The artwork's canvas, with its right margin made to match its left.

    The signed-off SVG is 430 wide but its ink stops around 316: the remainder
    is the artboard the wordmark was drawn on, not part of the lockup. Every
    raster target centres this canvas inside a fixed box, so shipping ~110
    units of empty artboard would shrink the logo on every surface it lands on
    and push it off-centre. The margin, the 24-inset mark, both baselines and
    the gap to the text are the artwork's own and are untouched; only the slack
    to the right of the wordmark is trimmed, and it is measured rather than
    typed so a change of wording stays correctly framed.
    """
    ink = max(_advance("AFENDA", LABEL), _advance("xForge", WORD))
    return LOCKUP_TEXT_X + ink + LOCKUP_MARGIN, LOCKUP_HEIGHT


# ---------------------------------------------------------------------------
# Drawing the lockup
# ---------------------------------------------------------------------------
def lockup_svg(cw: Colourway = LIGHT, wm: Wordmark = LIGHT_WORD) -> str:
    """The mark plus the wordmark, at the artwork's metrics, on transparency."""
    w, h = lockup_size()
    mx, my, side = LOCKUP_MARK
    arms = arms_at(side, mx, my)
    mark = "".join(
        '<path d="M {} Z" fill="{}"/>'.format(" L ".join(f"{x:g} {y:g}" for x, y in arm), fill)
        for arm, fill in zip(arms, cw.fills)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" '
        f'viewBox="0 0 {w:g} {h:g}">'
        + mark
        + _text_svg("AFENDA", LABEL, LOCKUP_TEXT_X, LABEL[3], [wm.label] * 6)
        + _text_svg("xForge", WORD, LOCKUP_TEXT_X, WORD[3], _wordmark_colours(wm))
        + "</svg>\n"
    )


def _lockup(cw: Colourway, wm: Wordmark, mark_fill: str | None = None) -> Image.Image:
    """The lockup at 4x the artwork's metrics, on transparency."""
    s = 4
    w, h = lockup_size()
    mx, my, side = LOCKUP_MARK
    im = Image.new("RGBA", (round(w * s), round(h * s)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fills = [rgb(mark_fill)] * 4 if mark_fill else [rgb(f) for f in cw.fills]
    draw_mark(d, arms_at(side * s, mx * s, my * s), fills)
    _text_png(d, "AFENDA", LABEL, LOCKUP_TEXT_X, LABEL[3], [wm.label] * 6, s)
    _text_png(d, "xForge", WORD, LOCKUP_TEXT_X, WORD[3], _wordmark_colours(wm), s)
    return im


def _fit(im: Image.Image, width: int, height: int) -> Image.Image:
    """Centre ``im`` in width x height, keeping its aspect ratio."""
    scale = min(width / im.width, height / im.height)
    inner = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(inner, ((width - inner.width) // 2, (height - inner.height) // 2))
    return canvas


def lockup_png(width: int, height: int) -> Image.Image:
    """The lockup for paper and light chrome: ink wordmark, light-ground wedges."""
    return _fit(_lockup(LIGHT, LIGHT_WORD), width, height)


def lockup_dark_png(width: int, height: int) -> Image.Image:
    """The lockup for a dark ground: white wordmark, the primary two-tone wedges."""
    return _fit(_lockup(PRIMARY, PRIMARY_WORD), width, height)


def _solid(im: Image.Image, rgb) -> Image.Image:
    """Force every pixel to one colour, keeping the alpha channel.

    Resampling an RGBA image blends colour into fully transparent pixels, which
    leaves a grey fringe on a white-on-dark lockup. Flattening the colour first
    keeps the edge white and the shape in the alpha channel.
    """
    out = Image.new("RGBA", im.size, tuple(rgb) + (0,))
    out.putalpha(im.getchannel("A"))
    return out


def lockup_white_png(width: int, height: int) -> Image.Image:
    """The lockup for surfaces that cannot carry colour at all: white throughout.

    Rendering it white first keeps the pre-flatten edges honest; _solid then
    overwrites every RGB value, so the two-tone step is gone by construction
    rather than by luck.
    """
    white = Wordmark(label="#FFFFFF", accent="#FFFFFF", word="#FFFFFF")
    return _solid(_fit(_lockup(LIGHT, white, mark_fill="#FFFFFF"), width, height), WHITE)


def lockup_faint_png(width: int, height: int, opacity: float = WATERMARK_OPACITY) -> Image.Image:
    """The standard lockup dimmed to a page-background watermark."""
    im = lockup_png(width, height)
    im.putalpha(im.getchannel("A").point(lambda v: int(v * opacity)))
    return im


def blank_jpg(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), WHITE)


# ---------------------------------------------------------------------------
def render_all(root: Path) -> list[Path]:
    written: list[Path] = []
    for rel, kind in {**TARGETS, **ADDON_TARGETS}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "tile_svg":
            path.write_text(tile_svg(CONTRACT[kind]), encoding="utf-8")
        elif kind == "lockup_svg":
            path.write_text(lockup_svg(LIGHT, LIGHT_WORD), encoding="utf-8")
        elif kind == "lockup_dark_svg":
            path.write_text(lockup_svg(PRIMARY, PRIMARY_WORD), encoding="utf-8")
        elif kind == "tile_ico":
            tile_png(64, CONTRACT[kind]).save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        elif kind in ("tile_png", "badge_png"):
            w, h = SIZES[rel]
            tile_png(w, CONTRACT[kind]).save(path)
        elif kind == "mark_png":
            w, h = SIZES[rel]
            mark_png(w).save(path)
        elif kind == "lockup_png":
            w, h = SIZES[rel]
            lockup_png(w, h).save(path)
        elif kind == "lockup_dark_png":
            w, h = SIZES[rel]
            lockup_dark_png(w, h).save(path)
        elif kind == "lockup_white_png":
            w, h = SIZES[rel]
            lockup_white_png(w, h).save(path)
        elif kind == "lockup_faint_png":
            w, h = SIZES[rel]
            lockup_faint_png(w, h).save(path)
        elif kind == "blank_jpg":
            w, h = SIZES[rel]
            blank_jpg(w, h).save(path, quality=95)
        else:
            raise ValueError(kind)
        written.append(path)
    # Imported here rather than at module level: app_icons builds on this
    # module's mark, so a top-level import would be circular.
    from . import app_icons

    written.extend(app_icons.render_all(root))
    return written


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    for p in render_all(root):
        print(p.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
