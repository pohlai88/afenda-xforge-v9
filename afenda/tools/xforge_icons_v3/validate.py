"""Structural validation. What a reviewer would otherwise have to check by eye.

These are the gates the reconstruction directive names: no raster inside an SVG,
no generic icon-library master, a valid viewBox, deterministic output, unique
keys and ids. They are cheap, so they run in the test suite rather than in a
checklist someone remembers to follow.
"""
from __future__ import annotations

import re

from .geometry import MASTERS
from .render_svg import icon_svg
from .spec import ORDER, SIZES, SPECS

__all__ = ["check_svg", "check_all", "PROHIBITED_SOURCES"]

# A final master may not come from any of these. They may be read for semantic
# understanding; they may not be the shipped geometry.
PROHIBITED_SOURCES = ("fontawesome", "font-awesome", "lucide", "heroicon",
                      "material-icons", "bootstrap-icons", "glyphicon", "@font-face")


def check_svg(key: str, svg: str) -> list[str]:
    """Every structural fault in one icon, as human-readable lines."""
    faults = []
    if "<image" in svg:
        faults.append(f"{key}: contains <image>, which means a raster was embedded")
    if "data:image" in svg or "base64," in svg:
        faults.append(f"{key}: contains a data: raster payload")
    if not re.search(r'viewBox="0 0 \d+ \d+"', svg):
        faults.append(f"{key}: has no valid viewBox")
    if "<svg" not in svg or "</svg>" not in svg:
        faults.append(f"{key}: is not a complete svg document")
    low = svg.lower()
    for bad in PROHIBITED_SOURCES:
        if bad in low:
            faults.append(f"{key}: references a prohibited icon source ({bad})")
    if "<rect" in svg and 'width="256" height="256"' in svg:
        faults.append(f"{key}: has a full-bleed rect, which is a background tile")
    # Filters are allowed in the crystal tier and NOWHERE else. A blur
    # rasterises differently between engines and falls apart below about 32px,
    # so it is confined to 48-128 where it is both safe and the whole point:
    # the board's planes give way at their edges rather than ending on a line.
    # check_all enforces the other half of this - that 16 and 24 carry none.
    if "filter=" in svg and "feGaussianBlur" not in svg:
        faults.append(f"{key}: uses a filter that is not the sanctioned edge blur")
    uid = SPECS[key].uid()
    for ref in re.findall(r"url\(#([^)]+)\)", svg):
        if not ref.startswith(uid):
            faults.append(f"{key}: references id {ref!r} outside its own namespace")
        if f'id="{ref}"' not in svg:
            faults.append(f"{key}: references id {ref!r} that it does not declare")
    return faults


def check_all() -> list[str]:
    """Every fault across the family, including cross-icon collisions."""
    faults = []
    seen_uid = {}
    for key in ORDER:
        if key not in SPECS:
            faults.append(f"{key}: has no spec")
            continue
        if key not in MASTERS:
            faults.append(f"{key}: has no bespoke master")
            continue
        svg = icon_svg(key, max(SIZES))
        faults.extend(check_svg(key, svg))
        # The small end must stay filter-free. This is the gate that keeps the
        # crystal tier's licence from leaking down to where it would hurt.
        for small in (s for s in SIZES if s < 48):
            if "filter" in icon_svg(key, small):
                faults.append(f"{key}@{small}: carries a filter below the crystal tier")
        if icon_svg(key, max(SIZES)) != svg:
            faults.append(f"{key}: SVG generation is not deterministic")
        uid = SPECS[key].uid()
        if uid in seen_uid:
            faults.append(f"{key}: shares a generated id namespace with {seen_uid[uid]}")
        seen_uid[uid] = key
    if len(set(ORDER)) != len(ORDER):
        faults.append("icon keys are not unique")
    return faults
