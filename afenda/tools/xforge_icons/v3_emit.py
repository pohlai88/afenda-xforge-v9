"""Emit the V3 masters as standalone, self-contained SVG.

One function writes every module, so a change to the plane system reaches all
five and cannot be applied to four of them by accident.
"""
from __future__ import annotations

from .v3_native import (PALETTES, PLANE_DEEP, PLANE_GLASS, PLANE_OVERLAP, VEC_BASE,
                        VEC_DEEP, VEC_FOLD, VEC_GLASS, VEC_OVERLAP, VIEW_H, VIEW_W)
from .v3_shapes import SHAPES

RENDERER = "xforge-v3-native"


def _stops(stops):
    out = []
    for offset, colour, opacity in stops:
        op = f' stop-opacity="{opacity}"' if opacity else ""
        out.append(f'<stop offset="{offset}" stop-color="{colour}"{op}/>')
    return "".join(out)


def _grad(uid, vec, stops):
    x1, y1, x2, y2 = vec
    return (f'    <linearGradient id="{uid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
            f' gradientUnits="userSpaceOnUse">{_stops(stops)}</linearGradient>\n')


def master_svg(key: str, *, micro: bool = False, size: int | None = None,
               shadow: bool = True) -> str:
    """One module's master.

    ``micro`` selects the small-size artwork: the planes stay - they are the
    identity and they survive downscaling - while sub-pixel passes (the glass
    overlay on the fold, the hairline edge, the second mark stroke) come off,
    because below 32px they contribute noise rather than form.
    """
    pal = PALETTES[key]
    art = SHAPES[key](micro)
    p = f"xf3-{key}" + ("-m" if micro else "")

    # the gear's aperture belongs to the clip too, or the planes fill the hole
    body_clip = art["body"] + (" " + art["aperture"] if "aperture" in art else "")

    defs = [f'    <clipPath id="{p}-clip" clip-rule="evenodd">'
            f'<path d="{body_clip}"/></clipPath>\n',
            _grad(f"{p}-base", VEC_BASE, pal.base),
            _grad(f"{p}-glass", VEC_GLASS, pal.glass),
            _grad(f"{p}-deep", VEC_DEEP, pal.deep),
            _grad(f"{p}-overlap", VEC_OVERLAP, pal.overlap)]
    if pal.fold and "fold" in art:
        defs.append(_grad(f"{p}-fold", VEC_FOLD, pal.fold))
        defs.append(f'    <linearGradient id="{p}-foldglass" x1="183" y1="38" x2="274" y2="124"'
                    f' gradientUnits="userSpaceOnUse">'
                    f'<stop offset="0" stop-color="#ffffff" stop-opacity=".30"/>'
                    f'<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
                    f'</linearGradient>\n')
    if shadow and not micro:
        # In the SVG, not CSS: a drop-shadow applied by the page does not
        # survive export to PNG or to an app launcher.
        defs.append(
            f'    <filter id="{p}-shadow" x="-25%" y="-25%" width="150%" height="165%">'
            f'<feGaussianBlur in="SourceAlpha" stdDeviation="3.8"/>'
            f'<feOffset dy="7" result="o"/>'
            f'<feColorMatrix in="o" type="matrix" values="0 0 0 0 0.02 0 0 0 0 0.16'
            f' 0 0 0 0 0.25 0 0 0 .18 0" result="s"/>'
            f'<feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge>'
            f'</filter>\n')

    w = size or VIEW_W
    h = round((size or VIEW_W) * VIEW_H / VIEW_W) if size else VIEW_H
    filt = f' filter="url(#{p}-shadow)"' if (shadow and not micro) else ""

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {VIEW_W} {VIEW_H}" role="img" '
           f'aria-label="AFENDA xForge {pal.label} icon">\n',
           '  <defs>\n', *defs, '  </defs>\n',
           f'  <g{filt}>\n',
           f'    <path d="{body_clip}" fill="url(#{p}-base)" fill-rule="evenodd"/>\n']

    out += [f'    <g clip-path="url(#{p}-clip)">\n',
            f'      <polygon points="{PLANE_GLASS}" fill="url(#{p}-glass)"/>\n',
            f'      <polygon points="{PLANE_DEEP}" fill="url(#{p}-deep)"/>\n',
            f'      <polygon points="{PLANE_OVERLAP}" fill="url(#{p}-overlap)"/>\n']
    if "facet" in art:
        out.append(f'      <path d="{art["facet"]}" fill="#ffffff" fill-opacity="'
                   f'{"0.10" if micro else "0.16"}"/>\n')
    out.append('    </g>\n')

    if "fold" in art and pal.fold:
        out.append(f'    <path d="{art["fold"]}" fill="url(#{p}-fold)"/>\n')
        if not micro:
            out.append(f'    <path d="{art["fold"]}" fill="url(#{p}-foldglass)"/>\n')
    if "edge" in art and not micro:
        out.append(f'    <path d="{art["edge"]}" fill="none" stroke="#dff8ff" '
                   f'stroke-opacity=".35" stroke-width="1.4"/>\n')
    if "marks" in art:
        g = "".join(f'<path d="M{x} {y}H{x2}"/>' for x, x2, y, _w in art["marks"])
        sw = art["marks"][0][3]
        out.append(f'    <g fill="none" stroke="{pal.detail}" stroke-width="{sw}" '
                   f'stroke-linecap="round">{g}</g>\n')
        if not micro:
            g2 = "".join(f'<path d="M{x} {int(y) - 3}H{x2}"/>' for x, x2, y, _w in art["marks"])
            out.append(f'    <g fill="none" stroke="#ffffff" stroke-width="4" '
                       f'stroke-linecap="round" opacity=".18">{g2}</g>\n')

    out += ['  </g>\n', '</svg>\n']
    return "".join(out)


def manifest_entry(key: str) -> dict:
    pal = PALETTES[key]
    return {"module": key, "label": pal.label, "semantic_master": pal.semantic,
            "renderer": RENDERER, "artboard": [VIEW_W, VIEW_H],
            "planes": {"glass": PLANE_GLASS, "deep": PLANE_DEEP, "overlap": PLANE_OVERLAP},
            "palette": pal.as_dict(),
            "master": f"masters/{key}.svg", "micro": f"masters/{key}-micro.svg"}
