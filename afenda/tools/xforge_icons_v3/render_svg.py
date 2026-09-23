"""Canonical SVG. Specification -> SVG; every raster output derives from this.

No raster data ever enters an SVG here: no <image>, no data: URI, no traced
polygon dump. The output is meant to be read in a diff, so the elements are the
design vocabulary in the order the material states:

    body in the base ramp
    the object's own facets, each shaded across itself
    the secondary deep plane, through the object
    the accent - on an object facet where the board puts it there, otherwise
        on the primary plane, translucent, so the crossing is what compositing
        produces rather than a third region cut to their intersection
    the object's fine marks
    a restrained edge highlight

Every region carries its own multi-stop ramp rather than a flat fill. One ramp
across the body cannot model the form, because each facet painted on top of it
is constant, and a family of constant facets is what made an earlier pass read
as a sticker. Compared at equal size, the approved board carries 588-727 distinct
colours per thousand ink pixels where flat facets carried 132-154.

One filter appears, and only in the crystal tier: a Gaussian blur on the brand
planes. Filters rasterise inconsistently between engines and fall apart below
about 32px, so they are confined to 48-128, where they are both safe and the
whole point - the board's planes give way at their edges instead of ending on a
line. The validator enforces both halves of that: nothing but the sanctioned
blur, and nothing at all below 48. Everything else is gradients, per-stop
opacity and real alpha compositing.

Ids derive from the spec digest, so two builds of one commit are byte-identical
and two icons inlined in the same document cannot collide.
"""
from __future__ import annotations

from .geometry import MASTERS, plane_points
from .material import (controlled_overlap, facet_stops, hex_of, mix, rgb, shift,
                       structural_dark, tier_for)
from .spec import SPECS, VIEWBOX, IconSpec

__all__ = ["icon_svg"]

WHITE = (255, 255, 255)


def _poly(points) -> str:
    return " ".join(f"{x:g},{y:g}" for x, y in points)


# The light is global: one direction across the whole icon box, upper left to
# lower right. Anything not bounded by the frame must say so in user space,
# because a shard runs far past the edge and its own bounding box is mostly
# outside the picture. Under objectBoundingBox the ramp is sized to the shard,
# so WHICH END of it falls on the icon depends on which shard the spec happened
# to assign - which is how the gear caught a dark end and the ledger a light one
# from the very same declaration.
LIGHT = (0, 0, VIEWBOX, VIEWBOX)


def _stops(uid: str, role: str, colour, units: str, axis,
           lift: float | None = None, drop: float | None = None,
           alpha: tuple[float, ...] | None = None) -> str:
    """One gradient definition. ``alpha`` gives a per-stop opacity.

    Opacity belongs in the stops rather than in a fill-opacity attribute
    whenever a plane should dissolve across the object instead of sitting on it
    at one constant strength. That is real compositing - the layers underneath
    show through by differing amounts - and it needs no filter to achieve.
    """
    kw = {}
    if lift is not None:
        kw["lift"] = lift
    if drop is not None:
        kw["drop"] = drop
    stops = facet_stops(colour, **kw)
    if alpha is None:
        body = "".join(f'<stop offset="{o:g}" stop-color="{c}"/>' for o, c in stops)
    else:
        body = "".join(f'<stop offset="{o:g}" stop-color="{c}" stop-opacity="{a:g}"/>'
                       for (o, c), a in zip(stops, alpha))
    x1, y1, x2, y2 = axis
    return (f'    <linearGradient id="{uid}-{role}" gradientUnits="{units}" '
            f'x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}">'
            f'{body}</linearGradient>\n')


def _ramp(uid: str, role: str, colour, axis=(0, 0, 1, 1),
          lift: float | None = None, drop: float | None = None) -> str:
    """A facet's own gradient, across that facet's own bounding box.

    objectBoundingBox is the point for facets: each is shaded across itself,
    which is what "per-facet" means, and each sits inside the frame so its own
    box is a meaningful extent.
    """
    return _stops(uid, role, colour, "objectBoundingBox", axis, lift, drop)


def _plane_ramp(uid: str, role: str, colour, lift: float | None = None,
                drop: float | None = None,
                alpha: tuple[float, ...] | None = None) -> str:
    """A ramp for geometry that runs past the frame: global light, user space."""
    return _stops(uid, role, colour, "userSpaceOnUse", LIGHT, lift, drop, alpha)


# How far past the declared pair the body ramp reaches, at each end. The
# manifest's base and base_hi both sit in the middle third of the value range,
# so a two-stop ramp between them models almost nothing - which is why an
# earlier pass read as pale next to the board. The board's own bodies run from a
# near-white catch of light down to a deep saturated foot.
RAMP_LIFT = 0.13
RAMP_FOOT = 0.30


def _family_ramp(uid: str, role: str, lo: str, hi: str) -> str:
    """The family ramp, reaching past base and base_hi at both ends.

    Across the OBJECT's own box, not the icon's. A body is bounded by the frame,
    so its box is meaningful - and a form that does not reach the corners, like
    the gear's ring or the ribbon, otherwise samples only the middle of an
    icon-box ramp and comes out with half the value range the board carries.
    """
    return (f'    <linearGradient id="{uid}-{role}" gradientUnits="objectBoundingBox" '
            f'x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{shift(hi, RAMP_LIFT)}"/>'
            f'<stop offset=".38" stop-color="{hi}"/>'
            f'<stop offset=".72" stop-color="{lo}"/>'
            f'<stop offset="1" stop-color="{shift(lo, -RAMP_FOOT)}"/></linearGradient>\n')


# How a plane behaves as it crosses the object, as a multiplier on its own alpha
# at each stop, running with the light from the lit end to the shaded end.
#
# A brand plane DISSOLVES: at one constant opacity it reads as a sheet laid on
# top, where one that gives way as it travels reads as structure passing through.
#
# A shadow does the opposite, and conflating the two is why reassigning the
# gear's deep plane to the shaded half still produced no shadow: the plane was
# being faded out precisely where it was meant to be deepest, so it composited
# to luminance 59 against a threshold of 60. A shadow is absent where the light
# lands and strongest where the light has gone.
DISSOLVE = (1.0, 0.93, 0.64)
# A floor, then a rise to full. The floor matters: a deep plane that fades to
# nearly nothing at the lit end loses the shadow on any icon whose plane sits in
# the lit half, which cost CRM two thirds of its modelling. Reaching 1.0 at the
# shaded end matters too - a solid's shadow side is opaque there, and at 0.9
# over a light base the composite landed at luminance 62, just the wrong side of
# reading as dark at all.
DEEPEN = (0.78, 0.90, 1.0)


def _form_facets(key: str, art: dict, spec: IconSpec):
    """The object's own planes: the form's depth, before any brand geometry.

    Each entry is ``(role, path, colour, axis, lift, drop)``. Only facets that
    model the SOLID appear here. A facet the board colours with the accent - the
    cube's right face, the right figure, the ribbon's leading edge - is drawn
    later in the accent ramp, which is what puts the gold on an object rather
    than in a floating band.
    """
    base, base_hi = rgb(spec.base), rgb(spec.base_hi)
    if key == "accounting":
        # the folded corner is the lightest region in the icon: a glass fold,
        # which the board makes pale cyan rather than a darker shade of the page
        return [("fold", art["fold"], mix(base_hi, WHITE, 0.72), (1, 0, 0, 1), None, None)]
    if key == "inventory":
        # Three faces, three different values, or the cube reads as a flat
        # hexagon. Measured against the board, this icon previously carried no
        # ink below luminance 60 at all, which is why it had no volume.
        return [("facetop", art["face_top"], mix(base_hi, WHITE, 0.34), (0, 0, 1, 1), 0.07, 0.05),
                ("faceleft", art["face_left"], mix(base, (0, 0, 0), 0.14), (0, 0, 0, 1), 0.06, 0.10)]
    if key == "employees":
        # The centre figure is the nearest and carries the family's own purple;
        # the left steps back in a lighter tone. Leaving the centre to the body
        # ramp let base_hi dominate and the cluster read magenta.
        return [("left", art["left"], mix(base_hi, WHITE, 0.10), (0, 0, 1, 1), None, None),
                # Deeper than the family default: the board's nearest figure is its
                # darkest region, which is what puts it in front of the other two.
                ("centre", art["centre"], base, (0, 0, 1, 1), 0.10, 0.20)]
    if key == "fleet":
        # Tyres, not chassis. At the body's own value the wheels disappeared and
        # the van read as a box with a nose; they are also the cue that has to
        # survive to 16px, where the window and the cab seam are long gone.
        return [("wheels", art["wheels"], mix(base, (0, 0, 0), 0.55), (0, 0, 1, 1), 0.06, 0.06)]
    return []


def icon_svg(key: str, size: int = VIEWBOX) -> str:
    """The canonical master for ``key``, carrying the material ``size`` allows."""
    spec: IconSpec = SPECS[key]
    art = MASTERS[key]
    tier = tier_for(size)
    uid = spec.uid()
    box = VIEWBOX

    base, base_hi = rgb(spec.base), rgb(spec.base_hi)
    acc, acc_hi = rgb(spec.accent), rgb(spec.accent_hi)
    over = controlled_overlap(base, acc)
    deep_tone = structural_dark(base)
    plane = _poly(plane_points(spec.plane))
    deep = _poly(plane_points(spec.deep_plane))

    # A body with a hole - the gear - is one path with two contours filled
    # even-odd, so the aperture is part of the silhouette rather than a disc
    # painted over it in a background colour the icon does not have.
    body_d = art["body"] + (" " + art["aperture"] if "aperture" in art else "")
    even_odd = ' fill-rule="evenodd"' if "aperture" in art else ""
    # A clipPath child is governed by clip-rule, NOT by fill-rule; the two are
    # separate properties and fill-rule is ignored there. With the default
    # nonzero winding the aperture stops being a hole as soon as both contours
    # happen to wind the same way - which is exactly what softening does, since
    # Clipper normalises orientation - and every plane then paints into the gear.
    clip_rule = ' clip-rule="evenodd"' if "aperture" in art else ""

    facets = _form_facets(key, art, spec)

    defs = [f'    <clipPath id="{uid}-body"><path d="{body_d}"{clip_rule}/></clipPath>\n',
            f'    <clipPath id="{uid}-plane"><polygon points="{plane}"/></clipPath>\n',
            f'    <clipPath id="{uid}-deep"><polygon points="{deep}"/></clipPath>\n']

    if tier.sheen:
        # A pool of light, not a ramp. This is the single biggest difference
        # between a facetted vector and the board's glass: the light arrives
        # from a point above the upper left and falls away in every direction.
        # TINTED, not white. A white sheen bleaches the chroma out of whatever it
        # falls on: measured against the board it cost 0.16 saturation on the
        # gear, whose blue is the most saturated in the family. The board's own
        # highlights stay in the hue - a bright cyan, never a washed one.
        sheen_col = shift(spec.base_hi, 0.30)
        defs.append(
            f'    <radialGradient id="{uid}-sheen" gradientUnits="userSpaceOnUse" '
            f'cx="74" cy="52" r="168">'
            f'<stop offset="0" stop-color="{sheen_col}" stop-opacity="{tier.sheen:g}"/>'
            f'<stop offset=".42" stop-color="{sheen_col}" stop-opacity="{tier.sheen * 0.40:.3f}"/>'
            f'<stop offset="1" stop-color="{sheen_col}" stop-opacity="0"/>'
            f'</radialGradient>\n')
    if tier.blur:
        defs.append(f'    <filter id="{uid}-soft" x="-30%" y="-30%" width="160%" height="160%">'
                    f'<feGaussianBlur stdDeviation="{tier.blur:g}"/></filter>\n')

    if tier.gradients:
        defs.append(_family_ramp(uid, "base", spec.base, spec.base_hi))
        defs.append(_family_ramp(uid, "accent", spec.accent, spec.accent_hi))
        defs.append(_plane_ramp(uid, "deep", deep_tone, 0.13, 0.11,
                                tuple(DEEPEN)))
        defs.append(_plane_ramp(uid, "accentplane", acc, 0.13, 0.11,
                                tuple(tier.accent_alpha * d for d in DISSOLVE)))
        for role, _d, colour, axis, lift, drop in facets:
            defs.append(_ramp(uid, role, colour, axis, lift, drop))
        base_fill, accent_fill = f"url(#{uid}-base)", f"url(#{uid}-accent)"
        deep_fill = f"url(#{uid}-deep)"
        plane_accent_fill = f"url(#{uid}-accentplane)"
        # Opacity lives in the stops now, so the element itself is fully painted.
        deep_alpha = plane_alpha = 1.0
        facet_fill = {role: f"url(#{uid}-{role})" for role, *_ in facets}
    else:
        # flat duotone: one value per colour, taken off the middle of the ramp
        # rather than an end stop, so a 16px icon keeps the family's midtone
        base_fill = hex_of(mix(base, base_hi, 0.30))
        accent_fill = hex_of(mix(acc, acc_hi, 0.25))
        deep_fill = hex_of(deep_tone)
        plane_accent_fill = accent_fill
        deep_alpha, plane_alpha = 1.0, tier.accent_alpha
        facet_fill = {role: hex_of(colour) for role, _d, colour, *_ in facets}

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{box}" height="{box}" '
           f'viewBox="0 0 {box} {box}" role="img" aria-label="AFENDA xForge {spec.label} icon">\n',
           '  <defs>\n', *defs, '  </defs>\n',
           f'  <path d="{body_d}"{even_odd} fill="{base_fill}"/>\n']

    # Facets are clipped to the body so they follow its softened hull. Without
    # the clip a square-cornered facet would overhang a rounded silhouette and
    # put the sharp corner back at the edge, where it is most visible.
    def paint_facet(role, d):
        out.append(f'  <g clip-path="url(#{uid}-body)">\n'
                   f'    <path d="{d}" fill="{facet_fill[role]}"/>\n  </g>\n')

    # A front facet is held back and painted after the accent and the crossing.
    # Without that the accent figure lands on top of the nearest one and the
    # cluster's depth order reverses.
    for role, d, _colour, *_ in facets:
        if role != spec.front_facet:
            paint_facet(role, d)

    # The secondary structural plane, through the object and clipped to it. This
    # is the deep diagonal the board carries on every icon; without it the solid
    # has no shadow side and the icon reads flat.
    # Blur first, clip second. The plane's own edge gives way while the object's
    # silhouette stays razor sharp, which is what the board actually does: its
    # planes dissolve, its forms never do.
    soft_open = f'<g filter="url(#{uid}-soft)">' if tier.blur else ""
    soft_shut = "</g>" if tier.blur else ""
    out.append(f'  <g clip-path="url(#{uid}-body)">{soft_open}\n'
               f'    <polygon points="{deep}" fill="{deep_fill}" '
               f'fill-opacity="{deep_alpha:g}"/>\n  {soft_shut}</g>\n')

    # The accent. Where the board puts gold on a facet of the object, it is
    # drawn on that facet; otherwise the primary plane carries it.
    if spec.accent_facet and spec.accent_facet in art:
        out.append(f'  <g clip-path="url(#{uid}-body)">\n'
                   f'    <path d="{art[spec.accent_facet]}" fill="{accent_fill}"/>\n  </g>\n')
        out.append(f'  <g clip-path="url(#{uid}-body)">\n'
                   f'    <polygon points="{plane}" fill="#FFFFFF" '
                   f'fill-opacity="{0.18 if tier.gradients else 0:g}"/>\n  </g>\n')
    else:
        out.append(f'  <g clip-path="url(#{uid}-body)">{soft_open}\n'
                   f'    <polygon points="{plane}" fill="{plane_accent_fill}" '
                   f'fill-opacity="{plane_alpha:g}"/>\n  {soft_shut}</g>\n')

    # The crossing. Where the planes are translucent it is not painted at all:
    # the accent is laid over the deep plane with real alpha, so the colour
    # where they meet is what compositing produces. That is the difference
    # between two sheets of glass and a third flat region cut to their
    # intersection, and it is why the crossing used to read as its own shape.
    #
    # The flat tier has no alpha to composite - 16 and 24 paint opaque, because
    # a translucent plane two pixels wide turns both colours to mud - so there
    # the crossing colour still has to be computed and painted explicitly.
    if not tier.gradients:
        out.append(f'  <g clip-path="url(#{uid}-body)"><g clip-path="url(#{uid}-plane)">\n'
                   f'    <polygon points="{deep}" fill="{hex_of(over)}" '
                   f'fill-opacity="{tier.overlap_alpha:g}"/>\n  </g></g>\n')

    # The nearest element, after everything structural. It is the last thing the
    # eye should meet, and it is what makes a cluster read as a group standing
    # together rather than as marks in a row.
    if spec.front_facet:
        for role, d, _colour, *_ in facets:
            if role == spec.front_facet:
                paint_facet(role, d)

    if tier.sheen:
        # Painted on the body path, never on a rect: a full-bleed rect is a
        # background tile, and this system does not have one.
        out.append(f'  <path d="{body_d}"{even_odd} fill="url(#{uid}-sheen)"/>\n')

    if tier.detail and "strip" in art:
        out.append(f'  <g clip-path="url(#{uid}-body)">\n'
                   f'    <path d="{art["strip"]}" fill="#FFFFFF" fill-opacity=".34"/>\n  </g>\n')

    # The optical correction belongs to the canonical master, not to one output
    # format. While the raster re-implemented the icon it could choose this on
    # its own and the two renderers silently disagreed at 16 and 24.
    detail_key = "detail_small" if tier.detail_small and "detail_small" in art else "detail"
    if tier.detail and detail_key in art:
        out.append(f'  <path d="{art[detail_key]}" fill="#FFFFFF" fill-opacity=".92"/>\n')

    if tier.highlight_alpha:
        # A restrained light on the leading edge, inside the body. An outer
        # stroke would be a halo, which the material rules out.
        out.append(f'  <g clip-path="url(#{uid}-body)">\n'
                   f'    <polygon points="{plane}" fill="none" stroke="#FFFFFF" '
                   f'stroke-opacity="{tier.highlight_alpha:g}" stroke-width="3"/>\n  </g>\n')

    out.append('</svg>\n')
    return "".join(out)
