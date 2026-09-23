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

# Known remaining hits on the current tree. NOT zero by design: phase 1
# deliberately leaves identity where rewriting it would break something —
# translator attribution in .po headers, the `odoo` package name in imports,
# API payload identifiers third parties have registered, and spreadsheet
# formula names like ODOO.PIVOT that live in saved documents. Those are
# covered by the engine's protections, not by this scan, which stays broader
# on purpose so a blind spot in the rules cannot also blind the check.
#
# The gate is that this number must not RISE. If a change legitimately lowers
# it, lower this constant in the same commit so the new floor is what holds.
BASELINE = 10826


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


def verdict(count: int, baseline: int = BASELINE) -> int:
    """Exit status for a scan: 0 while the count holds at or below the baseline."""
    return 1 if count > baseline else 0


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
    if len(hits) > 200:
        print(f"... and {len(hits) - 200} more")
    count = len(hits)
    delta = count - BASELINE
    print(f"{count:8d}  remaining (independent scan), baseline {BASELINE}, delta {delta:+d}")
    if delta > 0:
        print(f"FAIL: {delta} new identity hit(s) since the baseline.")
    elif delta < 0:
        print(f"OK: {-delta} fewer than the baseline — lower BASELINE to {count} to hold the new floor.")
    else:
        print("OK: holding at the baseline.")
    return verdict(count)


if __name__ == "__main__":
    sys.exit(main())
