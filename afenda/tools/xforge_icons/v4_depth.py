"""AFENDA xForge V4 — layered depth over the V3 plane system.

V3 is frozen and stays as it is. V4 keeps every V3 decision - the silhouettes,
the three shared diagonal planes, the palettes, the translucency in the stops -
and adds the one thing V3 does not have: the planes read as *stacked* rather
than as regions of one flat surface.

The depth is built from geometry, never from blur:

    for each plane, three draws instead of one

    1. the plane offset AWAY from the light, in a darkened tone
       -> the sliver that peeks out on the lower right is the plane's thickness
    2. the plane offset TOWARD the light, in a lightened tone
       -> the sliver on the upper left is the light catching its leading edge
    3. the plane itself, on top

Both slivers are hidden under the plane except along its edges, so each plane
gains a lit edge and a cast edge for the cost of two extra paths. Nothing here
uses a filter, a blur or a blend mode, so the result survives export to PNG, to
an app launcher, and to any renderer that does clipping and gradients.

A rim light inside the silhouette and a contact shade along its foot finish the
stack: the object sits on the ground rather than floating on it.
"""
from __future__ import annotations

# Light comes from the upper left, as it does in the V3 master's gradients.
# The offset is a share of the 300-unit artboard: enough to read as thickness at
# 128px, small enough to close up cleanly at 32.
LIGHT_DX, LIGHT_DY = -1.0, -1.0
DEPTH = 5.0          # plane thickness, in artboard units
DEPTH_MICRO = 3.0    # thicker relative to size, so it survives downscaling

RISER_DARKEN = 0.42      # how far the thickness tone moves toward ink
EDGE_LIGHTEN = 0.46      # how far the lit edge moves toward white
RISER_OPACITY = 0.55
EDGE_OPACITY = 0.62

RIM_COLOUR = "#ffffff"
RIM_OPACITY = 0.22
RIM_WIDTH = 3.0

CONTACT_COLOUR = "#001c38"
CONTACT_OPACITY = 0.16
CONTACT_WIDTH = 7.0

INK = (2, 22, 42)


def _rgb(colour: str):
    h = colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(c):
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in c))


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def riser_tone(colour: str) -> str:
    """The side wall of a plane: the plane's own hue, driven toward ink.

    Deriving it from the plane rather than using one shared shadow colour is
    what keeps a gold plane's thickness gold and a navy plane's navy - a single
    grey riser reads as dirt on both.
    """
    return _hex(_mix(_rgb(colour), INK, RISER_DARKEN))


def edge_tone(colour: str) -> str:
    """The lit leading edge: the plane's hue lifted toward white."""
    return _hex(_mix(_rgb(colour), (255, 255, 255), EDGE_LIGHTEN))


def offsets(micro: bool = False):
    """(toward the light, away from the light) as translate pairs."""
    d = DEPTH_MICRO if micro else DEPTH
    return ((LIGHT_DX * d, LIGHT_DY * d), (-LIGHT_DX * d, -LIGHT_DY * d))


def plane_stack(points: str, fill: str, lead_colour: str, uid: str,
                micro: bool = False) -> str:
    """One plane drawn as a lit stack: thickness, leading edge, face."""
    (lx, ly), (dx, dy) = offsets(micro)
    riser = riser_tone(lead_colour)
    lit = edge_tone(lead_colour)
    return (
        f'      <polygon points="{points}" fill="{riser}" fill-opacity="{RISER_OPACITY}"'
        f' transform="translate({dx:.1f} {dy:.1f})"/>\n'
        f'      <polygon points="{points}" fill="{lit}" fill-opacity="{EDGE_OPACITY}"'
        f' transform="translate({lx:.1f} {ly:.1f})"/>\n'
        f'      <polygon points="{points}" fill="{fill}"/>\n')


# The lit half of the artboard, at the light angle. Clipping the rim to this
# is what gives the object a light *direction*: a rim that runs the whole way
# round reads as a sticker outline, not as a lit edge.
LIT_HALF = "-60,-60 420,-60 -60,420"


def specular(uid: str, tint: str = "#ffffff") -> str:
    """A restrained highlight where the light strikes. Not a glow: it is bounded
    by the silhouette clip and falls to nothing before the middle."""
    return (f'    <radialGradient id="{uid}" cx="72" cy="66" r="210"'
            f' gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{tint}" stop-opacity=".20"/>'
            f'<stop offset=".55" stop-color="{tint}" stop-opacity=".05"/>'
            f'<stop offset="1" stop-color="{tint}" stop-opacity="0"/>'
            f'</radialGradient>\n')


def rim_and_contact(body_d: str, micro: bool = False, rim_clip: str = "",
                    tint: str = RIM_COLOUR) -> str:
    """A rim light inside the silhouette's lit edge and a shade along its foot.

    Both are strokes on the body path, drawn inside the body clip so only the
    inner half of each stroke survives - an outer glow would be a halo, which
    the doctrine rules out.
    """
    (lx, ly), (dx, dy) = offsets(micro)
    rim_w = RIM_WIDTH * (0.7 if micro else 1.0)
    con_w = CONTACT_WIDTH * (0.7 if micro else 1.0)
    return (
        f'      <g clip-path="url(#{rim_clip})">'
        f'<path d="{body_d}" fill="none" stroke="{tint}"'
        f' stroke-opacity="{RIM_OPACITY}" stroke-width="{rim_w}"'
        f' transform="translate({lx:.1f} {ly:.1f})"/></g>\n'
        f'      <path d="{body_d}" fill="none" stroke="{CONTACT_COLOUR}"'
        f' stroke-opacity="{CONTACT_OPACITY}" stroke-width="{con_w}"'
        f' transform="translate({dx:.1f} {dy:.1f})"/>\n')
