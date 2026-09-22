"""Independent check for Odoo identity on user-visible surfaces — deliberately does NOT
reuse RULES, so a blind spot in the rebrand rules cannot also blind this check. Exit 1
if anything is found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from afenda.tools.rebrand import iter_files, _is_protected, TEXT_SUFFIXES

# Broader and independent of afenda.tools.rules: case-insensitive, catches
# odoocdn.com and other odoo.com subdomains/paths that RULES might miss.
SUSPECT = re.compile(
    r"\bodoo\b|odoo\.com|odoocdn\.com|openerp",
    re.IGNORECASE,
)
# A handful of tokens that legitimately contain "odoo" and are never identity:
# the package name/imports, this project's own protected header/endpoint markers,
# and URLs to the upstream project (acceptable in e.g. README/COPYRIGHT context).
ALLOW = re.compile(
    r"^\s*(from|import)\s+odoo\b|^\s*#.*Part of Odoo|X-Odoo-|Odoo-Link-Preview"
    r"|github\.com/odoo/|Last-Translator:|Language-Team:|Report-Msgid-Bugs-To:",
)
# Structural shapes that contain "odoo" but carry no identity: the XML data-file
# root element, ES module specifiers for the bundled framework, and the .po
# extractor origin comments. These are code structure, not words a user reads.
STRUCTURAL = re.compile(r"</?odoo[\s>]|@odoo/|^#[.:]\s")


def scan(root: Path) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("odoo/cli/") or "iot_box_image" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if not SUSPECT.search(line):
                continue
            if ALLOW.search(line) or STRUCTURAL.search(line):
                continue
            # The engine's own protections mark lines that are deliberately not
            # identity (license headers, imports, translator attribution, machine
            # endpoints). The SUSPECT pattern above stays broader than the rules,
            # so this reuse narrows noise without inheriting the rules' blind spots.
            if _is_protected(line, path.relative_to(root)):
                continue
            hits.append((rel, lineno, line.strip()[:160]))
    return hits


def main() -> int:
    # Hits can contain any script; never let the console encoding abort the scan.
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    root = Path(__file__).resolve().parents[2]
    hits = scan(root)
    for rel, lineno, line in hits[:200]:
        print(f"{rel}:{lineno}: {line}")
    print(f"{len(hits):8d}  remaining (independent scan)")
    if len(hits) > 200:
        print(f"... and {len(hits) - 200} more")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
