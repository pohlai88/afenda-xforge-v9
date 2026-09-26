#!/usr/bin/env python3
"""PreToolUse hook: a gate cannot run a third time on an unchanged tree.

CLAUDE.md -> Execution discipline: "About to run the same command a third
time with no code change in between? Stop and report." This hook makes that
mechanical for Bash calls. It matches Claude Code's PreToolUse contract: JSON
on stdin with `tool_name`, `tool_input`, `session_id`, `cwd`; exit code 2
blocks the tool call and feeds stderr back to the model; exit 0 allows.

What counts as "the same run" (docs/superpowers/specs/2026-09-26-local-first-gates.md,
decision 3):

- **The gate's identity is semantic**, not its command text (`_gate_identities`):
  - `python -m unittest`: the sorted test targets, or the discover start
    directory, pattern and top level;
  - `odoo-bin` with `--test-enable`/`--test-tags`: the sorted `--test-tags` set;
  - `python -m afenda.tools.check`: its sorted `--gate` names (`--list` runs
    nothing and is not a gate);
  - `pytest` / `python -m pytest`: the sorted targets and any `-k`/`-m`;
  - `python -m afenda.tools.{api_diff,corpus,scan_identity,pr_evidence}`:
    the module and its arguments.
  Verbosity (`-v`, `-q`), `--failfast`, flag order, output redirections,
  pipes into `tail`/`tee`, leading `VAR=value` env prefixes and a
  backslash-newline continuation do not change it. A compound command
  (`a && b`) counts each gate in it.
- **A Bash call that holds a `git push` counts nothing** (`_contains_git_push`).
  The push gate blocks a push chained with anything else before any of it
  runs, so counting the gate in `check && git push` would spend runs that
  never happened and lock the tree out of `check` (sweep 2, H1); a push the
  gate allows is alone, so there is no gate in it to count.
- **The tree is the scoped fingerprint** from `afenda/tools/_git_identity.py`
  (HEAD plus a diff/status scoped to `_git_identity.SCOPED_PATHS`; an
  unscoped `git status` takes about two minutes on this tree).
- **One ledger per repository**, `<git common dir>/afenda-rerun-ledger.json`,
  keyed on `(gate identity, fingerprint)`, shared by every session and
  sub-agent, so a sub-agent inherits the count. Entries older than seven days
  are pruned on each write.

The same gate on the same unchanged tree is allowed twice and blocked the
third time; editing any fingerprinted path resets the count because the
fingerprint changes.

The fingerprint excludes root `odoo/` and `addons/`, so a `[REBRAND]` apply or
an upstream merge that only touches those trees does not move it. The run
right after one of those is legitimately new; cite that in the commit or PR
message, or proceed from a change under a fingerprinted path so the count
resets on its own.

A command that names no gate returns before any subprocess call: this hook
runs on every Bash call in every session, so a non-gate command must stay
cheap. Any failure -- malformed input, no git, not a repository, a slow git
call, the shared helper failing to import -- fails open (exit 0): this hook
must never be the reason real work is blocked. (The push gate,
`push_gate.py`, has the opposite polarity on purpose.)

Standard library only; runs on Python 3.11+, on Linux and Windows Git Bash.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Cheap prefilter on the raw text; only a match is parsed.
_MAYBE_GATE_RE = re.compile(
    r"-m\s+unittest\b|\bafenda\.tools\.(?:api_diff|corpus|scan_identity|pr_evidence|check)\b"
    r"|\bpy(?:\.)?test\b|\bodoo-bin\b"
)
_PLAIN_TOOL_MODULES = (
    "afenda.tools.api_diff",
    "afenda.tools.corpus",
    "afenda.tools.scan_identity",
    "afenda.tools.pr_evidence",
)
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_OPERATOR_CHARS = set("|&;<>()")
_HEREDOC_RE = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2")
_SHELL_WORD_RE = re.compile(r"(?:^|[\s/;&|(])(?:ba|z|da|k)?sh(?:\.exe)?(?=\s|$)")
# A line that ends in an unescaped backslash continues on the next one.
_CONTINUED_RE = re.compile(r"(?<!\\)(?:\\\\)*\\$")
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "bash.exe", "sh.exe"}
# git global options that take a separate value.
_GIT_VALUE_OPTIONS = {
    "-C", "-c", "--config-env", "--exec-path", "--super-prefix", "--git-dir", "--work-tree",
    "--namespace",
}
_VERBOSITY = {"-v", "-vv", "-vvv", "-q", "-qq", "--verbose", "--quiet"}
_UNITTEST_IGNORED = _VERBOSITY | {"-f", "--failfast", "-b", "--buffer", "-c", "--catch", "--locals"}

_LEDGER_DIR_ENV = "RERUN_GUARD_LEDGER_DIR"
_LEDGER_NAME = "afenda-rerun-ledger.json"
_BLOCK_AFTER = 2  # allowed twice, blocked on the third identical run.
_PRUNE_AFTER_SECONDS = 7 * 24 * 3600


def _load_git_identity():
    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from afenda.tools import _git_identity  # noqa: PLC0415

    return _git_identity


def _strip_heredoc_bodies(command: str) -> str:
    """Drop heredoc bodies (data such as a commit message that names a gate),
    except one fed to a shell (`bash <<EOF`), which is commands. The same
    rule as push_gate.py's, including its backslash-newline continuations."""
    kept, pending, carry = [], [], ""
    for raw in command.replace("\r\n", "\n").split("\n"):
        if pending:
            delimiter, strip_tabs, keep = pending[0]
            if (raw.lstrip("\t") if strip_tabs else raw).strip() == delimiter:
                pending.pop(0)
            elif keep:
                kept.append(raw)
            continue
        line = carry + raw
        if _CONTINUED_RE.search(line):
            carry = line[:-1] + " "
            continue
        carry = ""
        kept.append(line)
        for match in _HEREDOC_RE.finditer(line):
            feeds_shell = bool(_SHELL_WORD_RE.search(line[: match.start()]))
            pending.append((match.group(3), match.group(1) == "-", feeds_shell))
    if carry:
        kept.append(carry)
    return re.sub(r"\\\r?\n", " ", "\n".join(kept))


def _simple_commands(command: str) -> list[list[str]]:
    """argv of each simple command, redirections and env prefixes removed."""
    command = _strip_heredoc_bodies(command)
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    commands, current, skip_next = [], [], False
    for token in lexer:
        if skip_next:
            skip_next = False
            continue
        if token and set(token) <= _OPERATOR_CHARS:
            if token[0] in "<>" or token.startswith("&>"):
                if current and current[-1].isdigit():
                    current.pop()  # the fd of `2>&1`
                skip_next = True  # the redirection's target
                continue
            if current:
                commands.append(current)
            current = []
            continue
        current.append(token)
    if current:
        commands.append(current)
    result = []
    for argv in commands:
        while argv and _ENV_ASSIGNMENT_RE.match(argv[0]):
            argv = argv[1:]
        if argv:
            result.append(argv)
    return result


def _option_values(args, *names):
    """Values of `--name value` and `--name=value` options, in order."""
    values = []
    for index, arg in enumerate(args):
        for name in names:
            if arg == name and index + 1 < len(args):
                values.append(args[index + 1])
            elif arg.startswith(name + "="):
                values.append(arg[len(name) + 1:])
    return values


def _norm_path(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.rstrip("/") or "."


def _unittest_identity(args):
    rest, k_values, index = [], [], 0
    while index < len(args):
        arg = args[index]
        if arg in _UNITTEST_IGNORED:
            pass
        elif arg == "--durations":
            index += 1
        elif arg == "-k" and index + 1 < len(args):
            k_values.append(args[index + 1])
            index += 1
        else:
            rest.append(arg)
        index += 1
    k_part = "".join(f" -k {value}" for value in sorted(set(k_values)))
    if not rest or rest[0] == "discover":
        discover = rest[1:]
        start = (_option_values(discover, "-s", "--start-directory") or [None])[0]
        pattern = (_option_values(discover, "-p", "--pattern") or [None])[0]
        top = (_option_values(discover, "-t", "--top-level-directory") or [None])[0]
        positional, skip = [], False
        for arg in discover:
            if skip:
                skip = False
            elif arg in ("-s", "--start-directory", "-p", "--pattern", "-t", "--top-level-directory"):
                skip = True
            elif not arg.startswith("-"):
                positional.append(arg)
        positional += [None, None, None]
        start = start or positional[0] or "."
        pattern = pattern or positional[1] or "test*.py"
        top = top or positional[2] or ""
        return f"unittest discover {_norm_path(start)} {pattern} {top}{k_part}".rstrip()
    targets = sorted({_norm_path(arg) if "/" in arg else arg for arg in rest})
    return "unittest " + " ".join(targets) + k_part


def _pytest_identity(args):
    keep, targets, index = [], [], 0
    while index < len(args):
        arg = args[index]
        if arg in ("-k", "-m") and index + 1 < len(args):
            keep.append(f"{arg} {args[index + 1]}")
            index += 1
        elif arg in ("-p", "--tb", "-c", "--rootdir", "--maxfail", "--durations", "-o"):
            index += 1
        elif not arg.startswith("-"):
            targets.append(_norm_path(arg))
        index += 1
    return "pytest " + " ".join(sorted(set(targets)) + sorted(set(keep)))


def _odoo_identity(argv):
    tags = set()
    for value in _option_values(argv, "--test-tags"):
        tags.update(tag.strip() for tag in value.split(",") if tag.strip())
    if tags:
        return "odoo-bin --test-tags " + ",".join(sorted(tags))
    modules = set()
    for value in _option_values(argv, "-i", "--init", "-u", "--update"):
        modules.update(name.strip() for name in value.split(",") if name.strip())
    return "odoo-bin untagged " + ",".join(sorted(modules))


def _identity(argv):
    """The semantic gate identity of one simple command, or None."""
    names = [arg.replace("\\", "/").rsplit("/", 1)[-1] for arg in argv]
    if "odoo-bin" in names and ("--test-enable" in argv or _option_values(argv, "--test-tags")):
        return _odoo_identity(argv)
    for index, arg in enumerate(argv[:-1]):
        # `-m` of a Python interpreter, not of e.g. `git commit -m unittest`.
        if arg != "-m" or not any(name.startswith("py") for name in names[:index]):
            continue
        module, args = argv[index + 1], argv[index + 2:]
        if module == "unittest":
            return _unittest_identity(args)
        if module == "pytest":
            return _pytest_identity(args)
        if module == "afenda.tools.check":
            if "--list" in args:
                return None
            gates = sorted(set(_option_values(args, "--gate")))
            return "afenda.tools.check " + (" ".join(gates) if gates else "<selected>")
        if module in _PLAIN_TOOL_MODULES:
            return " ".join([module, *(a for a in args if a not in _VERBOSITY)])
        return None
    if names[0] in ("pytest", "py.test"):  # the command itself, not an argument
        return _pytest_identity(argv[1:])
    return None


def _basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1]


def _contains_git_push(command: str, depth: int = 0) -> bool:
    """True when any simple command names `git` followed (after git's global
    options) by `push`, also inside a `bash -c` / `eval` script. Deliberately
    broad: a false True only skips counting (fail-open)."""
    for argv in _simple_commands(command):
        for index, token in enumerate(argv):
            name = _basename(token)
            if name in ("git", "git.exe"):
                position = index + 1
                while position < len(argv) and argv[position].startswith("-"):
                    position += 2 if argv[position] in _GIT_VALUE_OPTIONS else 1
                if position < len(argv) and argv[position] == "push":
                    return True
            elif (name in _SHELLS or name == "eval") and depth < 4:
                if _contains_git_push(" ".join(argv[index + 1:]), depth + 1):
                    return True
    return False


def _gate_identities(command: str) -> list[str]:
    identities = []
    for argv in _simple_commands(command):
        identity = _identity(argv)
        if identity and identity not in identities:
            identities.append(identity)
    return identities


def _load_ledger(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_ledger(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)
    tmp_path.replace(path)


def main(stdin_text: str, env: dict) -> tuple:
    """Returns (exit_code, stderr_text). Never raises: any internal error is
    caught and treated as fail-open (0, "")."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
            return 0, ""
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0, ""
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return 0, ""

        if not _MAYBE_GATE_RE.search(command):
            return 0, ""
        identities = _gate_identities(command)
        if not identities or _contains_git_push(command):
            return 0, ""

        # From here on this is a gate: git calls are in scope.
        git_identity = _load_git_identity()
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        root = git_identity.repo_root(cwd)
        if root is None:
            return 0, ""
        fingerprint = git_identity.scoped_fingerprint(root)

        override = env.get(_LEDGER_DIR_ENV)
        base_dir = Path(override) if override else git_identity.git_common_dir(root)
        ledger_path = base_dir / _LEDGER_NAME
        ledger = _load_ledger(ledger_path)

        now = time.time()
        ledger = {
            key: entry for key, entry in ledger.items()
            if isinstance(entry, dict)
            and isinstance(entry.get("time"), (int, float))
            and now - entry["time"] <= _PRUNE_AFTER_SECONDS
        }

        keys = {
            identity: hashlib.sha256(f"{identity}\x00{fingerprint}".encode()).hexdigest()
            for identity in identities
        }
        for identity, key in keys.items():
            count = ledger.get(key, {}).get("count", 0)
            if isinstance(count, int) and count >= _BLOCK_AFTER:
                normalised_command = " ".join(command.split())
                head = fingerprint.split(":", 1)[0][:8]
                message = (
                    f'rerun-guard: "{normalised_command}" would run the gate '
                    f"`{identity}` a third time on this unchanged tree (HEAD {head}); "
                    "every session and sub-agent in this repository share the count. "
                    "CLAUDE.md → Execution discipline: cite the earlier printed "
                    "count, or change code first, or stop and report."
                )
                return 2, message

        for identity, key in keys.items():
            count = ledger.get(key, {}).get("count", 0)
            ledger[key] = {
                "count": (count if isinstance(count, int) else 0) + 1,
                "time": now,
                "gate": identity,
            }
        _save_ledger(ledger_path, ledger)
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
