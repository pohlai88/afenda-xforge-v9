"""Corpus of every distinct line the rebrand rules could touch, with a golden rewrite.

    python -m afenda.tools.corpus build --ref upstream-19.0   # corpus.txt from pristine tree
    python -m afenda.tools.corpus golden                       # golden.txt from corpus.txt + RULES
    python -m afenda.tools.corpus diff                         # show what current RULES change vs golden

Lines are keyed by (suffix, path kind) because rules depend on both.
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path

from afenda.tools.rebrand import iter_files, rewrite_text

HERE = Path(__file__).resolve().parent
CORPUS_DIR = HERE / "tests" / "corpus"
CORPUS = CORPUS_DIR / "corpus.txt"
GOLDEN = CORPUS_DIR / "golden.txt"

TRIGGER = re.compile(r"Odoo|odoo\.com|/odoo|%2Fodoo", re.IGNORECASE)
# Path kinds that rules key on. Keep in sync with rules.py path_contains/path_excludes.
KINDS = {
    "router": "addons/web/static/src/core/browser/router.js",
    "iot": "addons/iot_box_image/x",
    "cli": "odoo/cli/x",
    "other": "addons/m/x",
}
PO_MSGSTR_CAP = 2000  # translations are near-duplicates across languages; sample them


def kind_of(rel: str) -> str:
    if rel.endswith("core/browser/router.js"):
        return "router"
    if "iot_box_image" in rel:
        return "iot"
    if rel.startswith("odoo/cli/"):
        return "cli"
    return "other"


def synthetic_path(suffix: str, kind: str) -> Path:
    return Path(KINDS[kind] + suffix)


def build(ref: str, out: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        archive = root / "tree.tar"
        with archive.open("wb") as fh:
            subprocess.run(["git", "archive", ref, "addons", "odoo"], check=True, stdout=fh)
        with tarfile.open(archive) as tar:
            tar.extractall(root)
        archive.unlink()
        seen: set[tuple[str, str, str]] = set()
        msgstr_count: dict[str, int] = defaultdict(int)
        lines: list[str] = []
        for path in iter_files(root):
            rel = path.relative_to(root).as_posix()
            kind, suffix = kind_of(rel), path.suffix
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for raw in text.splitlines():
                if not TRIGGER.search(raw):
                    continue
                line = raw.strip()
                if suffix in (".po", ".pot") and line.startswith("msgstr"):
                    if msgstr_count[suffix] >= PO_MSGSTR_CAP:
                        continue
                    msgstr_count[suffix] += 1
                key = (suffix, kind, line)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"{suffix}\t{kind}\t{line}")
    lines.sort()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(lines)


def rewrite_corpus(corpus_text: str, rules) -> str:
    out = []
    for entry in corpus_text.splitlines():
        suffix, kind, line = entry.split("\t", 2)
        new, _ = rewrite_text(line + "\n", rules, synthetic_path(suffix, kind))
        out.append(f"{suffix}\t{kind}\t{new.rstrip(chr(10))}")
    return "\n".join(out) + "\n"


def emit_utf8(text: str, stream=None) -> None:
    """Write ``text`` to ``stream`` (default ``sys.stdout``) as UTF-8 bytes.

    The corpus holds non-Latin text (rule rewrites of translated strings), but a
    Windows console's ``sys.stdout`` is typically opened with the cp1252 codec, whose
    ``.write()`` raises ``UnicodeEncodeError`` on anything outside Latin-1. Rather than
    relaxing that encoding (which would require ``errors="replace"`` and silently mangle
    the very text a reviewer is trying to read), write UTF-8 bytes straight to the
    stream's underlying binary buffer, bypassing its text encoding entirely. Streams with
    no ``.buffer`` (e.g. ``io.StringIO`` in tests) fall back to a plain text write, where
    no encoding translation happens anyway.
    """
    stream = sys.stdout if stream is None else stream
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:
        stream.write(text)


def main(argv: list[str] | None = None) -> int:
    from afenda.tools.rules import RULES

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--ref", default="upstream-19.0")
    sub.add_parser("golden")
    sub.add_parser("diff")
    args = parser.parse_args(argv)
    if args.cmd == "build":
        n = build(args.ref, CORPUS)
        print(f"{n} corpus lines -> {CORPUS}")
        return 0
    corpus = CORPUS.read_text(encoding="utf-8")
    rewritten = rewrite_corpus(corpus, RULES)
    if args.cmd == "golden":
        GOLDEN.write_text(rewritten, encoding="utf-8", newline="\n")
        changed = sum(1 for a, b in zip(corpus.splitlines(), rewritten.splitlines()) if a != b)
        print(f"golden written: {changed} of {len(corpus.splitlines())} lines rewritten")
        return 0
    golden = GOLDEN.read_text(encoding="utf-8") if GOLDEN.exists() else ""
    diff = list(difflib.unified_diff(golden.splitlines(), rewritten.splitlines(), "golden", "current", lineterm="", n=0))
    emit_utf8("\n".join(diff[:400]) + ("\n" if diff else "no changes vs golden\n"))
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
