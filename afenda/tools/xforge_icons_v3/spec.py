"""AFENDA xForge Application Icon System V3 - the declarative specification.

The design truth is the approved V3 reference board. This module holds what that
board states in machine-readable form, and nothing else: identity, palette
tokens, and the xForge plane each module carries. Geometry lives in
``geometry``, material in ``material``, export in ``render_svg`` / ``render_png``.
Keeping those four apart is the point - an icon's meaning, its surface, its
brand planes and its output format each change for different reasons.

Colour values are transcribed from AFENDA_xForge_Icon_Manifest_v3.1.json, which
specifies every module as ``source: BESPOKE_SVG`` with ``material: Crystal
Duotone V3.1``. They are NOT inherited from the V2 palette, which differs.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json

RENDERER = "xforge-v3.1"

# The canonical master coordinate system. One square viewBox for every icon, so
# optical weight can be compared directly between them.
VIEWBOX = 256
LIVE = 0.86  # share of the box the semantic object may occupy

# --- palette tokens --------------------------------------------------------
#
# Named once, referenced by the specs. No icon file carries a colour literal.
# Sampled from the approved board rather than copied from the manifest, because
# the board is the visual authority and the two disagree on hue for three of the
# five families. Each value below is a measured dominant bin; the hue angle after
# it is what that bin samples at.
AZURE = "#106090"         # 202 deg - Accounting's dominant bin, 5.2% of its ink
AZURE_HI = "#3AA7CB"      # its light end
COBALT = "#1070A0"        # 200 deg - Manufacturing's dominant bin, 10.9%
COBALT_HI = "#1FA0D2"     # 196 deg - its second bin, #1090C0 voiced up
SEA = "#00808F"           # 187 deg - Inventory's dominant bin, 5.6%
SEA_HI = "#2FB3AE"        # 180 deg - its #20A0A0 bin, voiced up
PLUM = "#7C3A8A"          # 290 deg - matches Employees' #502050 / #402050 bins
MULBERRY = "#BE2F7F"      # 325 deg - the magenta family
TEAL_DARK = "#0F766E"     # the cool accent Accounting and CRM carry
TEAL = "#10B981"
OCHRE = "#C97917"         # 38 deg - the warm accent, measured on three icons
MUSTARD = "#D49A23"

# Retained because the manifest names them and a reader will look for them. The
# board does not use these as dominant surfaces; AZURE and COBALT replaced them.
LEDGER = "#1E3A8A"        # 224 deg - too violet for the board's Accounting
SLATE = "#3B6EA8"


@dataclass(frozen=True)
class IconSpec:
    """One approved icon. The spec is the design truth; renderers are derived."""

    key: str
    label: str
    module: str
    semantic_master: str
    base: str
    base_hi: str
    accent: str
    accent_hi: str
    plane: str
    # The secondary structural plane. The board carries TWO planes crossing the
    # object plus their intersection - "max 3 planes" counts them: primary
    # translucent, secondary deep, and the crossing. One plane alone cannot
    # produce the board's depth.
    deep_plane: str = "shard-br"
    # Which part of the object carries the accent. The board puts gold on the
    # cube's right FACE, on the right FIGURE, on a gear QUADRANT - object
    # geometry, not a floating band. None means the primary plane carries it.
    accent_facet: str | None = None
    # A facet that must stay in FRONT of everything structural, drawn after the
    # accent and the crossing. The board's people cluster has a depth order -
    # the centre figure is nearest - and without this the accent figure paints
    # over it, which reverses the composition.
    front_facet: str | None = None
    version: int = 1

    def digest(self) -> str:
        """Stable lineage hash over renderer + spec. No timestamps, no order
        dependence: the same source commit must produce the same identifier."""
        payload = json.dumps({"renderer": RENDERER, "spec": asdict(self)},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(payload).hexdigest()

    def uid(self) -> str:
        """The prefix for every generated SVG id, unique per icon and stable."""
        return "xf3-" + self.digest()[:12]


# The canonical masters. The first five are the genetic reference for the system
# and were frozen before anything was built on them; the family now grows one
# tranche at a time, each audited against the board before the next begins.
SPECS: dict[str, IconSpec] = {
    "accounting": IconSpec(
        "accounting", "Accounting", "account", "Invoice ledger / folded record",
        base=AZURE, base_hi=AZURE_HI, accent=TEAL_DARK, accent_hi=TEAL,
        plane="band-diag", deep_plane="shard-br"),
    "employees": IconSpec(
        "employees", "Employees", "hr", "Team / people cluster",
        base=PLUM, base_hi=MULBERRY, accent=OCHRE, accent_hi=MUSTARD,
        plane="shard-bl", deep_plane="shard-br", accent_facet="right",
        front_facet="centre"),
    "inventory": IconSpec(
        "inventory", "Inventory", "stock", "Package cube / stock volume",
        base=SEA, base_hi=SEA_HI, accent=OCHRE, accent_hi=MUSTARD,
        plane="fold-tr", deep_plane="shard-bl", accent_facet="face_right"),
    "manufacturing": IconSpec(
        "manufacturing", "Manufacturing", "mrp", "Gear / production tool",
        base=COBALT, base_hi=COBALT_HI, accent=OCHRE, accent_hi=MUSTARD,
        # The deep plane was shard-tl, which left the gear with no shadow side
        # at all: the light runs upper left to lower right, so shard-tl sits in
        # the LIT half and a shadow declared there does nothing. Measured on the
        # board, the gear's dark centres on (0.535, 0.632) of its bounding box.
        # Of the planes still free once shard-br is carrying the gold, shard-bl
        # lands nearest at (0.454, 0.736) - against 0.366 away for shard-tl -
        # and projects to 0.595 along the light ramp, past the midpoint into the
        # shaded half.
        plane="shard-br", deep_plane="shard-bl"),
    "crm": IconSpec(
        "crm", "CRM", "crm", "Relationship pipeline / forward ribbon",
        base=PLUM, base_hi=MULBERRY, accent=TEAL_DARK, accent_hi=TEAL,
        plane="band-diag", deep_plane="shard-tl", accent_facet="lead"),

    # --- Finance, People and Operations: the first tranche beyond the five ---
    #
    # Every deep plane here lands in the SHADED half of the global light, which
    # the gear had to learn the hard way: a shadow declared on shard-tl sits
    # where the light falls and does nothing. shard-br projects to 0.76 along
    # the ramp and shard-bl to 0.50; shard-tl, at 0.195, is not used as a deep
    # plane by any icon added here.
    "hr_expense": IconSpec(
        "hr_expense", "Expenses", "hr_expense", "Receipt / wallet record",
        base=AZURE, base_hi=AZURE_HI, accent=OCHRE, accent_hi=MUSTARD,
        plane="band-diag", deep_plane="shard-br", accent_facet="band"),
    "contacts": IconSpec(
        "contacts", "Contacts", "contacts", "Contact card / person",
        base=PLUM, base_hi=MULBERRY, accent=TEAL_DARK, accent_hi=TEAL,
        plane="shard-tr", deep_plane="shard-br", accent_facet="panel"),
    "hr_recruitment": IconSpec(
        "hr_recruitment", "Recruitment", "hr_recruitment", "Candidate / open role",
        base=PLUM, base_hi=MULBERRY, accent=OCHRE, accent_hi=MUSTARD,
        plane="shard-tr", deep_plane="shard-br", accent_facet="opening"),
    "hr_skills": IconSpec(
        "hr_skills", "Skills", "hr_skills", "Skill badge / capability mark",
        base=PLUM, base_hi=MULBERRY, accent=OCHRE, accent_hi=MUSTARD,
        plane="band-diag", deep_plane="shard-br", accent_facet="tails"),
    # The manifest gives Fleet a PLUM accent against its teal body, not the warm
    # one the other Operations icons carry. Keeping that: it is the only cool
    # body in the tranche and a gold cab would have made it a second Inventory.
    "fleet": IconSpec(
        "fleet", "Fleet", "fleet", "Vehicle / motion plane",
        base=SEA, base_hi=SEA_HI, accent=PLUM, accent_hi=MULBERRY,
        plane="band-diag", deep_plane="shard-br", accent_facet="cab"),
}

ORDER = ("accounting", "employees", "inventory", "manufacturing", "crm",
         "hr_expense", "contacts", "hr_recruitment", "hr_skills", "fleet")

# Export matrix. SVG is canonical; every one of these is derived from it.
SIZES = (128, 64, 32, 24, 16)
