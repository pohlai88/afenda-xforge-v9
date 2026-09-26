# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""One local check before a push: `python -m afenda.tools.check`.

It knows every gate, picks the ones the change needs, runs each once, prints
one Markdown table (gate · command · printed result · commit) that can be
pasted into a PR's Verification section, and on a full pass writes a stamp
the push gate (`.claude/hooks/push_gate.py`) reads.
Spec: docs/superpowers/specs/2026-09-26-local-first-gates.md, decision 1 and
"Corrections after review"; plan: docs/superpowers/plans/2026-09-26-local-first-gates.md,
"Shared interface".

    python -m afenda.tools.check [--base REF] [--db NAME] [--gate NAME ...] [--list]

- `--base` (default `origin/main`): the gates are chosen from
  `git diff --name-only <merge-base(base, HEAD)>..HEAD` (`select_gates`), and
  `api_contract` diffs against it, as CI's pull-request step does.
- `--db` (default `$AFENDA_CHECK_DB`, else `afenda`): the database the Odoo
  gates run on. They pass `-i M -u M` together: Odoo installs the listed
  modules that are uninstalled and upgrades the installed ones
  (odoo/modules/loading.py:431-439, fed both lists by
  odoo/service/server.py:1591), so a fresh container works after the "first
  run" command.
- `--gate NAME` (repeatable): run only these. Allowed on a dirty tree; stamps
  nothing unless the tree is clean and the named gates cover the selection.
- `--list`: print the selection and the commands; run nothing.

It certifies a commit, not a working tree: with tracked changes under
`_git_identity.SCOPED_PATHS` it refuses (exit 2) unless `--gate` is given.
Root `odoo/` and `addons/` are out of scope (see `_git_identity`).

Exit 0 when every gate passed, 1 when one failed, 2 when it refused or could
not start. The stamp, written only on a full pass of a clean tree, is
`<git common dir>/afenda-check/<tree sha>.json`:
`{"tree", "head", "base", "gates": [{"name", "command", "result"}], "passed": true, "time"}`.

The test floors (`ODOO_TESTS_MIN`, `PACK_TESTS_MIN`) stay in the CI workflow
(spec correction 10); CI keeps its own copy of the `tools` and `api_contract`
commands, and `tests/test_check.py` asserts each equals `gate_argv(...)` here.

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from afenda.tools import _git_identity

ODOO_MODULES = ("afenda_brand", "afenda_runtime", "afenda_api_docs", "afenda_brand_digest")
PACK_MODULES = ("afenda_industry_base", "afenda_industry_bakery")
NGINX_CONFIGS = ("afenda.conf", "afenda.tls.conf")
NGINX_IMAGE = "nginx:1.27-alpine"
DEFAULT_BASE = "origin/main"
DB_ENV = "AFENDA_CHECK_DB"


def _odoo_test_argv(modules):
    mods = ",".join(modules)
    tags = ",".join(f"/{name}" for name in modules)
    return [
        "{python}", "odoo-bin", "-c", "afenda/odoo.conf", "-d", "{db}",
        "-i", mods, "-u", mods, "--test-enable", "--test-tags", tags,
        "--stop-after-init", "--http-port", "8179",
    ]


# The gates, in the order they run. `argv` is a template: `{python}`,
# `{base}` and `{db}` are filled by `gate_argv`. `before` runs first without
# tests: the industry packs refuse to install before a chart of accounts
# exists (afenda/addons/afenda_industry_bakery/hooks.py:159,300), so CI
# installs `account` first and so does this.
GATES = {
    "tools": {
        "argv": ["{python}", "-m", "unittest", "discover", "afenda/tools/tests"],
    },
    "api_contract": {
        "argv": ["{python}", "-m", "afenda.tools.api_diff", "check", "--base-ref", "{base}"],
    },
    "odoo": {
        "argv": _odoo_test_argv(ODOO_MODULES),
    },
    "packs": {
        "before": [
            "{python}", "odoo-bin", "-c", "afenda/odoo.conf", "-d", "{db}",
            "-i", "account", "--stop-after-init", "--http-port", "8179",
        ],
        "argv": _odoo_test_argv(PACK_MODULES),
    },
    "nginx": {
        # Once per file in NGINX_CONFIGS, as afenda-ci.yml's `nginx -t` job.
        "argv": [
            "docker", "run", "--rm", "--add-host", "xforge:127.0.0.1",
            "-v", "{conf}:/etc/nginx/conf.d/default.conf:ro",
            "-v", "{certs}:/etc/letsencrypt:ro", NGINX_IMAGE, "nginx", "-t",
        ],
    },
}

_ODOO_RESULT_RE = re.compile(
    r"(\d+) failed, (\d+) error\(s\) of (\d+) tests(?: when loading database '[^']*')?"
)
_RAN_RE = re.compile(r"^Ran \d+ tests? in \S+$")
_API_SHORT_RE = re.compile(r"^breaking: \d+, additive: \d+, descriptive: \d+$")


def _fill(template, **values):
    return [token.format(**values) if "{" in token else token for token in template]


def gate_argv(name, *, python="python", base=DEFAULT_BASE, db="afenda"):
    """The gate's command as argv; `python` is shown as `python` by default."""
    if name == "nginx":
        return _fill(GATES[name]["argv"], conf="deploy/nginx/<conf>", certs="<certs>")
    return _fill(GATES[name]["argv"], python=python, base=base, db=db)


def gate_command(name, **values):
    """The gate's command as one shell line, as the table prints it."""
    return shlex.join(gate_argv(name, **values))


def select_gates(paths):
    """The gates a change to `paths` needs, in GATES order."""
    selected = {"tools", "api_contract"}
    for path in paths:
        if (
            path.startswith("afenda/addons/")
            or path in ("deploy/Dockerfile", "requirements.txt")
        ):
            selected.add("odoo")
        if path.startswith("afenda/addons/afenda_industry_"):
            selected.add("packs")
        if path.startswith("deploy/nginx/"):
            selected.add("nginx")
    return [name for name in GATES if name in selected]


def _last_line(output, predicate):
    found = None
    for line in output.splitlines():
        line = line.strip()
        if predicate(line):
            found = line
    return found


def parse_result(name, returncode, output):
    """(printed result, passed) for one gate's exit code and output."""
    if name == "tools":
        ran = _last_line(output, lambda line: bool(_RAN_RE.match(line)))
        status = _last_line(
            output, lambda line: line == "OK" or line.startswith(("OK (", "FAILED ("))
        )
        if not ran or not status:
            return "no unittest result line", False
        return f"{ran} · {status}", returncode == 0 and status.startswith("OK")
    if name == "api_contract":
        short = _last_line(output, lambda line: bool(_API_SHORT_RE.match(line)))
        if short:
            if "no base contract" in output.splitlines():
                short += " (no base contract)"
            return short, returncode == 0
        counts = {"Breaking": 0, "Additive": 0, "Descriptive": 0}
        current = None
        for line in output.splitlines():
            if line.rstrip(":") in counts and line.endswith(":"):
                current = line.rstrip(":")
            elif current and line.startswith("  ") and line.strip():
                counts[current] += 1
        result = ", ".join(f"{key.lower()}: {value}" for key, value in counts.items())
        return result, returncode == 0
    if name in ("odoo", "packs"):
        matches = list(_ODOO_RESULT_RE.finditer(output))
        if not matches:
            return "no Odoo test result line", False
        last = matches[-1]
        failed, errors, total = (int(group) for group in last.groups())
        return last.group(0), returncode == 0 and failed == 0 and errors == 0 and total > 0
    raise KeyError(name)


def _default_executor(argv, cwd):
    """Run `argv`, echo its output as it comes, return (exit code, output)."""
    process = subprocess.Popen(
        argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    lines = []
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line)
    return process.wait(), "".join(lines)


def _docker_available():
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _run_nginx(root, executor):
    if not _docker_available():
        return "CI only (no docker here)", True
    with tempfile.TemporaryDirectory() as certs:
        live = Path(certs) / "live" / "app.nexuscanon.com"
        live.mkdir(parents=True)
        code, output = executor(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=app.nexuscanon.com",
             "-keyout", str(live / "privkey.pem"), "-out", str(live / "fullchain.pem")],
            root,
        )
        if code != 0:
            return "openssl could not make the throwaway certificate", False
        ok = 0
        for conf in NGINX_CONFIGS:
            argv = _fill(
                GATES["nginx"]["argv"],
                conf=str(Path(root) / "deploy" / "nginx" / conf), certs=certs,
            )
            code, output = executor(argv, root)
            if code == 0 and "test is successful" in output:
                ok += 1
    return f"nginx -t: {ok} of {len(NGINX_CONFIGS)} configs successful", ok == len(NGINX_CONFIGS)


def run_gate(name, root, executor, *, base, db):
    """(command, printed result, passed) for one gate."""
    display = gate_command(name, base=base, db=db)
    if name == "nginx":
        result, passed = _run_nginx(root, executor)
        return f"{display} (for {', '.join(NGINX_CONFIGS)})", result, passed
    before = GATES[name].get("before")
    if before:
        code, output = executor(_fill(before, python=sys.executable, db=db), root)
        if code != 0:
            return display, f"`{shlex.join(_fill(before, python='python', db=db))}` exited {code}", False
    argv = gate_argv(name, python=sys.executable, base=base, db=db)
    code, output = executor(argv, root)
    result, passed = parse_result(name, code, output)
    return display, result, passed


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(rows, commit):
    lines = [
        "| gate | command | printed result | commit |",
        "|---|---|---|---|",
    ]
    for name, command, result, _passed in rows:
        lines.append(f"| {name} | `{_cell(command)}` | {_cell(result)} | {commit} |")
    return "\n".join(lines)


def _parser():
    parser = argparse.ArgumentParser(
        prog="python -m afenda.tools.check",
        description="Run the gates this change needs, once; stamp the tree on a full pass.",
    )
    parser.add_argument("--base", default=DEFAULT_BASE, help="base ref (default: %(default)s)")
    parser.add_argument(
        "--db", default=os.environ.get(DB_ENV) or "afenda",
        help=f"Odoo database for the module gates (default: ${DB_ENV} or afenda)",
    )
    parser.add_argument(
        "--gate", action="append", choices=list(GATES), default=[],
        help="run only this gate (repeatable)",
    )
    parser.add_argument("--list", action="store_true", help="print the selection; run nothing")
    return parser


def main(argv=None, *, cwd=None, executor=None) -> int:
    args = _parser().parse_args(argv)
    executor = executor or _default_executor
    root = _git_identity.repo_root(cwd or os.getcwd())
    if root is None:
        print("check: not inside a git repository")
        return 2

    try:
        _git_identity.rev_sha(root, args.base)
        merge_base = _git_identity.run_git(["merge-base", args.base, "HEAD"], root).strip()
        changed = _git_identity.run_git(
            ["diff", "--name-only", f"{merge_base}..HEAD"], root
        ).splitlines()
        head = _git_identity.rev_sha(root, "HEAD")
        tree = _git_identity.tree_sha(root)
        dirty = _git_identity.scoped_dirty(root)
    except _git_identity.GitIdentityError as error:
        print(f"check: cannot read the change against {args.base!r}: {error}")
        return 2

    selected = select_gates(changed)
    if args.list:
        print(f"base {args.base} (merge base {merge_base[:12]}), {len(changed)} changed paths")
        for name in selected:
            before = GATES[name].get("before")
            if before:
                print(f"{name} (after): {shlex.join(_fill(before, python='python', db=args.db))}")
            print(f"{name}: {gate_command(name, base=args.base, db=args.db)}")
        return 0

    if dirty and not args.gate:
        print(
            "check: refused. It certifies a commit, and these paths have "
            "uncommitted or untracked changes (commit them, or name gates with --gate to run "
            "them without a stamp):"
        )
        for path in dirty:
            print(f"  {path}")
        return 2

    to_run = [name for name in GATES if name in args.gate] if args.gate else selected
    rows = []
    for name in to_run:
        print(f"== {name}", flush=True)
        command, result, passed = run_gate(name, root, executor, base=args.base, db=args.db)
        rows.append((name, command, result, passed))

    all_passed = all(row[3] for row in rows)
    print()
    print(_table(rows, head[:12]))
    print()

    if not all_passed:
        print("check: FAILED: " + ", ".join(row[0] for row in rows if not row[3]) + "; no stamp")
        return 1

    reason = None
    # The API gate compares against the base's tip, so a stamp needs the base tip itself to be
    # origin/main's, not only a shared merge base (Codex P1, PR #9).
    try:
        default_tip = _git_identity.rev_sha(root, DEFAULT_BASE)
    except _git_identity.GitIdentityError:
        default_tip = None  # no origin/main here (a scratch repo): the base passed is all there is
    if dirty:
        reason = "the tree has uncommitted scoped changes"
    elif default_tip and default_tip != _git_identity.rev_sha(root, args.base):
        reason = f"the gates were chosen against {args.base!r}, not {DEFAULT_BASE}"
    elif not set(selected) <= set(to_run):
        reason = "not every selected gate ran (" + ", ".join(
            name for name in selected if name not in to_run
        ) + " missing)"
    else:
        try:
            if (
                _git_identity.rev_sha(root, "HEAD") != head
                or _git_identity.scoped_dirty(root)
            ):
                reason = "HEAD or the scoped tree changed while the gates ran"
        except _git_identity.GitIdentityError as error:
            reason = f"cannot re-read the tree: {error}"

    if reason:
        print(f"check: passed; no stamp: {reason}")
        return 0

    stamp = {
        "tree": tree,
        "head": head,
        "base": args.base,
        "gates": [
            {"name": name, "command": command, "result": result}
            for name, command, result, _passed in rows
        ],
        "passed": True,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    path = _git_identity.stamp_path(root, tree)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    print(f"check: passed; stamp {path} (tree {tree[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
