"""Authored SVG path data as polygons Pillow can fill.

The V4 masters are authored as SVG path strings. The shipping renderer draws
with Pillow, which fills polygons and knows nothing about curves, so the two
need a bridge. ``fontTools.svgLib.path.parse_path`` is that bridge: it is
already a pinned dependency (app_icons reads FontAwesome through fontTools), it
parses the full path grammar including arcs, and it needs no native Cairo -
which on Windows is the difference between a pipeline that builds and one that
does not.

Flattening is at a FIXED subdivision rather than an adaptive tolerance. The
rendered PNGs are committed, so the same checkout has to produce the same bytes;
an adaptive flattener emits a different vertex count when a curve is scaled,
and every icon in the tree would churn on an unrelated edit.
"""
from __future__ import annotations

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path

__all__ = ["Polygons", "flatten_path", "scale_polygons", "bounds"]

# Segments per curve. 16 holds a 300-unit artboard's curvature to well under
# half a pixel at the 1024 supersampled box app_icons rasterises in, and stays
# cheap: the authored masters carry a few hundred curves between them.
SEGMENTS = 16

Point = tuple[float, float]
Polygons = list[list[Point]]


def _quad(p0: Point, c: Point, p1: Point) -> list[Point]:
    """A quadratic Bezier, sampled past its start and up to its end."""
    out = []
    for i in range(1, SEGMENTS + 1):
        t = i / SEGMENTS
        u = 1.0 - t
        out.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]))
    return out


def _cubic(p0: Point, c1: Point, c2: Point, p1: Point) -> list[Point]:
    """A cubic Bezier, sampled past its start and up to its end."""
    out = []
    for i in range(1, SEGMENTS + 1):
        t = i / SEGMENTS
        u = 1.0 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p1[0],
                    u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p1[1]))
    return out


def flatten_path(d: str) -> Polygons:
    """Every contour of the SVG path ``d``, as a list of vertex lists.

    A path with subpaths - the gear's teeth around its open centre, the
    accounting record's rules - comes back as several contours. The caller
    decides what they mean: filling them all with an even-odd rule reproduces
    the hole, which is what ``fill`` in SVG does by default for these masters.
    """
    pen = RecordingPen()
    parse_path(d, pen)

    polys: Polygons = []
    current: list[Point] = []
    start: Point | None = None
    here: Point | None = None

    def close() -> None:
        nonlocal current
        if len(current) >= 3:
            polys.append(current)
        current = []

    for op, args in pen.value:
        if op == "moveTo":
            close()
            here = start = tuple(args[0])
            current = [here]
        elif op == "lineTo":
            here = tuple(args[0])
            current.append(here)
        elif op == "curveTo":
            # fontTools emits cubics for SVG C/S and for arcs; a run of more
            # than one control pair is a super-Bezier, which parse_path does
            # not produce, so the three-point form is the whole story.
            c1, c2, end = (tuple(p) for p in args[-3:])
            current.extend(_cubic(here, c1, c2, end))
            here = end
        elif op == "qCurveTo":
            # TrueType-style: a run of off-curve points with one final on-curve
            # point, and an implied on-curve midpoint between each off-curve
            # pair. SVG Q/T reach here, and the masters use Q for every rounded
            # corner, so this path is load-bearing.
            pts = [tuple(p) for p in args if p is not None]
            if not pts:
                continue
            end = pts[-1]
            offs = pts[:-1]
            for i, ctrl in enumerate(offs):
                nxt = offs[i + 1] if i + 1 < len(offs) else end
                stop = ((ctrl[0] + nxt[0]) / 2.0, (ctrl[1] + nxt[1]) / 2.0) if i + 1 < len(offs) else end
                current.extend(_quad(here, ctrl, stop))
                here = stop
        elif op in ("closePath", "endPath"):
            if start is not None and current and current[-1] != start:
                current.append(start)
            close()
            here = start
    close()
    return polys


def scale_polygons(polys: Polygons, sx: float, sy: float,
                   dx: float = 0.0, dy: float = 0.0) -> Polygons:
    """``polys`` scaled about the origin then translated."""
    return [[(x * sx + dx, y * sy + dy) for x, y in poly] for poly in polys]


def bounds(polys: Polygons) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) over every vertex. Raises on empty input."""
    xs = [x for poly in polys for x, _ in poly]
    ys = [y for poly in polys for _, y in poly]
    if not xs:
        raise ValueError("no vertices")
    return min(xs), min(ys), max(xs), max(ys)
