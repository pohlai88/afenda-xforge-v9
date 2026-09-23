"""Generate the AFENDA xForge Version 3 icon system.

    .venv/Scripts/python -m afenda.tools.xforge_icons --out afenda/assets/xforge-icons/v3

Deterministic: the same checkout produces byte-identical output, which is what
lets the rendered files be committed and reviewed like any other source.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from .render import icon_png, icon_svg, manifest_entry
from .sheets import DARK, LIGHT, construction_board, contact_sheet, size_test
from .tokens import (ARTBOARD, FAMILIES, LARGE_SIZES, ORDER, PALETTE,
                     RENDERER_VERSION, RIBBON_ANGLES, RIBBON_WIDTH, SMALL_SIZES)

DEFAULT_OUT = pathlib.Path("afenda/assets/xforge-icons/v3")


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def generate(out: pathlib.Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    written = []

    for key in ORDER:
        fam = FAMILIES[key]
        write(out / f"{key}.svg", icon_svg(fam, small=False))
        written.append(f"{key}.svg")
        for s in SMALL_SIZES:
            write(out / "small" / f"{key}-{s}.svg", icon_svg(fam, small=True, size=s))
            written.append(f"small/{key}-{s}.svg")
        for s in SMALL_SIZES + LARGE_SIZES:
            p = out / "png" / str(s) / f"{key}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            icon_png(fam, s).save(p)
            written.append(f"png/{s}/{key}.png")

    prev = out / "previews"
    prev.mkdir(parents=True, exist_ok=True)
    contact_sheet(LIGHT).save(prev / "xforge-v3-contact-sheet-light.png")
    contact_sheet(DARK).save(prev / "xforge-v3-contact-sheet-dark.png")
    size_test().save(prev / "xforge-v3-size-test.png")
    construction_board().save(prev / "xforge-v3-construction.png")
    written += [f"previews/{n}" for n in sorted(p.name for p in prev.glob("*.png"))]

    tokens = {
        "renderer": RENDERER_VERSION,
        "artboard": ARTBOARD,
        "palette": PALETTE,
        "ribbon": {"angles": list(RIBBON_ANGLES), "width_fraction": RIBBON_WIDTH},
        "sizes": {"small": list(SMALL_SIZES), "large": list(LARGE_SIZES)},
        "families": {k: FAMILIES[k].as_dict() for k in ORDER},
    }
    write(out / "tokens.json", json.dumps(tokens, indent=2) + "\n")

    manifest = {
        "system": "AFENDA xForge Application Icon System",
        "version": 3,
        "renderer": RENDERER_VERSION,
        "artboard": ARTBOARD,
        "icons": [manifest_entry(FAMILIES[k], SMALL_SIZES, LARGE_SIZES) for k in ORDER],
    }
    write(out / "icon-manifest.json", json.dumps(manifest, indent=2) + "\n")
    written += ["tokens.json", "icon-manifest.json"]
    return {"out": str(out), "files": written}


def main() -> None:
    ap = argparse.ArgumentParser(prog="afenda.tools.xforge_icons")
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    result = generate(args.out)
    print(f"{len(result['files'])} files -> {result['out']}")


if __name__ == "__main__":
    main()
