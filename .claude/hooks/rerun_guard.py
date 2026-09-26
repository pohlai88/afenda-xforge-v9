#!/usr/bin/env python3
"""PreToolUse hook: a gate command cannot run a third time on an unchanged tree.

CLAUDE.md -> Execution discipline: "About to run the same command a third
time with no code change in between? Stop and report." This hook makes that
mechanical for Bash calls. It matches Claude Code's PreToolUse contract: JSON
on stdin with `tool_name`, `tool_input`, `session_id`, `cwd`; exit code 2
blocks the tool call and feeds stderr back to the model; exit 0 allows.

A "gate command" is a test suite, `api_diff`, `corpus`, `scan_identity` or
`pr_evidence` invocation (see `_is_gate_command`). Everything else returns
immediately, before any subprocess call: this hook runs on every Bash call in
every session, so a non-gate command must stay cheap.

For a gate command, the hook fingerprints the working tree (`HEAD` plus a
diff/status scoped to the paths that matter: `afenda .github .claude docs
CLAUDE.md deploy` -- an unscoped `git status` takes about two minutes on this
tree) and keys a per-session ledger on the session id, the whitespace-
normalised command text, and that fingerprint. The same command on the same
unchanged tree is allowed twice and blocked the third time; editing any
fingerprinted path resets the count because the fingerprint changes.

Any failure -- malformed input, no git, not a repository, a slow git call --
fails open (exit 0): this hook must never be the reason real work is blocked.

Standard library only; runs on Python 3.11+, on Linux and Windows Git Bash.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Gate patterns, case-sensitive, matched against the raw command text.
_GATE_PATTERNS = (
    re.compile(r"\bunittest\b"),
    re.compile(r"\bafenda\.tools\.api_diff\b"),
    re.compile(r"\bafenda\.tools\.corpus\b"),
    re.compile(r"\bafenda\.tools\.scan_identity\b"),
    re.compile(r"\bafenda\.tools\.pr_evidence\b"),
)
# odoo-bin is a gate command only together with --test-enable.
_ODOO_BIN_RE = re.compile(r"\bodoo-bin\b")
_TEST_ENABLE_RE = re.compile(r"--test-enable\b")

# Fingerprint scope: matches CLAUDE.md's Lane A spec exactly.
_FINGERPRINT_PATHS = ("afenda", ".github", ".claude", "docs", "CLAUDE.md", "deploy")

_LEDGER_DIR_ENV = "RERUN_GUARD_LEDGER_DIR"
_LEDGER_SUBDIR = Path(".claude") / ".rerun-ledger"
_GIT_TIMEOUT_SECONDS = 5
_BLOCK_AFTER = 2  # allowed twice, blocked on the third identical run.


def _is_gate_command(command: str) -> bool:
    if _ODOO_BIN_RE.search(command) and _TEST_ENABLE_RE.search(command):
        return True
    return any(pattern.search(command) for pattern in _GATE_PATTERNS)


def _run_git(args, cwd):
    """Run a git subcommand; return CompletedProcess, or None on any failure
    (missing git, not a repo, timeout) so callers can fail open uniformly."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _repo_root(cwd: str):
    result = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if result is None or result.returncode != 0:
        return None
    root = result.stdout.strip()
    return root or None


def _fingerprint(repo_root: str):
    """(HEAD sha, sha256 of the scoped diff+status), or None on any failure."""
    head = _run_git(["rev-parse", "HEAD"], repo_root)
    if head is None or head.returncode != 0:
        return None
    head_sha = head.stdout.strip()
    if not head_sha:
        return None

    diff_result = _run_git(
        ["diff", "HEAD", "--no-ext-diff", "--", *_FINGERPRINT_PATHS], repo_root
    )
    status_result = _run_git(
        ["status", "--porcelain", "--", *_FINGERPRINT_PATHS], repo_root
    )
    if diff_result is None or status_result is None:
        return None
    if diff_result.returncode != 0 or status_result.returncode != 0:
        return None

    tree_hash = hashlib.sha256(
        (diff_result.stdout + status_result.stdout).encode("utf-8")
    ).hexdigest()
    return head_sha, tree_hash


def _ledger_paths(repo_root: str, session_id: str, env: dict):
    override = env.get(_LEDGER_DIR_ENV)
    base_dir = Path(override) if override else Path(repo_root) / _LEDGER_SUBDIR
    safe_session = session_id.replace("/", "_").replace("\\", "_")
    return base_dir, base_dir / f"{safe_session}.json"


def _load_ledger(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_ledger(base_dir: Path, path: Path, data: dict) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)
    tmp_path.replace(path)


def main(stdin_text: str, env: dict) -> tuple:
    """Returns (exit_code, stderr_text). Never raises: any internal error is
    caught and treated as fail-open (0, "")."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            return 0, ""

        if payload.get("tool_name") != "Bash":
            return 0, ""

        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0, ""
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return 0, ""

        if not _is_gate_command(command):
            return 0, ""

        # From here on this is a gate command: git calls are in scope.
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            session_id = "unknown-session"
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()

        repo_root = _repo_root(cwd)
        if not repo_root:
            return 0, ""

        fingerprint = _fingerprint(repo_root)
        if fingerprint is None:
            return 0, ""
        head_sha, tree_hash = fingerprint

        normalised_command = " ".join(command.split())
        key = hashlib.sha256(
            "\x00".join([session_id, normalised_command, head_sha, tree_hash]).encode(
                "utf-8"
            )
        ).hexdigest()

        base_dir, ledger_path = _ledger_paths(repo_root, session_id, env)
        ledger = _load_ledger(ledger_path)
        count = ledger.get(key, 0)
        if not isinstance(count, int):
            count = 0

        if count >= _BLOCK_AFTER:
            short_sha = head_sha[:8]
            message = (
                f'rerun-guard: "{normalised_command}" has already run twice in '
                f"this session on this unchanged tree (HEAD {short_sha}). "
                "CLAUDE.md → Execution discipline: cite the earlier printed "
                "count, or change code first, or stop and report."
            )
            return 2, message

        ledger[key] = count + 1
        _save_ledger(base_dir, ledger_path, ledger)
        return 0, ""
    except Exception:
        # Fail open: this hook must never be the reason real work is blocked.
        return 0, ""


if __name__ == "__main__":
    _stdin_text = sys.stdin.read()
    _exit_code, _stderr_text = main(_stdin_text, dict(os.environ))
    if _stderr_text:
        sys.stderr.write(_stderr_text)
    sys.exit(_exit_code)
