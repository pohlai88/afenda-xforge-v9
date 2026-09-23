"""The human review sheet. A review aid, never a canonical asset.

It reproduces the approved board's own layout so the two can be held side by
side: the five icons across the top, the Accounting size progression beneath,
the construction principle, and the design rules the family is judged against.
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

from .spec import ORDER, SIZES, SPECS

PAPER = (251, 250, 247, 255)
INK = (27, 42, 58)
MUTED = (120, 128, 134)
RULES = ("Clear silhouette", "Controlled translucency", "Distinct xForge geometry",
         "Scales 16-128px", "Consistent across modules")


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def write_contact_sheet(path: pathlib.Path, png_dir: pathlib.Path) -> pathlib.Path:
    """Compose the review sheet from the already-exported PNGs."""
    w, h = 1400, 760
    im = Image.new("RGBA", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    title, label, small = _font(26), _font(15), _font(12)

    d.text((48, 38), "AFENDA xForge", fill=INK, font=title)
    d.text((48, 74), "Application Icon System - Version 3.1", fill=MUTED, font=label)
    d.line((48, 118, w - 48, 118), fill=(226, 224, 216), width=1)

    # the family
    x = 92
    for key in ORDER:
        icon = Image.open(png_dir / f"{key}@128.png").convert("RGBA")
        im.alpha_composite(icon, (x, 150))
        text = SPECS[key].label
        d.text((x + 64 - d.textlength(text, font=label) / 2, 292), text, fill=INK, font=label)
        x += 252

    d.line((48, 340, w - 48, 340), fill=(226, 224, 216), width=1)

    # Accounting size progression - the mandated calibration
    d.text((48, 360), "Accounting - scales", fill=MUTED, font=small)
    x, base = 48, 400
    for size in SIZES:
        icon = Image.open(png_dir / f"accounting@{size}.png").convert("RGBA")
        im.alpha_composite(icon, (x, base + (128 - size)))
        d.text((x, base + 136), f"{size}px", fill=MUTED, font=small)
        x += size + 34

    # construction principle
    cx = 600
    d.text((cx, 360), "Construction principle", fill=MUTED, font=small)
    d.text((cx, 400), "semantic master", fill=INK, font=label)
    d.text((cx, 424), "+  xForge planes through the object", fill=INK, font=label)
    d.text((cx, 448), "+  controlled crossing", fill=INK, font=label)
    d.text((cx, 476), "=  final V3 icon (max 3 planes)", fill=INK, font=label)

    # the rules
    rx = 1010
    d.text((rx, 360), "Design principles", fill=MUTED, font=small)
    for i, rule in enumerate(RULES):
        d.text((rx, 400 + i * 26), f"-  {rule}", fill=INK, font=label)

    d.line((48, h - 76, w - 48, h - 76), fill=(226, 224, 216), width=1)
    d.text((48, h - 58), "Review artifact. SVG is canonical; these PNGs are derived.",
           fill=MUTED, font=small)

    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(path)
    return path
