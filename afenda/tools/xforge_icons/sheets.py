"""Presentation artifacts: contact sheets, a size test and a construction board.

These are review aids. The transparent SVG and PNG files are the deliverable;
nothing here is consumed by the product.
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

from .render import icon_png
from .tokens import (ARTBOARD, FAMILIES, ORDER, SMALL_SIZES, hex_of, mix, rgb)

_REPO = pathlib.Path(__file__).resolve().parents[3]
_FONTS = _REPO / "afenda" / "addons" / "afenda_brand" / "static" / "fonts"

LIGHT = {"bg": (246, 248, 251), "ink": (11, 36, 66), "muted": (110, 124, 142),
         "rule": (222, 228, 236)}
DARK = {"bg": (10, 17, 32), "ink": (233, 251, 255), "muted": (140, 154, 172),
        "rule": (31, 41, 55)}

SCALE_TEST = (128, 64, 32, 24, 16)


def _font(name: str, size: int):
    f = _FONTS / name
    if f.exists():
        try:
            return ImageFont.truetype(str(f), size)
        except OSError:
            pass
    return ImageFont.load_default()


def _fonts(scale=1):
    return (_font("SourceSans3-Semibold.ttf", 34 * scale),
            _font("SourceSans3-Regular.ttf", 19 * scale),
            _font("SourceCodePro-Regular.ttf", 15 * scale) if
            (_FONTS / "SourceCodePro-Regular.ttf").exists()
            else _font("SourceSans3-Regular.ttf", 15 * scale))


def contact_sheet(theme: dict) -> Image.Image:
    title_f, body_f, mono_f = _fonts()
    W, H = 1500, 880
    im = Image.new("RGB", (W, H), theme["bg"])
    d = ImageDraw.Draw(im)

    d.text((64, 56), "Application Icon System — Version 3", font=title_f, fill=theme["ink"])
    d.line([(64, 128), (W - 64, 128)], fill=theme["rule"], width=1)

    # the five, one row
    cell = (W - 128) // 5
    for i, key in enumerate(ORDER):
        fam = FAMILIES[key]
        ic = icon_png(fam, 176)
        x = 64 + i * cell + (cell - 176) // 2
        im.paste(ic, (x, 196), ic)
        w = d.textlength(fam.label, font=body_f)
        d.text((64 + i * cell + (cell - w) / 2, 400), fam.label, font=body_f, fill=theme["ink"])

    d.line([(64, 468), (W - 64, 468)], fill=theme["rule"], width=1)

    # accounting scale test
    d.text((64, 500), "Accounting — scales", font=mono_f, fill=theme["muted"])
    x = 64
    fam = FAMILIES["accounting"]
    for s in SCALE_TEST:
        ic = icon_png(fam, s)
        im.paste(ic, (x, 540 + (128 - s)), ic)
        lab = f"{s}px"
        d.text((x, 690), lab, font=mono_f, fill=theme["muted"])
        x += max(s, 44) + 44

    # construction
    cx = 760
    d.text((cx, 500), "Construction", font=mono_f, fill=theme["muted"])
    d.text((cx, 538), "Semantic shape + xForge geometry + controlled intersection",
           font=body_f, fill=theme["ink"])
    d.text((cx, 580), "Three dominant planes. The crossing colour is precomputed,",
           font=body_f, fill=theme["muted"])
    d.text((cx, 608), "never a blend mode, so SVG and PNG agree everywhere.",
           font=body_f, fill=theme["muted"])
    d.text((cx, 656), "Ribbons at +45° and −45°, 24% of the live area.",
           font=mono_f, fill=theme["muted"])

    d.line([(64, 744), (W - 64, 744)], fill=theme["rule"], width=1)
    d.text((64, 768), "AFENDA xForge", font=body_f, fill=theme["muted"])
    return im


def size_test() -> Image.Image:
    title_f, body_f, mono_f = _fonts()
    sizes = (16, 24, 32, 48, 64, 128)
    W = 200 + len(sizes) * 168
    H = 160 + len(ORDER) * 168
    im = Image.new("RGB", (W, H), LIGHT["bg"])
    d = ImageDraw.Draw(im)
    d.text((48, 44), "Version 3 — size test", font=title_f, fill=LIGHT["ink"])
    for j, s in enumerate(sizes):
        d.text((208 + j * 168, 112), f"{s}px", font=mono_f, fill=LIGHT["muted"])
    for i, key in enumerate(ORDER):
        fam = FAMILIES[key]
        y = 148 + i * 168
        d.text((48, y + 60), fam.label, font=body_f, fill=LIGHT["ink"])
        for j, s in enumerate(sizes):
            ic = icon_png(fam, s)
            im.paste(ic, (208 + j * 168 + (128 - s) // 2, y + (128 - s) // 2), ic)
    return im


def construction_board() -> Image.Image:
    """Semantic shape, then the ribbons, then the finished icon."""
    from . import geometry as G
    from .render import path_mask

    title_f, body_f, mono_f = _fonts()
    W, H = 1180, 560
    im = Image.new("RGB", (W, H), LIGHT["bg"])
    d = ImageDraw.Draw(im)
    d.text((48, 44), "Construction — Accounting", font=title_f, fill=LIGHT["ink"])

    fam = FAMILIES["accounting"]
    art = G.BUILDERS["accounting"](False)
    S = 232

    def grey(mask, shade=(176, 186, 200)):
        layer = Image.new("RGBA", (S, S), shade + (0,))
        layer.putalpha(mask)
        return layer

    body = path_mask(art["body"], S)
    r1d, r2d = G.ribbons(art["ribbon_offsets"], art["ribbon_width"])
    steps = [
        ("1. Semantic shape", grey(body)),
        ("2. xForge geometry", grey(ImageChops_lighter(path_mask(r1d, S), path_mask(r2d, S)),
                                    (150, 162, 180))),
        ("3. Controlled intersection", icon_png(fam, S)),
    ]
    x = 48
    for i, (label, img) in enumerate(steps):
        im.paste(img, (x, 150), img)
        d.text((x, 410), label, font=body_f, fill=LIGHT["ink"])
        if i < 2:
            d.text((x + S + 34, 250), "+" if i == 0 else "=", font=title_f, fill=LIGHT["muted"])
        x += S + 110
    d.text((48, 470), "Semantic shape + xForge geometry + controlled intersection",
           font=mono_f, fill=LIGHT["muted"])
    return im


def ImageChops_lighter(a, b):
    from PIL import ImageChops
    return ImageChops.lighter(a, b)
