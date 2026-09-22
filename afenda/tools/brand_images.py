"""Render AFENDA images over the paths where Odoo ships its own logos.

Keeping Odoo's file names means the 300 templates that reference them
need no change. Run after the rebrand script:
    python -m afenda.tools.brand_images
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BLUE = (30, 58, 138)
INK = (15, 23, 42)
PAPER = (247, 247, 245)
WHITE = (255, 255, 255)
SS = 8  # supersampling factor

FONTS = Path(__file__).resolve().parents[1] / "addons" / "afenda_brand" / "static" / "fonts"

# repo-relative path -> kind
TARGETS: dict[str, str] = {
    "addons/web/static/img/favicon.ico": "tile_ico",
    "addons/web/static/img/odoo-icon-192x192.png": "tile_png",
    "addons/web/static/img/odoo-icon-512x512.png": "tile_png",
    "addons/web/static/img/odoo-icon-ios.png": "tile_png",
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

SIZES: dict[str, tuple[int, int]] = {
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

# Alpha kept by the report background watermark (Odoo ships its own at 25/255).
WATERMARK_OPACITY = 0.12

MARK_SVG_INNER = (
    '<path d="M32 12 L50 42 H41 L32 27 L23 42 H14 Z" fill="{fg}" stroke="{fg}" stroke-width="2.5" stroke-linejoin="round"/>'
    '<rect x="14" y="46" width="36" height="4" rx="2" fill="{fg}"/>'
    '<rect x="14" y="52" width="36" height="4" rx="2" fill="{fg}"/>'
)


def tile_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#1E3A8A"/>' + MARK_SVG_INNER.format(fg="#FFFFFF") + "</svg>\n"
    )


def lockup_svg(ink: str, sub: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="80" viewBox="0 0 360 80">'
        '<g transform="translate(8 8)"><rect width="64" height="64" rx="12" fill="#1E3A8A"/>'
        + MARK_SVG_INNER.format(fg="#FFFFFF")
        + "</g>"
        f'<text x="90" y="46" font-family="\'Source Serif 4\', Georgia, serif" font-weight="600" font-size="36" letter-spacing="1.8" fill="{ink}">AFENDA</text>'
        f'<text x="90" y="70" font-family="\'Source Sans 3\', Arial, sans-serif" font-weight="500" font-size="20" fill="{sub}">xForge</text>'
        "</svg>\n"
    )


def _rounded(d: ImageDraw.ImageDraw, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def _mark(d: ImageDraw.ImageDraw, s: float, fg, box_mark=True):
    pts = [(32, 12), (50, 42), (41, 42), (32, 27), (23, 42), (14, 42)] if box_mark else [(32, 2), (56, 46), (44, 46), (32, 24), (20, 46), (8, 46)]
    d.polygon([(x * s, y * s) for x, y in pts], fill=fg)
    if box_mark:
        _rounded(d, (14 * s, 46 * s, 50 * s, 50 * s), 2 * s, fg)
        _rounded(d, (14 * s, 52 * s, 50 * s, 56 * s), 2 * s, fg)
    else:
        _rounded(d, (6 * s, 50 * s, 58 * s, 55 * s), 2.5 * s, fg)
        _rounded(d, (6 * s, 58 * s, 58 * s, 63 * s), 2.5 * s, fg)


def tile_png(size: int) -> Image.Image:
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _rounded(d, (0, 0, big - 1, big - 1), big * 12 / 64, BLUE)
    _mark(d, big / 64, WHITE)
    return im.resize((size, size), Image.LANCZOS)


def mark_png(size: int, fg=BLUE) -> Image.Image:
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    _mark(ImageDraw.Draw(im), big / 64, fg, box_mark=False)
    return im.resize((size, size), Image.LANCZOS)


def _solid(im: Image.Image, rgb) -> Image.Image:
    """Force every pixel to one colour, keeping the alpha channel.

    Resampling an RGBA image blends colour into fully transparent pixels, which
    leaves a grey fringe on a white-on-dark lockup. Flattening the colour first
    keeps the edge white and the shape in the alpha channel.
    """
    out = Image.new("RGBA", im.size, tuple(rgb) + (0,))
    out.putalpha(im.getchannel("A"))
    return out


def blank_jpg(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), WHITE)


def _font(name: str, size: int, **axes) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    ax = f.get_variation_axes()
    names = [a["name"].decode() if isinstance(a["name"], bytes) else a["name"] for a in ax]
    f.set_variation_by_axes([axes.get(n, a["default"]) for a, n in zip(ax, names)])
    return f


def lockup_png(width: int, height: int, ink=INK, sub=BLUE, mark_fill=None) -> Image.Image:
    """Fit the AFENDA lockup into width x height on a transparent canvas.

    ``mark_fill=None`` draws the blue tile with a white mark; a colour draws the
    bare mark in that colour with no tile behind it.
    """
    W, H, S = 1200, 300, 4
    im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    glyph = tile_png(220 * S) if mark_fill is None else mark_png(220 * S, mark_fill)
    im.alpha_composite(glyph, (40 * S, 40 * S))
    serif = _font("SourceSerif4-VF.ttf", 150 * S, **{"Optical Size": 60, "Weight": 600})
    sans = _font("SourceSans3-VF.ttf", 78 * S, **{"Weight": 500})
    x = cx = 300 * S
    for ch in "AFENDA":
        d.text((cx, 62 * S), ch, font=serif, fill=ink)
        cx += d.textlength(ch, font=serif) + 4 * S
    d.text((x + 4 * S, 200 * S), "xForge", font=sans, fill=sub)
    im = im.resize((W, H), Image.LANCZOS)
    # Fit into the requested box, centered, keeping aspect ratio.
    scale = min(width / W, height / H)
    inner = im.resize((max(1, int(W * scale)), max(1, int(H * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(inner, ((width - inner.width) // 2, (height - inner.height) // 2))
    return canvas


def lockup_white_png(width: int, height: int) -> Image.Image:
    """Lockup for dark backgrounds: white wordmark, white mark, no tile."""
    # mark_fill is the load-bearing argument: it is what suppresses the blue tile,
    # and _solid cannot undo a tile once drawn. ink and sub only keep the
    # pre-flatten render honest, since _solid overwrites every RGB value.
    return _solid(lockup_png(width, height, ink=WHITE, sub=WHITE, mark_fill=WHITE), WHITE)


def lockup_faint_png(width: int, height: int, opacity: float = WATERMARK_OPACITY) -> Image.Image:
    """The standard lockup dimmed to a page-background watermark."""
    im = lockup_png(width, height)
    im.putalpha(im.getchannel("A").point(lambda v: int(v * opacity)))
    return im


def render_all(root: Path) -> list[Path]:
    written: list[Path] = []
    for rel, kind in TARGETS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "tile_svg":
            path.write_text(tile_svg(), encoding="utf-8")
        elif kind == "lockup_svg":
            path.write_text(lockup_svg("#0F172A", "#1E3A8A"), encoding="utf-8")
        elif kind == "lockup_dark_svg":
            path.write_text(lockup_svg("#F7F7F5", "#A5B4FC"), encoding="utf-8")
        elif kind == "tile_ico":
            tile_png(64).save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        elif kind == "tile_png":
            w, h = SIZES[rel]
            tile_png(w).save(path)
        elif kind == "mark_png":
            w, h = SIZES[rel]
            mark_png(w).save(path)
        elif kind == "lockup_png":
            w, h = SIZES[rel]
            lockup_png(w, h).save(path)
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
    # module's mark and tile, so a top-level import would be circular.
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
