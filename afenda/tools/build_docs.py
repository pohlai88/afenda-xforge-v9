"""Convert authored Markdown guides into committed QWeb templates.

    python -m afenda.tools.build_docs

Both the Markdown and the generated XML are committed; `test_guides_in_sync`
in afenda_api_docs asserts they agree, so a hand-edit of the XML is caught.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

import markdown

HERE = Path(__file__).resolve().parents[1]
SRC = HERE / "addons" / "afenda_api_docs" / "docs"
OUT = HERE / "addons" / "afenda_api_docs" / "views" / "guides.xml"


def slug_for(rel_path: str) -> str:
    return rel_path.removesuffix(".md").replace("/", "_").replace(".", "_")


def title_for(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def build(src_dir: Path, out_file: Path) -> int:
    pages = sorted(Path(src_dir).rglob("*.md"), key=lambda p: p.as_posix())
    parts = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>"]
    for page in pages:
        rel = page.relative_to(src_dir).as_posix()
        text = page.read_text(encoding="utf-8")
        body = markdown.markdown(text, extensions=["tables", "fenced_code"])
        parts.append(f'    <template id="guide_{slug_for(rel)}" name={quoteattr(title_for(text, rel))}>')
        parts.append('        <t t-call="web.frontend_layout">')
        parts.append('            <div class="container py-5 o_afenda_guide">')
        parts.append(body)
        parts.append("            </div>")
        parts.append("        </t>")
        parts.append("    </template>")
    parts.append("</odoo>")
    out_file.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    return len(pages)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=SRC)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    count = build(args.src, args.out)
    print(f"{count} guide(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
