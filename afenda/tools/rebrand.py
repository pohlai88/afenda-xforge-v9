"""Rewrite Odoo identity in the upstream tree by rules.

Usage (from the repository root):
    python -m afenda.tools.rebrand            # dry run: per-rule counts
    python -m afenda.tools.rebrand --apply    # write changes

Only ``addons/`` and ``odoo/`` are scanned; ``afenda/`` is never touched.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SCAN_DIRS = ("addons", "odoo")
SKIP_DIRS = {".git", ".venv", "afenda", "node_modules", "__pycache__", "docs"}
TEXT_SUFFIXES = frozenset({
    ".py", ".js", ".ts", ".xml", ".html", ".md", ".rst", ".txt", ".po", ".pot",
    ".scss", ".css", ".json", ".csv", ".template", ".cfg", ".conf", ".ini",
    ".yml", ".yaml", ".sh", ".sql",
})
CODE_SUFFIXES = frozenset({".py", ".js", ".ts", ".scss", ".css"})
PO_SUFFIXES = frozenset({".po", ".pot"})

# Lines never rewritten, in any file.
PROTECTED_ALWAYS = re.compile(
    r"noqa: rebrand|X-Odoo-|iap\.odoo\.com|iap-services\.odoo\.com|services\.odoo\.com"
)
# Lines never rewritten in code files: license headers, imports, module loader.
PROTECTED_IN_CODE = re.compile(
    r"Part of Odoo|Copyright|^\s*(from|import)\s|odoo\.define\(|require\("
)
# In .po files only these lines carry user-visible text.
PO_TEXT_LINE = re.compile(r'^(msgid |msgstr|msgid_plural |")')


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    replacement: str
    suffixes: frozenset[str] | None = None
    path_contains: tuple[str, ...] = ()
    path_excludes: tuple[str, ...] = ()

    def applies_to(self, path: Path) -> bool:
        posix = path.as_posix()
        if self.suffixes is not None and path.suffix not in self.suffixes:
            return False
        if self.path_contains and not any(s in posix for s in self.path_contains):
            return False
        if any(s in posix for s in self.path_excludes):
            return False
        return True


def _is_protected(line: str, path: Path) -> bool:
    if PROTECTED_ALWAYS.search(line):
        return True
    if path.suffix in CODE_SUFFIXES and PROTECTED_IN_CODE.search(line):
        return True
    if path.suffix in PO_SUFFIXES and not PO_TEXT_LINE.match(line):
        return True
    return False


def rewrite_text(text: str, rules: list[Rule], path: Path) -> tuple[str, dict[str, int]]:
    """Return (new_text, counts). counts maps rule name to replacements made."""
    counts: dict[str, int] = {}
    active = [r for r in rules if r.applies_to(path)]
    if not active:
        return text, counts
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if not _is_protected(line, path):
            for rule in active:
                line, n = rule.pattern.subn(rule.replacement, line)
                if n:
                    counts[rule.name] = counts.get(rule.name, 0) + n
        out.append(line)
    return "".join(out), counts


def iter_files(root: Path) -> Iterator[Path]:
    for top in SCAN_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                yield path


def run(root: Path, rules: list[Rule], apply: bool) -> dict[str, int]:
    totals: dict[str, int] = {}
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text, counts = rewrite_text(text, rules, path.relative_to(root))
        for name, n in counts.items():
            totals[name] = totals.get(name, 0) + n
        if apply and counts:
            path.write_text(new_text, encoding="utf-8", newline="")
    return totals


def main(argv: list[str] | None = None) -> int:
    from afenda.tools.rules import RULES

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    totals = run(args.root, RULES, apply=args.apply)
    mode = "applied" if args.apply else "would apply"
    for name, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"{n:8d}  {name}")
    print(f"{sum(totals.values()):8d}  total ({mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
