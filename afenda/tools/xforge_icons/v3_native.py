"""AFENDA xForge V3 — native master artwork.

The construction language is taken from the approved Accounting master, not
inferred from the raster board:

    rounded semantic silhouette, filled with a three-stop userSpaceOnUse gradient
      + three translucent diagonal planes, clipped inside that silhouette
      + module detail (a folded corner, a face, an aperture) with a glass pass
      = the final icon

The three planes are **the same polygons in every module**. They are clipped to
each silhouette, so each icon differs in outline and palette while the diagonal
vocabulary is literally identical - which is what makes the family resemblance
structural rather than a matter of care.

Four things here go beyond the supplied master, each for a production reason:

* **IDs are namespaced per module.** The master uses bare ``v3-base`` /
  ``v3-teal-plane``; inline two icons in one document and the second one's
  gradients silently retarget the first one's definitions.
* **Each master is self-contained.** The supplied file keeps its defs in the
  page and refers to them by ``<use>``; a standalone ``accounting.svg`` has to
  carry its own.
* **The shadow is in the SVG.** The master defines ``v3-shadow`` but never uses
  it - the page shadow is CSS ``drop-shadow`` on the hero, which does not
  survive export to a PNG or an app launcher.
* **Micro variants are real artwork.** At 16px the master's marks are
  ``stroke-width 14`` of a 300-unit box, which lands on three quarters of a
  pixel and disappears.
"""
from __future__ import annotations

# The shared artboard. Portrait, as the approved master is: an app icon that
# sits in a list reads taller than wide, and the fold needs the headroom.
VIEW_W, VIEW_H = 300, 365

# ---------------------------------------------------------------------------
# The xForge plane system. Identical in every module; only the clip differs.
# Angles and vertices are transcribed from the approved Accounting master.
PLANE_GLASS = "8,43 282,198 282,244 8,91"
PLANE_DEEP = "-8,330 282,112 282,183 88,340 -8,340"
PLANE_OVERLAP = "148,130 282,198 282,274 212,232 111,176"

# Gradient vectors, also from the master, in user space.
VEC_BASE = ("20", "20", "278", "335")
VEC_GLASS = ("20", "45", "270", "220")
VEC_DEEP = ("35", "330", "274", "112")
VEC_OVERLAP = ("152", "120", "285", "280")
VEC_FOLD = ("183", "24", "266", "120")


class Palette:
    """One module's colour character.

    ``base`` is the semantic object. ``glass``, ``deep`` and ``overlap`` are the
    three planes, each carrying its own opacity ramp - the translucency is in
    the stops, never in a blend mode, so an export cannot lose it.
    """

    __slots__ = ("key", "label", "semantic", "base", "glass", "deep", "overlap",
                 "detail", "fold")

    def __init__(self, key, label, semantic, base, glass, deep, overlap, detail,
                 fold=None):
        self.key, self.label, self.semantic = key, label, semantic
        self.base, self.glass, self.deep = base, glass, deep
        self.overlap, self.detail, self.fold = overlap, detail, fold

    def as_dict(self):
        return {"key": self.key, "label": self.label, "semantic": self.semantic,
                "base": self.base, "glass": self.glass, "deep": self.deep,
                "overlap": self.overlap, "detail": self.detail, "fold": self.fold}


# Stops are (offset, colour, opacity). The Accounting entry is transcribed from
# the approved master; the other four are built in the same language - same
# stop count, same opacity ramp, same relationship between the three planes.
ACCOUNTING = Palette(
    "accounting", "Accounting", "Invoice ledger / folded record",
    base=[("0", "#3ca7cb", None), (".47", "#178faa", None), ("1", "#52bdd8", None)],
    glass=[("0", "#58d9ca", ".96"), (".63", "#23b4b7", ".70"), ("1", "#167d9b", ".48")],
    deep=[("0", "#01335b", ".98"), (".58", "#045178", ".94"), ("1", "#073c67", ".90")],
    overlap=[("0", "#1677a5", ".72"), (".55", "#258bb5", ".70"), ("1", "#3bb5cf", ".62")],
    detail="#dffcff",
    fold=[("0", "#d2f5ff", None), (".42", "#9fd9f4", None), ("1", "#5db8e3", None)])

EMPLOYEES = Palette(
    "employees", "Employees", "Team / people cluster",
    base=[("0", "#c84f96", None), (".47", "#a3308a", None), ("1", "#d96bb0", None)],
    # the glass plane crosses the heads here, so it veils rather than covers:
    # "controlled gold secondary", and faces stay readable at 24px
    glass=[("0", "#f3c266", ".58"), (".63", "#d99a3a", ".44"), ("1", "#a8682a", ".30")],
    deep=[("0", "#3d1148", ".98"), (".58", "#5a1f63", ".94"), ("1", "#46154f", ".90")],
    overlap=[("0", "#8c2a78", ".74"), (".55", "#a13a8b", ".70"), ("1", "#c45aa6", ".62")],
    detail="#ffeaf8")

INVENTORY = Palette(
    "inventory", "Inventory", "Package cube / stock volume",
    base=[("0", "#3fc3c0", None), (".47", "#17a09f", None), ("1", "#55d6cd", None)],
    glass=[("0", "#6fe6d8", ".96"), (".63", "#26bdb4", ".70"), ("1", "#15879a", ".48")],
    deep=[("0", "#073f52", ".98"), (".58", "#0a5a66", ".94"), ("1", "#08485c", ".90")],
    overlap=[("0", "#c88a24", ".78"), (".55", "#dca43c", ".72"), ("1", "#f0c25e", ".64")],
    detail="#e4fffb")

MANUFACTURING = Palette(
    "manufacturing", "Manufacturing", "Gear / production tool",
    base=[("0", "#3aa5d6", None), (".47", "#1a7fb4", None), ("1", "#4fc0e2", None)],
    glass=[("0", "#6fd8f0", ".96"), (".63", "#2496c4", ".70"), ("1", "#136d97", ".48")],
    deep=[("0", "#022f52", ".98"), (".58", "#064a70", ".94"), ("1", "#04395f", ".90")],
    overlap=[("0", "#c8891c", ".78"), (".55", "#dea63e", ".72"), ("1", "#f2c264", ".64")],
    detail="#e3f8ff")

CRM = Palette(
    "crm", "CRM", "Relationship pipeline / forward ribbon",
    base=[("0", "#c4479b", None), (".47", "#9c2d87", None), ("1", "#d466ad", None)],
    glass=[("0", "#5fd8d0", ".94"), (".63", "#26aab4", ".70"), ("1", "#157b95", ".50")],
    deep=[("0", "#3a1046", ".98"), (".58", "#561d60", ".94"), ("1", "#42144d", ".90")],
    overlap=[("0", "#2f7fa8", ".74"), (".55", "#3f9fbc", ".70"), ("1", "#57c2d2", ".62")],
    detail="#ffeaf9")

PALETTES = {p.key: p for p in (ACCOUNTING, EMPLOYEES, INVENTORY, MANUFACTURING, CRM)}
ORDER = ("accounting", "employees", "inventory", "manufacturing", "crm")
