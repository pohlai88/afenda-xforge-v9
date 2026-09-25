# AFENDA xForge (Odoo 19.0)

This repository is upstream Odoo 19.0 plus the AFENDA layer under `afenda/`.
Root `odoo/` and `addons/` are upstream plus the generated rebrand transform: never
hand-edit them (text and image changes go through `afenda/tools/` rules). Custom work
goes under `afenda/addons/`. See `afenda/README.md` for the layout and run steps.

## Execution discipline (binding on every session and sub-agent)

**No trial and error.**
- Name the cause with evidence (`path:line`, a traceback, a measured value) before
  changing anything. If you cannot name it, read, trace, or ask `odoo-docs-librarian`.
  Do not edit something just to see what happens.
- State the expected output before running a command. A result that contradicts it is a
  finding to explain, not a reason to rerun.
- If the same fix fails twice, stop and go back to diagnosis
  (`superpowers:systematic-debugging`). Do not try a third variation.

**Test the edit, not the world.**
- Per edit: run the narrowest check that exercises it (one test class or method, e.g.
  `--test-tags "/module:TestClass.test_x"`, or one `afenda/tools/tests` file). Never the
  full chain for a small edit.
- Full gates run **once**, at the end of a unit of work, right before the commit: the
  tools suite, the touched modules' Odoo suites, `scan_identity`, and `corpus diff` if a
  rule changed. The `web,test_http` suite runs once per branch.
- Do not rerun a gate that passed unless something it covers has changed since. Record
  the command, the printed count and the SHA, and cite that record instead of rerunning.
- When a gate fails, read the whole failure, fix it, rerun only the failing test, then
  rerun the full gate once.
- About to run the same command a third time with no code change in between? Stop and
  report instead.

**Orchestrators decide; sub-agents execute.**
- Decide from the spec, the plan and the evidence. Write each ruling as one line
  (decision · evidence · cost if wrong), then continue. Do not ask the user anything the
  repo, a committed plan, or this conversation already answers.
- Stop for the user only for what only they can supply (secrets, credentials, payment,
  hosts, DNS), for irreversible or outward-facing actions (push, deploy, delete, send),
  or when two of their stated goals conflict.
- Dispatch with complete context: the task, the exact files, the acceptance check with
  its expected count, and what not to touch. If a sub-agent has to rediscover context,
  the dispatch was defective.
- Run independent tasks in parallel in one turn. Run tasks that share a file serially.
  Accept a sub-agent's result only against its acceptance check: a "passed" without the
  printed count is not accepted.

## Odoo 19 knowledge

A version-locked copy of the official Odoo 19.0 developer documentation lives at
`.agents/Odoo_19_Developer_LLM_Kit/`. Start with its `AGENTS.md` and `llms.txt`.
It omits autodoc docstrings on purpose; resolve those by reading `odoo/orm/`,
`odoo/http.py`, `odoo/addons/base/models/`, or `addons/web/static/src/`.

## Sub-agents

Project agents under `.claude/agents/` share the rules in `.claude/odoo-agent-rules.md`:

- `odoo-docs-librarian`: cited answers from the kit and source. Read-only.
- `odoo-backend-dev`: models, ORM, security files, actions, controllers, reports.
- `odoo-frontend-dev`: Owl, registries, services, hooks, JS fields/views, HOOT tests.
- `odoo-ui-dev`: view XML, xpath inheritance, SCSS, theming.
- `odoo-reviewer`: read-only review against kit rules and layering.
- `odoo-test-runner`: runs test tags with the known environment, reports failures.

## Environment

- Python only from `.venv/Scripts/python`; never install into the global interpreter.
- Server port 8169, test port 8179, PostgreSQL `127.0.0.1:5444`, database `afenda`.
- Port 8069 is already taken by the vendor Odoo 19 Windows service (a `nssm.exe`
  service whose Python listens on `0.0.0.0:8069` against its own bundled PostgreSQL
  on 5432). Leave it alone and keep using 8169/8179; it is not a Windows reserved
  range, so a bind failure there means that service is running, not that the port is
  unusable.

## Commands (run from the repo root in Git Bash)

```bash
# first run
git submodule update --init --depth 1
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -i afenda_brand --stop-after-init --without-demo=all
# server (or the "odoo-afenda" launch config)
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda
# Odoo tests for one module; the env prefix stops MSYS from mangling "/module"
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -u afenda_brand --test-enable --test-tags "/afenda_brand" --stop-after-init --http-port 8179
# rebrand tooling tests (fast, no database)
.venv/Scripts/python -m unittest discover afenda/tools/tests
# rebrand rule change: review on the corpus, then regenerate the golden file, then apply once
.venv/Scripts/python -m afenda.tools.corpus diff
.venv/Scripts/python -m afenda.tools.corpus golden
.venv/Scripts/python -m afenda.tools.rebrand --apply && .venv/Scripts/python -m afenda.tools.scan_identity
```

## Branches and commits

- **One branch: `main`** — the product, what production runs; GitHub's default; CI and `deploy/redeploy.sh` use it. Branch short-lived work off it. (Renamed from `afenda/deidentify-phase1` on 2026-09-25; GitHub redirects the old name, but push to `main`.)
- Upstream is the `upstream` remote (`odoo/odoo` `19.0`). Retired branches are tags under `archive/`: `archive/19.0` (never the product), `archive/upstream-19.0` (the fork's orphan anchor), `archive/brand-identity`, `archive/cloud-api-hardening`, `archive/industry-packs-wip` (unfinished industry packs — resume from there).
- The checkout is shallow and the fork's anchor is an orphan root commit, so `git merge --ff-only upstream/19.0` refuses — see `afenda/README.md` for the one-time local re-anchor that fixes it.
- Commit subjects use Odoo tags: `[ADD]`, `[FIX]`, `[IMP]`, `[REBRAND]`.
- Stage explicit paths, never `git add -A`: the rebrand script can leave about 19,000 modified files under `addons/` and `odoo/`.
- Upstream `.gitignore` ignores all dotfiles, so `.claude/` files need `git add -f`. The doc kit under `.agents/` is untracked on purpose.

## Gotchas

- `git status` on the whole tree takes about two minutes; scope it to paths.
- The `web,test_http` suite has known unrelated failures: wkhtmltopdf missing, `WebSuite.test_check_suite`, `WebManifestRoutesTest` colliding with afenda_brand. Run it once at the end, not per fix.
- Never review rebrand rule changes by applying to the tree; the corpus diff shows every distinct rewrite first.
- New files under `.claude/agents/` appear in the Agent tool only after a session restart.
- Never read `exit = 0` from an Odoo test run as evidence; read the printed count. `log_level = warn` silences the INFO result line, so a *passing* suite would print nothing and "40 passed" would look identical to "0 collected". `afenda/odoo.conf` now sets `log_handler = odoo.tests:INFO` to restore it, so the count prints unasked (a CLI `--log-handler` accumulates with it rather than replacing it, so the count survives unless you override `odoo.tests` itself).
- A test class that does not subclass Odoo's `BaseCase` is discovered and then silently dropped by `TagsSelector` (`odoo/tests/tag_selector.py:88-90`); the skip logs at DEBUG, which `log_level = warn` hides. `afenda_brand`'s `test_every_test_class_would_actually_be_collected` guards every addon against this.
- Several Claude sessions may share this one worktree, so they share one `.git/index`. The exposure is the next bare `git commit` by anyone, not your `git add`: use `git commit --only -F msgfile -- <paths>` (options before the `--`), staging and committing in one shell invocation.
- Look at a file before `cat >` onto it, and re-check `git log` on paths you are about to write; a peer session may have committed there since you last read.
- Cloning a database for a parallel lane must copy the filestore too (`filestore/<db>` under Odoo's data dir, path from `odoo.tools.config`), or every attachment-backed field breaks and the failures read as code regressions.
- Ask "does this code call X" with an AST walk, not grep: grep matches the name inside docstrings, including ones stating it is deliberately *not* called.
