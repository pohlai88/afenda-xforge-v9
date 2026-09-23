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
CODE_SUFFIXES = frozenset({".py", ".js", ".ts", ".scss", ".css", ".template"})
PO_SUFFIXES = frozenset({".po", ".pot"})
# Where Odoo renders reStructuredText: READMEs, and the `description` in a
# manifest. See `repair_rst_underlines`.
RST_SUFFIXES = frozenset({".md", ".rst"})
RULE_CHARS = frozenset("=-~^`#*+_")

# Lines never rewritten, in any file.
PROTECTED_ALWAYS = re.compile(
    r"noqa: rebrand|X-Odoo-|Odoo-Link-Preview|Part of Odoo|Last-Translator:|Language-Team:|Report-Msgid-Bugs-To:"
)
# Machine service endpoints: protected only in Python source (API calls), not in
# templates/JS where the same text may appear as human-facing link text or hrefs.
PROTECTED_ENDPOINTS_PY = re.compile(r"iap\.odoo\.com|iap-services\.odoo\.com|services\.odoo\.com")
# Lines never rewritten in code files: license headers, imports, module loader.
PROTECTED_IN_CODE = re.compile(
    r"Part of Odoo|Copyright|^\s*(from|import)\s+[\w.]+(\s+import\s|$)|odoo\.define\(|require\("
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
    if "noqa: rebrand" in line:
        return True
    if path.suffix == ".py" and PROTECTED_ENDPOINTS_PY.search(line):
        return True
    if PROTECTED_ALWAYS.search(line):
        return True
    if path.suffix in CODE_SUFFIXES and PROTECTED_IN_CODE.search(line):
        return True
    if path.suffix in PO_SUFFIXES and not PO_TEXT_LINE.match(line):
        return True
    return False


def _is_rule_line(line: str) -> bool:
    """True if ``line`` is nothing but a run of one reStructuredText rule character.

    Quotes are deliberately NOT rule characters here. RST allows them, but in this
    tree a line of \"\"\" is a docstring terminator about a hundred times more often
    than it is a section rule, and treating one as the other would rewrite Python
    source. The repair below only ever runs where Odoo renders RST anyway; this is
    the second lock on the same door.
    """
    body = line.strip()
    return len(body) >= 3 and body[0] in RULE_CHARS and set(body) == {body[0]}


def repair_rst_underlines(lines: list[str], changed: set[int], markers: tuple[str, ...] = ()) -> int:
    """Re-pad the RST rule under any title this rewrite just lengthened.

    Odoo renders module descriptions and READMEs as reStructuredText, where a
    title's rule must be at least as long as the title. Substituting a longer
    product name into a heading lengthens the title and leaves the rule where it
    was, so docutils warns and the heading renders wrong in the Apps list.

    A title qualifies if this call just rewrote it, OR if it carries one of the
    literal strings the rules substitute in. Both are needed. The first alone
    would never fire on an already-converged tree - the titles say the new name
    already, so there is nothing left to substitute and the damage would sit
    there forever. The second alone would miss a title lengthened by a rule
    whose replacement it does not literally contain.

    That pairing is what keeps the repair to this transform's own collateral
    damage: a short rule that upstream shipped is upstream's business, and
    measured across addons/ and odoo/ there are none. Rules are only ever
    lengthened, never shortened.
    """
    fixed = 0
    candidates = set(changed)
    if markers:
        candidates.update(
            i for i, line in enumerate(lines) if any(m in line for m in markers))
    for i in sorted(candidates):
        if i + 1 >= len(lines):
            continue
        title, rule = lines[i].rstrip("\r\n"), lines[i + 1].rstrip("\r\n")
        body, mark = title.strip(), rule.strip()
        if not body or _is_rule_line(title) or not _is_rule_line(rule):
            continue
        if len(mark) >= len(body):
            continue
        pad = mark[0] * len(body)
        lines[i + 1] = pad + lines[i + 1][len(rule):]
        fixed += 1
        # A rule ABOVE the title is an overline. RST requires an overline and its
        # underline to be the same length; padding only the underline turns a
        # warning into a hard docutils error, so the pair moves together.
        if i and _is_rule_line(lines[i - 1]):
            over = lines[i - 1].rstrip("\r\n")
            if over.strip()[0] == mark[0] and len(over.strip()) == len(mark):
                lines[i - 1] = pad + lines[i - 1][len(over):]
    return fixed


def rewrite_text(text: str, rules: list[Rule], path: Path) -> tuple[str, dict[str, int]]:
    """Return (new_text, counts). counts maps rule name to replacements made."""
    counts: dict[str, int] = {}
    active = [r for r in rules if r.applies_to(path)]
    if not active:
        return text, counts
    out: list[str] = []
    changed: set[int] = set()
    for index, line in enumerate(text.splitlines(keepends=True)):
        if not _is_protected(line, path):
            for rule in active:
                line, n = rule.pattern.subn(rule.replacement, line)
                if n:
                    counts[rule.name] = counts.get(rule.name, 0) + n
                    changed.add(index)
        out.append(line)
    # Structural repair, after the substitutions rather than among them: a rule
    # sees one line at a time and an underline is only wrong relative to the line
    # above it, so this cannot be expressed as a Rule.
    if path.suffix in RST_SUFFIXES or path.name == "__manifest__.py":
        # The literals the rules put into the tree, so the repair can recognise a
        # title this transform lengthened on an earlier run. Replacements holding
        # a backreference are not literals and are skipped.
        markers = tuple(sorted({
            r.replacement for r in active
            if "\\" not in r.replacement and len(r.replacement) > 3
        }))
        n = repair_rst_underlines(out, changed, markers)
        if n:
            counts["rst_underline"] = counts.get("rst_underline", 0) + n
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
