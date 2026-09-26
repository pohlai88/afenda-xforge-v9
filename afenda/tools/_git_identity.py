# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""The one place that asks git "which tree is this?" for the local gates.

Three callers share it (docs/superpowers/specs/2026-09-26-local-first-gates.md,
"Corrections after review", item 5): `.claude/hooks/rerun_guard.py` (the
scoped fingerprint that keys its ledger), `afenda/tools/check.py` (the tree
sha a passing run stamps) and `.claude/hooks/push_gate.py` (the tree sha a
push must have a stamp for). One copy of the scoped path list and one git
timeout, so the three cannot drift.

The scope is `SCOPED_PATHS`. Root `odoo/` and `addons/` stay out on purpose:
a `[REBRAND]` apply leaves 23,291 modified files there, and a whole-tree
`git status` takes about two minutes. So a change only under `odoo/` or
`addons/` does not move the fingerprint and does not make the tree dirty.

Every git call runs with `timeout=GIT_TIMEOUT_SECONDS` (5 s). Any failure
(no git, not a repository, a non-zero exit, a timeout) raises
`GitIdentityError`, except `repo_root`, which returns None. Callers choose
their own polarity: the rerun guard fails open, the push gate fails closed.

Standard library only; Python 3.11+, Linux and Windows Git Bash.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

SCOPED_PATHS = ("afenda", ".github", ".claude", "docs", "CLAUDE.md", "deploy")
GIT_TIMEOUT_SECONDS = 5
STAMP_DIRNAME = "afenda-check"


class GitIdentityError(RuntimeError):
    """A git call failed, timed out, or printed nothing usable."""


def run_git(args, cwd, ok_returncodes=(0,)) -> str:
    """stdout of `git <args>` in `cwd`; raises GitIdentityError on any failure,
    including an exit code outside `ok_returncodes`."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GitIdentityError(f"git {' '.join(args)}: {error}") from error
    if result.returncode not in ok_returncodes:
        raise GitIdentityError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def repo_root(cwd) -> Path | None:
    """The work tree's top level, or None outside a repository or on any failure."""
    try:
        root = run_git(["rev-parse", "--show-toplevel"], cwd).strip()
    except GitIdentityError:
        return None
    return Path(root).resolve() if root else None


def git_common_dir(root) -> Path:
    """The `.git` directory every worktree of this repository shares."""
    common = run_git(["rev-parse", "--git-common-dir"], root).strip()
    if not common:
        raise GitIdentityError("git rev-parse --git-common-dir printed nothing")
    path = Path(common)
    if not path.is_absolute():
        path = Path(root) / path
    return path.resolve()


def rev_sha(root, rev: str) -> str:
    """The object id `rev` names; raises when it does not resolve."""
    sha = run_git(["rev-parse", "--verify", "--quiet", "--end-of-options", rev], root).strip()
    if not sha:
        raise GitIdentityError(f"{rev!r} does not resolve")
    return sha


def tree_sha(root, rev: str = "HEAD") -> str:
    """The tree of `rev` (a tag or commit is peeled to its tree)."""
    return rev_sha(root, f"{rev}^{{tree}}")


def scoped_fingerprint(root) -> str:
    """`<HEAD sha>:<sha256 of the scoped diff against HEAD and the scoped status>`."""
    head = rev_sha(root, "HEAD")
    diff = run_git(["diff", "HEAD", "--no-ext-diff", "--", *SCOPED_PATHS], root)
    status = run_git(["status", "--porcelain", "--", *SCOPED_PATHS], root)
    digest = hashlib.sha256((diff + status).encode("utf-8")).hexdigest()
    return f"{head}:{digest}"


def scoped_dirty(root) -> list[str]:
    """Tracked paths under SCOPED_PATHS with staged or unstaged changes, sorted."""
    out = run_git(
        ["status", "--porcelain=v1", "-z", "--untracked-files=no", "--", *SCOPED_PATHS],
        root,
    )
    entries = out.split("\0")
    paths = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":  # a rename or copy carries its source as the next entry
            index += 1
    return sorted(set(paths))


def stamp_path(root, tree: str) -> Path:
    """Where `check` records a passing run for `tree`."""
    return git_common_dir(root) / STAMP_DIRNAME / f"{tree}.json"


def has_passing_stamp(root, tree: str) -> bool:
    """True only for a readable stamp of this very tree that says it passed."""
    path = stamp_path(root, tree)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("tree") == tree and data.get("passed") is True
