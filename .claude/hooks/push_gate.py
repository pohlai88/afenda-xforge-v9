#!/usr/bin/env python3
"""PreToolUse hook: no `git push` of a tree that `afenda.tools.check` has not passed.

docs/superpowers/specs/2026-09-26-local-first-gates.md, decision 2 and
"Corrections after review" 1-4. Claude Code's PreToolUse contract: JSON on
stdin with `tool_name`, `tool_input`, `cwd`; exit code 2 blocks the call and
feeds stderr back to the model. Any other exit code, and a hook timeout, do
NOT block (code.claude.com/docs/en/hooks), so this hook fails closed by its
own code: every git call has a 5 s timeout (`afenda/tools/_git_identity.py`),
and any exception, parse failure or unresolvable ref returns 2.

What it does:

- **`git push`** in a Bash command (also after `cd`, `&&`, `;`, `|`, env
  prefixes, `env`/`command`/`exec` wrappers, `git -C <path>`, `bash -c '...'`
  and `eval`): each refspec is resolved with `git rev-parse` to its tip commit's
  tree, and that tree must have a passing stamp,
  `<git common dir>/afenda-check/<tree sha>.json`, written by
  `python -m afenda.tools.check`. Only the tip tree of each pushed ref is
  checked, not every commit in the push.
  - Resolved forms: bare `git push` and `git push <remote>` (the current
    branch; a detached HEAD, `push.default=matching` or configured
    `remote.*.push` refspecs are blocked), `HEAD`, `<src>:<dst>`,
    `<sha>:<dst>`, `+<ref>`, `tag <name>`; `--force`, `--force-with-lease[=…]`
    and `--no-verify` change nothing.
  - Needs no stamp: `--dry-run`/`-n`; `--delete`/`-d` and `:<dst>` deletes;
    a tag pushed as a tag (`v1`, `refs/tags/v1[:refs/tags/…]`, `tag v1`,
    `--tags` alone). A tag pushed onto a branch needs one.
  - Blocked outright: `--all`, `--branches`, `--mirror`, wildcard refspecs,
    `--git-dir`/`--work-tree`/`--namespace` or a `GIT_DIR`-style env prefix,
    anything that does not resolve, and a command that mentions `push` but
    does not parse.
- **The GitHub file-writing MCP tools** (`BLOCKED_MCP_TOOLS`) are always
  blocked: they write commits without git and would route around this gate.
  Agents push with git.

No bypass inside the hook: no environment variable or flag switches it off.
Residual risk, named (spec correction 2 and 4): `disableAllHooks` or a
`--settings` override switches every hook off; a git alias, wrapper script,
Makefile target, `xargs`, or a raw `curl`/`gh api` write to GitHub is not a
`git push` this hook can see. Branch protection's required status checks on
`main` are the backstop for all of those.

Standard library plus `afenda/tools/_git_identity.py`, imported only once a
push is found, so every other Bash call stays cheap.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

BLOCKED_MCP_TOOLS = (
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
    "mcp__github__delete_file",
)
CHECK_COMMAND = "python -m afenda.tools.check"

_PUSH_RE = re.compile(r"\bpush\b")
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GIT_ENV_RE = re.compile(r"^GIT_(DIR|WORK_TREE|COMMON_DIR|NAMESPACE|INDEX_FILE)=")
_OPERATOR_CHARS = set("|&;<>()")
_HEREDOC_RE = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2")
_SHELL_WORD_RE = re.compile(r"(?:^|[\s/;&|(])(?:ba|z|da|k)?sh(?:\.exe)?(?=\s|$)")
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "bash.exe", "sh.exe"}
_WRAPPERS = {"command", "exec", "nohup", "time", "builtin", "sudo", "nice", "stdbuf"}
_MAX_DEPTH = 4

# git global options that take a separate value.
_GIT_VALUE_OPTIONS = {"-c", "--config-env", "--exec-path", "--super-prefix"}
_GIT_UNSUPPORTED = ("--git-dir", "--work-tree", "--namespace")
# git push options that take a separate value (unless given as `--opt=value`).
_PUSH_VALUE_OPTIONS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


class _Blocked(Exception):
    """A push form this hook refuses to guess about."""


def _load_git_identity():
    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from afenda.tools import _git_identity  # noqa: PLC0415

    return _git_identity


def _basename(token: str) -> str:
    return token.lstrip("`").replace("\\", "/").rsplit("/", 1)[-1]


def _strip_heredoc_bodies(command: str) -> str:
    """Drop heredoc bodies (data such as a commit message, not shell syntax),
    except one fed to a shell (`bash <<EOF`), which is commands."""
    lines, kept, pending = command.split("\n"), [], []
    for line in lines:
        if pending:
            delimiter, strip_tabs, keep = pending[0]
            if (line.lstrip("\t") if strip_tabs else line).strip() == delimiter:
                pending.pop(0)
            elif keep:
                kept.append(line)
            continue
        kept.append(line)
        for match in _HEREDOC_RE.finditer(line):
            feeds_shell = bool(_SHELL_WORD_RE.search(line[: match.start()]))
            pending.append((match.group(3), match.group(1) == "-", feeds_shell))
    return "\n".join(kept)


def _simple_commands(command: str) -> list[list[str]]:
    """argv of each simple command, in order; redirections removed."""
    command = _strip_heredoc_bodies(command)
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    commands, current, skip_next = [], [], False
    for token in lexer:  # an unbalanced quote raises ValueError: fail closed upstream
        if skip_next:
            skip_next = False
            continue
        if token and set(token) <= _OPERATOR_CHARS:
            if token[0] in "<>" or token.startswith("&>"):
                if current and current[-1].isdigit():
                    current.pop()
                skip_next = True
                continue
            if current:
                commands.append(current)
            current = []
            continue
        current.append(token)
    if current:
        commands.append(current)
    return commands


def _strip_prefixes(argv):
    """Drop env assignments and wrapper commands in front of the real command."""
    while argv:
        head = argv[0]
        if _ENV_ASSIGNMENT_RE.match(head):
            if _GIT_ENV_RE.match(head):
                raise _Blocked(f"`{head.split('=', 1)[0]}` points git elsewhere; push without it")
            argv = argv[1:]
        elif _basename(head) == "env":
            argv = argv[1:]
            while argv and (argv[0].startswith("-") or _ENV_ASSIGNMENT_RE.match(argv[0])):
                if _GIT_ENV_RE.match(argv[0]):
                    raise _Blocked(f"`{argv[0].split('=', 1)[0]}` points git elsewhere; push without it")
                argv = argv[1:]
        elif _basename(head) in _WRAPPERS:
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = argv[1:]
        elif _basename(head) == "timeout":
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = argv[1:]
            argv = argv[1:]  # the duration
        else:
            break
    return argv


def _find_pushes(command: str, cwd: str, depth: int = 0):
    """[(cwd, push arguments)] for every `git push` in `command`."""
    if depth > _MAX_DEPTH:
        raise _Blocked("the command nests shells too deeply to read")
    pushes = []
    for argv in _simple_commands(command):
        argv = _strip_prefixes(argv)
        if not argv:
            continue
        name = _basename(argv[0])
        if name in ("cd", "pushd"):
            target = argv[1] if len(argv) > 1 else os.path.expanduser("~")
            if target == "-":
                cwd = None
            elif cwd is not None:
                cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
            continue
        if name in _SHELLS and "-c" in argv[1:]:
            index = argv.index("-c")
            if index + 1 < len(argv):
                pushes += _find_pushes(argv[index + 1], cwd, depth + 1)
            continue
        if name == "eval":
            pushes += _find_pushes(" ".join(argv[1:]), cwd, depth + 1)
            continue
        if name not in ("git", "git.exe"):
            continue
        git_cwd, index = cwd, 1
        subcommand = None
        while index < len(argv):
            arg = argv[index]
            if arg == "-C" and index + 1 < len(argv):
                if git_cwd is not None:
                    git_cwd = os.path.normpath(os.path.join(git_cwd, argv[index + 1]))
                index += 2
            elif arg.startswith(_GIT_UNSUPPORTED):
                raise _Blocked(f"`git {arg}` is not a form this gate resolves; use `git -C <path>`")
            elif arg in _GIT_VALUE_OPTIONS:
                index += 2
            elif arg.startswith("-"):
                index += 1
            else:
                subcommand = arg
                break
        if subcommand == "push":
            if git_cwd is None:
                raise _Blocked("`cd -` before the push leaves the directory unknown")
            pushes.append((git_cwd, argv[index + 1:]))
    return pushes


def _parse_push_args(args):
    flags, positional, index = set(), [], 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positional += args[index + 1:]
            break
        if arg.startswith("--"):
            name = arg.split("=", 1)[0]
            flags.add(name)
            if arg in _PUSH_VALUE_OPTIONS:
                index += 1
        elif arg.startswith("-") and len(arg) > 1:
            for position, char in enumerate(arg[1:], start=1):
                if char == "o":
                    if position == len(arg) - 1:
                        index += 1
                    break
                flags.add(f"-{char}")
        else:
            positional.append(arg)
        index += 1
    return flags, positional


def _evaluate(git_identity, cwd, args):
    """None when this push may go, else the reason it may not."""
    root = git_identity.repo_root(cwd)
    if root is None:
        return f"{cwd} is not inside a git repository"
    flags, positional = _parse_push_args(args)
    if flags & {"--dry-run", "-n"}:
        return None
    if flags & {"--all", "--branches", "--mirror"}:
        return "`--all`/`--branches`/`--mirror` push many refs at once; push one branch"
    if flags & {"--delete", "-d"}:
        return None

    refspecs = []
    specs = positional[1:]
    index = 0
    while index < len(specs):
        if specs[index] == "tag" and index + 1 < len(specs):
            refspecs.append(f"refs/tags/{specs[index + 1]}")
            index += 2
        else:
            refspecs.append(specs[index])
            index += 1

    if not refspecs:
        if "--tags" in flags:
            return None
        config = git_identity.run_git(
            ["config", "--get-regexp", r"^(push\.default|remote\..*\.push)$"], root, ok_returncodes=(0, 1)
        )
        for line in config.splitlines():
            key, _, value = line.partition(" ")
            if key.endswith(".push"):
                return f"`{key}` configures push refspecs; name the refspec explicitly"
            if key == "push.default" and value.strip() == "matching":
                return "`push.default=matching` pushes every matching branch; name the refspec explicitly"
        branch = git_identity.run_git(["symbolic-ref", "-q", "HEAD"], root, ok_returncodes=(0, 1)).strip()
        if not branch:
            return "HEAD is detached, so a bare `git push` has no branch to push"
        refspecs = ["HEAD"]

    for spec in refspecs:
        src, sep, dst = spec[1:].partition(":") if spec.startswith("+") else spec.partition(":")
        if "*" in spec:
            return f"`{spec}` is a wildcard refspec; push named refs"
        if sep and not src:
            continue  # `:dst` deletes dst
        full_name = git_identity.run_git(
            ["rev-parse", "--verify", "--quiet", "--symbolic-full-name", "--end-of-options", src],
            root, ok_returncodes=(0, 1),
        ).strip()
        if full_name.startswith("refs/tags/") and (not dst or dst.startswith("refs/tags/")):
            continue  # a tag pushed as a tag
        try:
            tree = git_identity.tree_sha(root, src)
        except git_identity.GitIdentityError:
            return f"`{src}` does not resolve to a commit here"
        if not git_identity.has_passing_stamp(root, tree):
            return f"`{src}` (tree {tree[:12]}) has no passing check stamp"
    return None


def _check_push(command: str, cwd: str):
    try:
        pushes = _find_pushes(command, cwd)
    except ValueError as error:
        return 2, (
            f"push-gate: blocked; the command mentions `push` but does not parse ({error}). "
            "Write the `git push` as its own plain command."
        )
    except _Blocked as error:
        return 2, f"push-gate: blocked; {error}."
    if not pushes:
        return 0, ""
    git_identity = _load_git_identity()
    for push_cwd, args in pushes:
        try:
            reason = _evaluate(git_identity, push_cwd, args)
        except git_identity.GitIdentityError as error:
            reason = f"git could not answer ({error})"
        if reason:
            return 2, (
                f"push-gate: blocked `git push {' '.join(args)}`: {reason}. "
                f"Commit, run `{CHECK_COMMAND}` on the clean tree (it stamps the tree on a "
                "full pass), then push. CLAUDE.md -> Execution discipline: a push is not a "
                "test runner."
            )
    return 0, ""


def main(stdin_text: str, env: dict) -> tuple:
    """(exit code, stderr). Fails closed: any exception is (2, reason)."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            return 2, "push-gate: blocked; the hook input is not a JSON object."
        tool_name = payload.get("tool_name")
        if tool_name in BLOCKED_MCP_TOOLS:
            return 2, (
                f"push-gate: `{tool_name}` writes commits to GitHub without git and would "
                f"route around the push gate. Commit locally, run `{CHECK_COMMAND}`, "
                "then `git push`."
            )
        if tool_name != "Bash":
            return 0, ""
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str) or not _PUSH_RE.search(command):
            return 0, ""
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        return _check_push(command, cwd)
    except Exception as error:  # fail closed: never let a broken gate pass a push
        return 2, (
            f"push-gate: blocked; the gate itself failed ({type(error).__name__}: {error}). "
            "Diagnose the hook before pushing."
        )


if __name__ == "__main__":
    try:
        _stdin_text = sys.stdin.read()
        _exit_code, _stderr_text = main(_stdin_text, dict(os.environ))
    except BaseException as _error:  # noqa: BLE001 - even a read failure blocks
        _exit_code, _stderr_text = 2, f"push-gate: blocked; {type(_error).__name__}: {_error}"
    if _stderr_text:
        sys.stderr.write(_stderr_text + "\n")
    sys.exit(_exit_code)
