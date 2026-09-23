"""SVG emission and deterministic rasterising for the xForge V3 icons.

SVG is the canonical source. The PNG path rasterises the *same* geometry dict
the SVG is written from, so the two cannot drift; ``test_xforge_icons`` pins
that by checking every path in the SVG against the geometry it came from.

Composition, in the specification's terms:

    plane 1  body minus the ribbons          base gradient
    plane 2  body meet ribbons, minus their  ribbon gradient
             own crossing
    plane 3  body meet ribbon meet ribbon    the deliberate intersection colour

Three dominant planes, by construction rather than by discipline. The
intersection colour is precomputed and written literally into the SVG, so no
export depends on ``mix-blend-mode`` or on the renderer's blending.
"""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter
from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path import parse_path

from . import geometry as G
from .material import (GLOSS_ALPHA, GLOSS_END, LIGHT_ANGLE, crystal, gloss,
                       gloss_layer, paint_gradient)
from .tokens import ICE_HIGHLIGHT
from .tokens import (ARTBOARD, INK_NAVY, RENDERER_VERSION, RIBBON_ALPHA,
                     SHADOW_THRESHOLD, SMALL_THRESHOLD, hex_of, luminance, mix, rgb)

MAX_SUPERSAMPLED = 2048


# ----------------------------------------------------------------- colour ---
def intersection_colour(family, small: bool):
    """The crossing, stated rather than blended.

    The specification asks for rich, never black: if the declared colour is too
    dark to hold its own at 16px it is lifted toward the pair it sits between,
    which keeps luminance without inventing a new hue.
    """
    c = rgb(family.intersect)
    if luminance(c) < 0.035:
        c = mix(c, mix(rgb(family.base), rgb(family.ribbon), 0.5), 0.28)
    if small:
        c = mix(c, rgb(family.base), 0.10)   # a touch more body at small sizes
    return c


def depth(lo, hi):
    """Widen a two-stop pair so the plane reads dimensional.

    Browser validation against the reference showed the declared pair alone is
    too shallow a range: a plane filled base -> base_hi looks flat next to the
    reference's deep-to-bright sweep. Deepening the low stop toward the ink and
    lifting the high stop is what buys the depth, without introducing a hue the
    family did not declare.
    """
    return mix(lo, rgb(INK_NAVY), 0.22), mix(hi, (255, 255, 255), 0.10)


def tint(colour, t):
    """Lighten toward white without boosting saturation into neon."""
    return mix(rgb(colour) if isinstance(colour, str) else colour, (255, 255, 255), t)


# ------------------------------------------------------------ rasterising ---
class _Flatten(BasePen):
    def __init__(self, steps=24):
        super().__init__(None)
        self.steps, self.contours, self._cur = steps, [], []

    def _moveTo(self, pt):
        self.flush()
        self._cur = [pt]

    def _lineTo(self, pt):
        self._cur.append(pt)

    def _curveToOne(self, c1, c2, pt):
        x0, y0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            self._cur.append((
                u ** 3 * x0 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * pt[0],
                u ** 3 * y0 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * pt[1]))

    def _qCurveToOne(self, c, pt):
        x0, y0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            self._cur.append((u * u * x0 + 2 * u * t * c[0] + t * t * pt[0],
                              u * u * y0 + 2 * u * t * c[1] + t * t * pt[1]))

    def _closePath(self):
        self.flush()

    def _endPath(self):
        self.flush()

    def flush(self):
        if len(self._cur) > 2:
            self.contours.append(self._cur)
        self._cur = []


def _signed_area(contour) -> float:
    a = 0.0
    for i, (x0, y0) in enumerate(contour):
        x1, y1 = contour[(i + 1) % len(contour)]
        a += x0 * y1 - x1 * y0
    return a / 2


def path_mask(d: str, side: int) -> Image.Image:
    """Fill one path, honouring winding.

    Contours wound like the first are unioned; contours wound against it are
    holes. Even-odd would be wrong here: a figure built from overlapping
    sub-shapes - three people sharing a torso - would cancel itself where the
    shapes meet, which is exactly the hole-punched result even-odd produced in
    the first pass.
    """
    pen = _Flatten()
    parse_path(d, pen)
    pen.flush()
    if not pen.contours:
        return Image.new("L", (side, side), 0)
    u = side / ARTBOARD
    reference = _signed_area(pen.contours[0])
    solid = Image.new("L", (side, side), 0)
    holes = Image.new("L", (side, side), 0)
    for contour in pen.contours:
        one = Image.new("L", (side, side), 0)
        ImageDraw.Draw(one).polygon([(x * u, y * u) for x, y in contour], fill=255)
        same = (_signed_area(contour) >= 0) == (reference >= 0)
        if same:
            solid = ImageChops.lighter(solid, one)
        else:
            holes = ImageChops.lighter(holes, one)
    return ImageChops.multiply(solid, ImageChops.invert(holes))


def _ramp(side: int, lo, hi) -> Image.Image:
    """A 45-degree two-stop ramp, matching the SVG's gradient vector."""
    g = Image.linear_gradient("L").rotate(-45, resample=Image.BILINEAR, expand=False)
    g = g.crop((74, 74, 182, 182)).resize((side, side), Image.BILINEAR)
    return Image.composite(Image.new("RGB", (side, side), hex_of(hi)),
                           Image.new("RGB", (side, side), hex_of(lo)), g)


def _sub(a, b):
    return ImageChops.multiply(a, ImageChops.invert(b))


def icon_png(family, size: int, small: bool | None = None) -> Image.Image:
    """One icon at ``size``, transparent, optically centred."""
    small = (size < SMALL_THRESHOLD) if small is None else small
    ss = max(1, min(4, MAX_SUPERSAMPLED // max(size, 1)))
    side = size * ss
    art = G.BUILDERS[family.key](small)

    body = path_mask(art["body"], side)
    cx, cy = art.get("ribbon_centre", (ARTBOARD / 2, ARTBOARD / 2))
    r1d, r2d = G.ribbons(art["ribbon_offsets"], art["ribbon_width"], cx, cy)
    r1 = ImageChops.multiply(path_mask(r1d, side), body)
    r2 = ImageChops.multiply(path_mask(r2d, side), body)
    cross = ImageChops.multiply(r1, r2)
    ribbon = _sub(ImageChops.lighter(r1, r2), cross)

    base, base_hi = rgb(family.base), rgb(family.base_hi)
    # the ribbon is a translucent plane laid over the base, not the third hue
    # at full strength - the semantic object has to stay the subject
    rib = mix(base, rgb(family.ribbon), RIBBON_ALPHA)
    rib_hi = mix(base_hi, rgb(family.ribbon_hi), RIBBON_ALPHA)
    inter = intersection_colour(family, small)

    # Each plane gets the shared light, except the cube's faces: a face turned
    # away from the light must sweep differently or the box flattens into a
    # hexagon. That per-face angle is the whole 3D read.
    def fill(lo, hi, angle=LIGHT_ANGLE):
        if small:
            return Image.new("RGB", (side, side), hex_of(mix(lo, hi, 0.42)))
        return paint_gradient(side, crystal(lo, hi, angle=angle))

    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))

    def paint(img, mask):
        layer = img.convert("RGBA")
        layer.putalpha(mask)
        out.alpha_composite(layer)

    union = ImageChops.lighter(r1, r2)
    plane1 = _sub(body, union)
    paint(fill(base, base_hi), plane1)

    if "face_top" in art:
        top = _sub(ImageChops.multiply(path_mask(art["face_top"], side), body), union)
        paint(fill(tint(base, 0.26), tint(base_hi, 0.34), angle=LIGHT_ANGLE + 34), top)
    if "face_right" in art:
        right = _sub(ImageChops.multiply(path_mask(art["face_right"], side), body), union)
        paint(fill(rib, rib_hi, angle=LIGHT_ANGLE - 46), right)

    paint(fill(rib, rib_hi), ribbon)
    paint(fill(inter, mix(inter, rgb(family.base_hi), 0.30)), cross)

    if "corner" in art:
        corner = ImageChops.multiply(path_mask(art["corner"], side), body)
        paint(fill(tint(base, 0.40), tint(base_hi, 0.50), angle=LIGHT_ANGLE + 56), corner)

    if "detail" in art:
        det = ImageChops.multiply(path_mask(art["detail"], side), body)
        paint(Image.new("RGB", (side, side), "#F6F8FB"),
              det.point(lambda v: round(v * (1.0 if small else 0.95))))

    if not small and size >= SMALL_THRESHOLD:
        # specular first - a broad sweep across the upper shoulder of the whole
        # form, which is what makes it read as one material rather than as
        # planes that happen to touch
        out.alpha_composite(gloss_layer(side, body))
        # then the one narrow edge light, along the ribbon where it catches
        edge = _sub(union, union.filter(ImageFilter.MinFilter(3)))
        hl = Image.new("RGBA", (side, side), (233, 251, 255, 0))
        hl.putalpha(ImageChops.multiply(edge.point(lambda v: round(v * 0.44)), body))
        out.alpha_composite(hl)

    icon = out.resize((size, size), Image.LANCZOS) if ss > 1 else out
    if size < SHADOW_THRESHOLD:
        return icon

    small_body = body.resize((size, size), Image.LANCZOS) \
        .filter(ImageFilter.GaussianBlur(max(1, round(size * 0.035))))
    shadow = Image.new("RGBA", (size, size), (11, 36, 66, 0))
    shadow.putalpha(small_body.point(lambda v: round(v * 0.16)))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(shadow, (0, max(1, round(size * 0.018))))
    canvas.alpha_composite(icon)
    return canvas


# ------------------------------------------------------------------- SVG ---
def _grad(uid, grad):
    """One gradient, carrying the same stops and vector the rasteriser uses."""
    return (f'    <linearGradient id="{uid}" {grad.svg_vector()}>'
            f'{grad.svg_stops()}</linearGradient>\n')


def _gloss_grad(uid):
    """The specular sweep. Alpha stops rather than a blend mode, so an export
    that ignores CSS still gets the same result."""
    g = gloss()
    return (f'    <linearGradient id="{uid}" {g.svg_vector()}>'
            f'<stop offset="0" stop-color="{ICE_HIGHLIGHT}" stop-opacity="{GLOSS_ALPHA:.3g}"/>'
            f'<stop offset="{GLOSS_END:.3g}" stop-color="{ICE_HIGHLIGHT}" stop-opacity="0"/>'
            f'</linearGradient>\n')


def icon_svg(family, small: bool = False, size: int | None = None) -> str:
    """The canonical SVG. IDs are prefixed per module so two icons can be
    inlined in one document without colliding."""
    art = G.BUILDERS[family.key](small)
    p = f"xf3-{family.key}" + ("-s" if small else "")
    cx, cy = art.get("ribbon_centre", (ARTBOARD / 2, ARTBOARD / 2))
    r1, r2 = G.ribbons(art["ribbon_offsets"], art["ribbon_width"], cx, cy)
    base, base_hi = rgb(family.base), rgb(family.base_hi)
    rib = mix(base, rgb(family.ribbon), RIBBON_ALPHA)
    rib_hi = mix(base_hi, rgb(family.ribbon_hi), RIBBON_ALPHA)
    inter = intersection_colour(family, small)

    defs = [f'    <clipPath id="{p}-body"><path d="{art["body"]}" clip-rule="evenodd"/></clipPath>\n',
            f'    <clipPath id="{p}-r1"><path d="{r1}"/></clipPath>\n']
    if not small:
        defs += [_grad(f"{p}-g-base", crystal(base, base_hi)),
                 _grad(f"{p}-g-rib", crystal(rib, rib_hi)),
                 _grad(f"{p}-g-int", crystal(inter, mix(inter, base_hi, 0.30))),
                 _gloss_grad(f"{p}-g-gloss")]
        if "face_top" in art:
            defs.append(_grad(f"{p}-g-top", crystal(tint(base, 0.26), tint(base_hi, 0.34),
                                                    angle=LIGHT_ANGLE + 34)))
        if "face_right" in art:
            defs.append(_grad(f"{p}-g-right", crystal(rib, rib_hi, angle=LIGHT_ANGLE - 46)))
        if "corner" in art:
            defs.append(_grad(f"{p}-g-corner", crystal(tint(base, 0.40), tint(base_hi, 0.50),
                                                       angle=LIGHT_ANGLE + 56)))

    def paint_base():
        return f'url(#{p}-g-base)' if not small else hex_of(mix(base, base_hi, 0.42))

    def paint_rib():
        return f'url(#{p}-g-rib)' if not small else hex_of(mix(rib, rib_hi, 0.42))

    def paint_int():
        return f'url(#{p}-g-int)' if not small else hex_of(inter)

    def paint_role(role, lo, hi):
        return f'url(#{p}-g-{role})' if not small else hex_of(mix(lo, hi, 0.42))

    dim = size or ARTBOARD
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{dim}" height="{dim}" '
           f'viewBox="0 0 {ARTBOARD} {ARTBOARD}" role="img" '
           f'aria-label="AFENDA xForge {family.label} icon">\n',
           '  <defs>\n', *defs, '  </defs>\n',
           f'  <g clip-path="url(#{p}-body)">\n',
           f'    <path d="{art["body"]}" fill="{paint_base()}" fill-rule="evenodd"/>\n']

    if "face_top" in art:
        out.append(f'    <path d="{art["face_top"]}" fill="{hex_of(tint(base, 0.30))}"/>\n')
    if "face_right" in art:
        out.append(f'    <path d="{art["face_right"]}" fill="{paint_rib()}"/>\n')

    out += [f'    <path d="{r1}" fill="{paint_rib()}"/>\n',
            f'    <path d="{r2}" fill="{paint_rib()}"/>\n',
            f'    <g clip-path="url(#{p}-r1)"><path d="{r2}" fill="{paint_int()}"/></g>\n']

    if "corner" in art:
        out.append(f'    <path d="{art["corner"]}" fill="{hex_of(tint(base, 0.44))}"/>\n')
    if "detail" in art:
        out.append(f'    <path d="{art["detail"]}" fill="#F6F8FB" '
                   f'fill-opacity="{"1" if small else "0.95"}"/>\n')
    out += ['  </g>\n', '</svg>\n']
    return "".join(out)


def manifest_entry(family, small_sizes, large_sizes):
    art = G.BUILDERS[family.key](False)
    return {
        "module": family.key,
        "label": family.label,
        "renderer": RENDERER_VERSION,
        "palette": family.as_dict(),
        "intersection_resolved": hex_of(intersection_colour(family, False)),
        "ribbon": {"angles": [45.0, -45.0],
                   "width_fraction": art["ribbon_width"],
                   "offsets": list(art["ribbon_offsets"])},
        "svg": f"{family.key}.svg",
        "small_svg": [f"small/{family.key}-{s}.svg" for s in small_sizes],
        "png": {str(s): f"png/{s}/{family.key}.png" for s in small_sizes + large_sizes},
    }
