"""Emit the V4 masters: the V3 system with layered depth.

V3 is untouched and still emits from ``v3_emit``. V4 reads the same palettes and
the same silhouettes, so the two stay in step: a correction to a silhouette
reaches both, and a V4 icon is recognisably the same icon as its V3 sibling.
"""
from __future__ import annotations

from .v3_native import (PALETTES, PLANE_DEEP, PLANE_GLASS, PLANE_OVERLAP, VEC_BASE,
                        VEC_DEEP, VEC_FOLD, VEC_GLASS, VEC_OVERLAP, VIEW_H, VIEW_W)
from .v4_shapes import SHAPES
from .v4_colour import (FAMILIES as CFAM, edge_of, lift, riser_of,
                        stops_oklch as stops_for, tint_of)
from .oklch import ACCENT_TARGET, scale
from .v4_depth import LIT_HALF, plane_stack, rim_and_contact, specular

RENDERER = "xforge-v4-layered"


def _stops(stops):
    return "".join(
        f'<stop offset="{o}" stop-color="{c}"'
        + (f' stop-opacity="{a}"' if a else "") + "/>"
        for o, c, a in stops)


def _grad(uid, vec, stops):
    x1, y1, x2, y2 = vec
    return (f'    <linearGradient id="{uid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
            f' gradientUnits="userSpaceOnUse">{_stops(stops)}</linearGradient>\n')


def master_svg(key: str, *, micro: bool = False, size: int | None = None,
               shadow: bool = True) -> str:
    pal = PALETTES[key]
    art = SHAPES[key](micro)
    p = f"xf4-{key}" + ("-m" if micro else "")
    st = stops_for(key)
    fam = CFAM[key]
    body_clip = art["body"] + (" " + art["aperture"] if "aperture" in art else "")

    defs = [f'    <clipPath id="{p}-clip" clip-rule="evenodd">'
            f'<path d="{body_clip}"/></clipPath>\n',
            _grad(f"{p}-base", VEC_BASE, st["base"]),
            _grad(f"{p}-glass", VEC_GLASS, st["glass"]),
            _grad(f"{p}-deep", VEC_DEEP, st["deep"]),
            _grad(f"{p}-overlap", VEC_OVERLAP, st["overlap"]),
            f'    <clipPath id="{p}-lit"><polygon points="{LIT_HALF}"/></clipPath>\n',
            # The xForge X is its two crossing arms. Clipping one arm by the
            # other gives their true intersection, so the crossing can never
            # drift from the arms that make it: it is not a third polygon drawn
            # beside them approximating where they meet, it IS where they meet.
            f'    <clipPath id="{p}-armA"><polygon points="{PLANE_GLASS}"/></clipPath>\n',
            specular(f"{p}-spec", tint_of(key))]
    if pal.fold and "fold" in art:
        defs.append(_grad(f"{p}-fold", VEC_FOLD, [
            ("0", lift(fam["glass"], 0.86), None),
            (".42", lift(fam["base"], 0.62), None),
            ("1", lift(fam["base"], 0.34), None)]))
        defs.append(f'    <linearGradient id="{p}-foldglass" x1="183" y1="38" x2="274" y2="124"'
                    f' gradientUnits="userSpaceOnUse">'
                    f'<stop offset="0" stop-color="#ffffff" stop-opacity=".34"/>'
                    f'<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
                    f'</linearGradient>\n')
    if shadow and not micro:
        defs.append(
            f'    <filter id="{p}-shadow" x="-30%" y="-30%" width="160%" height="175%">'
            f'<feGaussianBlur in="SourceAlpha" stdDeviation="4.4"/>'
            f'<feOffset dy="9" result="o"/>'
            f'<feColorMatrix in="o" type="matrix" values="0 0 0 0 0.02 0 0 0 0 0.14'
            f' 0 0 0 0 0.24 0 0 0 .20 0" result="s"/>'
            f'<feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge>'
            f'</filter>\n')

    w = size or VIEW_W
    h = round(size * VIEW_H / VIEW_W) if size else VIEW_H
    filt = f' filter="url(#{p}-shadow)"' if (shadow and not micro) else ""

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {VIEW_W} {VIEW_H}" role="img" '
           f'aria-label="AFENDA xForge {pal.label} icon">\n',
           '  <defs>\n', *defs, '  </defs>\n',
           f'  <g{filt}>\n',
           f'    <path d="{body_clip}" fill="url(#{p}-base)" fill-rule="evenodd"/>\n',
           f'    <g clip-path="url(#{p}-clip)">\n']

    # Each plane is a lit stack. Order matters: glass sits lowest, the deep
    # structural plane above it, the overlap on top - the same z-order V3 uses,
    # now with each plane carrying its own thickness.
    # arm one, arm two, then the crossing they make. Three planes, and the
    # third is derived from the first two rather than authored beside them.
    out += [plane_stack(PLANE_GLASS, f"url(#{p}-glass)", fam["glass"], f"{p}-g", micro),
            plane_stack(PLANE_DEEP, f"url(#{p}-deep)", fam["base"],
                        f"{p}-d", micro),
            f'      <g clip-path="url(#{p}-armA)">\n'
            + plane_stack(PLANE_DEEP, f"url(#{p}-overlap)", fam["accent"],
                          f"{p}-x", micro)
            + '      </g>\n']

    # Facets are drawn ABOVE the xForge planes, not beneath them. The audit
    # against the reference found this was the flattening bug: with the planes
    # on top, a cube's three faces stop carrying the form and it collapses into
    # a hexagon. The reference puts the object's own facets first and lays the
    # ribbon over them.
    base_sc = scale(fam["base"])
    acc_sc = scale(fam["accent"], target=ACCENT_TARGET)
    if "face_top" in art:
        out.append(f'      <path d="{art["face_top"]}" fill="{base_sc[300]}"/>\n')
    if "face_right" in art:
        out.append(f'      <path d="{art["face_right"]}" fill="{acc_sc[500]}"/>\n')
    if "ribbon" in art:
        # the xForge ribbon, over the facets and bending with the form
        out.append(f'      <path d="{art["ribbon"]}" fill="{tint_of(key)}"'
                   f' fill-opacity=".62"/>\n')
    if "facet" in art:
        out.append(f'      <path d="{art["facet"]}" fill="#ffffff" fill-opacity="'
                   f'{"0.10" if micro else "0.17"}"/>\n')

    # the carton's tape band and the funnel's stage divisions: the marks that
    # make a cube a carton and a funnel a pipeline
    if "band" in art:
        out.append(f'      <path d="{art["band"]}" fill="#062a44" fill-opacity=".20"/>\n')
    if "stages" in art:
        out.append(f'      <path d="{art["stages"]}" fill="#ffffff" fill-opacity=".26"'
                   f' fill-rule="evenodd"/>\n')

    if "lining" in art:
        # the single strongest 3D cue the audit found missing: a light line on
        # every facet boundary, and a brighter one on the lit outer edges
        lw = 1.6 if micro else 2.1
        out.append(f'      <path d="{art["lining"]}" fill="none" stroke="{base_sc[100]}"'
                   f' stroke-opacity=".50" stroke-width="{lw}" stroke-linejoin="round"/>\n')
    if "lit_edges" in art:
        out.append(f'      <path d="{art["lit_edges"]}" fill="none" stroke="{base_sc[50]}"'
                   f' stroke-opacity=".72" stroke-width="{2.0 if micro else 2.6}"'
                   f' stroke-linejoin="round" stroke-linecap="round"/>\n')

    out.append(rim_and_contact(art["body"], micro, rim_clip=f"{p}-lit", tint=tint_of(key)))
    out.append(f'      <path d="{body_clip}" fill="url(#{p}-spec)"'
               f' fill-rule="evenodd"/>\n')
    out.append('    </g>\n')

    if "fold" in art and pal.fold:
        out.append(f'    <path d="{art["fold"]}" fill="url(#{p}-fold)"/>\n')
        if not micro:
            out.append(f'    <path d="{art["fold"]}" fill="url(#{p}-foldglass)"/>\n')
    if "edge" in art and not micro:
        out.append(f'    <path d="{art["edge"]}" fill="none" stroke="#dff8ff" '
                   f'stroke-opacity=".40" stroke-width="1.6"/>\n')
    if "marks" in art:
        sw = art["marks"][0][3]
        # the marks get the same treatment as a plane: a cast edge below and a
        # lit edge above, so they sit *in* the surface rather than on it
        cast = "".join(f'<path d="M{x} {int(y) + 2}H{x2}"/>' for x, x2, y, _w in art["marks"])
        face = "".join(f'<path d="M{x} {y}H{x2}"/>' for x, x2, y, _w in art["marks"])
        out.append(f'    <g fill="none" stroke="#062a44" stroke-opacity=".22" '
                   f'stroke-width="{sw}" stroke-linecap="round">{cast}</g>\n')
        out.append(f'    <g fill="none" stroke="{pal.detail}" stroke-width="{sw}" '
                   f'stroke-linecap="round">{face}</g>\n')
        if not micro:
            top = "".join(f'<path d="M{x} {int(y) - 3}H{x2}"/>' for x, x2, y, _w in art["marks"])
            out.append(f'    <g fill="none" stroke="#ffffff" stroke-width="4" '
                       f'stroke-linecap="round" opacity=".22">{top}</g>\n')

    out += ['  </g>\n', '</svg>\n']
    return "".join(out)


def manifest_entry(key: str) -> dict:
    pal = PALETTES[key]
    return {"module": key, "label": pal.label, "semantic_master": pal.semantic,
            "renderer": RENDERER, "artboard": [VIEW_W, VIEW_H],
            "derives_from": "v3", "palette": pal.as_dict(),
            "master": f"masters/{key}.svg", "micro": f"masters/{key}-micro.svg"}
