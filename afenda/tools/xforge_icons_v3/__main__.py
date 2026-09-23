"""Export the V3 icon system.

    .venv/Scripts/python -m afenda.tools.xforge_icons_v3 --out <dir>

Writes the canonical SVG masters, the derived PNG export matrix, a per-icon
lineage manifest and a human review contact sheet. Nothing is written outside
``--out``. This is a lab: the 108 production module icons Odoo ships are not
this command's business, and a test asserts that no module here so much as
names their location, so an accidental export cannot reach them.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from .contact_sheet import write_contact_sheet
from .render_png import icon_png
from .render_svg import icon_svg
from .spec import ORDER, RENDERER, SIZES, SPECS, VIEWBOX
from .validate import check_all

DEFAULT_OUT = pathlib.Path("afenda/assets/xforge-icons/v3.1")


def export(out: pathlib.Path) -> dict:
    (out / "svg").mkdir(parents=True, exist_ok=True)
    (out / "png").mkdir(parents=True, exist_ok=True)
    (out / "review").mkdir(parents=True, exist_ok=True)

    entries = []
    for key in ORDER:
        spec = SPECS[key]
        svg_name = f"{key}.svg"
        (out / "svg" / svg_name).write_text(icon_svg(key, VIEWBOX), encoding="utf-8", newline="\n")
        pngs = {}
        for size in SIZES:
            name = f"{key}@{size}.png"
            icon_png(key, size).save(out / "png" / name)
            pngs[str(size)] = f"png/{name}"
        entries.append({
            "key": key, "label": spec.label, "module": spec.module,
            "semantic_master": spec.semantic_master, "renderer": RENDERER,
            "viewBox": [0, 0, VIEWBOX, VIEWBOX], "digest": spec.digest(),
            "svg": f"svg/{svg_name}", "png": pngs,
            "palette": {"base": spec.base, "base_hi": spec.base_hi,
                        "accent": spec.accent, "accent_hi": spec.accent_hi},
            "planes": {"primary": spec.plane, "deep": spec.deep_plane,
                       "accent_facet": spec.accent_facet},
        })

    manifest = {"system": "AFENDA xForge Application Icon System",
                "version": "3.1", "renderer": RENDERER,
                "canonical": "svg", "derived": "png", "icons": entries}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    write_contact_sheet(out / "review" / "contact-sheet.png", out / "png")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="afenda.tools.xforge_icons_v3", description=__doc__)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    faults = check_all()
    for fault in faults:
        print("FAIL", fault)
    manifest = export(args.out)
    print(f"{len(manifest['icons'])} masters, {len(SIZES)} sizes each -> {args.out}")
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
