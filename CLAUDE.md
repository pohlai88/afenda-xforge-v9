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
  rule changed. The `web,test_http` suite runs once per branch. Before every push run
  `/preflight` (`.claude/skills/preflight/`): `python -m afenda.tools.check`, then the reviews.
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
  `.claude/skills/orchestrate/SKILL.md` is binding on how: a conflict map before any dispatch,
  the slowest real-environment signal (CI, the image, a fresh install) started first, reviews as
  one parallel sweep split by dimension, then one fix wave and one scoped re-review.
  Accept a sub-agent's result only against its acceptance check: a "passed" without the
  printed count is not accepted.

## Handoffs between sessions

Before starting work, read the newest file in `docs/superpowers/handoffs/`. It records what the
previous session (cloud or local) shipped, the owner's binding decisions, what waits on the
owner, and what is still open. At present that is `2026-09-26-api-assets.md` (phase 1 of the
"AFENDA-owned API assets" plan, done); `2026-09-25-cloud-session.md` still holds two owner
rulings that are easy to miss: do not hand-write guide pages, and do not start G2.
A session that ends with work in flight writes a new dated handoff there. It does not rely on
a scratch ledger, which dies with a cloud container.

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

## Superpowers skills

`.claude/settings.json` enables `superpowers@superpowers-marketplace` for every session
(it loads at session start; `claude plugin list` shows it). Use these, in this order of
a unit of work; this file wins wherever a skill's default differs:

- `superpowers:brainstorming` before new features or behaviour changes. Specs go to
  `docs/superpowers/specs/YYYY-MM-DD-<topic>.md`.
- `superpowers:writing-plans` for any multi-step task, before code. Plans go to
  `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`; a committed plan is what
  orchestrators decide from.
- `superpowers:subagent-driven-development` to execute a plan through the project
  agents above (dispatch rules under **Execution discipline** apply);
  `superpowers:dispatching-parallel-agents` for independent tasks in one turn;
  `superpowers:executing-plans` only when working inline.
- `superpowers:test-driven-development` for every feature or fix: the test lands with
  the code, and each run is the narrowest one (**Test the edit, not the world**).
- `superpowers:systematic-debugging` on any failure, before proposing a fix.
- `superpowers:verification-before-completion` before claiming done: cite the printed
  test count and the SHA, never an exit code.
- `superpowers:requesting-code-review` (with `odoo-reviewer`) before merging to `main`;
  `superpowers:receiving-code-review` when answering review.
- `superpowers:finishing-a-development-branch` to integrate: the target is `main`.

Skip `superpowers:using-git-worktrees`: a cloud session is already an isolated
container, and locally a second checkout of this tree is large; commit with
`git commit --only` instead (see **Gotchas**).

## Cloud sessions (Claude Code on the web)

A cloud session is a fresh Ubuntu container, not the Windows machine above.
`.claude/hooks/session-start.sh` (a SessionStart hook; it exits at once when
`CLAUDE_CODE_REMOTE` is not `true`, so local sessions never run it) prepares it before
the first prompt:

- build headers for psycopg2 and python-ldap, via apt;
- `git submodule update --init --depth 1` (the OCA addons on `addons_path`);
- a Python 3.11 `.venv` with `requirements.txt`, both `afenda/tools/requirements*.txt`
  and ruff; `.venv/Scripts` links to `.venv/bin`, so every command below runs verbatim;
- a PostgreSQL cluster `afenda` on `127.0.0.1:5444` with a passwordless `odoo`
  superuser, as `afenda/odoo.conf` expects.

Each step is guarded: about 90 s on a cold container, about 2 s warm. The hook is
synchronous, so the session starts only once it finishes. Differences from local:

- The database is not created by the hook. Run the "first run" command below once per
  container before any Odoo test (about 30 s); the test command's `-u` upgrades an
  installed module, it does not install one.
- The Odoo doc kit (`.agents/`) is untracked, so it is absent in the cloud;
  `odoo-docs-librarian` answers from `odoo/`, `addons/` and the kit only when present.
- No vendor service holds 8069, and the MSYS prefix on test commands is harmless on Linux.
- Odoo warns "Running as user 'root' is a security risk"; that is expected in the container.
- Anything not committed and pushed is lost when the container is reclaimed.
- Changing the hook: keep it idempotent and non-interactive, then run
  `CLAUDE_CODE_REMOTE=true CLAUDE_PROJECT_DIR=$PWD .claude/hooks/session-start.sh`
  twice (cold, then warm) and cite both exit codes before committing. It takes effect
  for new sessions once it is on `main`.

## Environment

- Python only from `.venv/Scripts/python`; never install into the global interpreter.
  (Cloud sessions: see **Cloud sessions** above; the same path works there.)
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
# server
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda
# Odoo tests for one module; the env prefix stops MSYS from mangling "/module"
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -u afenda_brand --test-enable --test-tags "/afenda_brand" --stop-after-init --http-port 8179
# rebrand tooling tests (fast, no database)
.venv/Scripts/python -m unittest discover afenda/tools/tests
# rebrand rule change: review on the corpus, then regenerate the golden file, then apply once
.venv/Scripts/python -m afenda.tools.corpus diff
.venv/Scripts/python -m afenda.tools.corpus golden
.venv/Scripts/python -m afenda.tools.rebrand --apply && .venv/Scripts/python -m afenda.tools.scan_identity
# regenerate the committed OpenAPI asset (afenda/addons/afenda_api_docs/openapi/<area>.json), on a
# fresh all-apps database, through odoo-bin shell; prints "afenda-openapi: wrote <N> documents"
OUT_DIR=afenda/addons/afenda_api_docs/openapi ADDONS_ROOT=addons \
  .venv/Scripts/python odoo-bin shell -c afenda/odoo.conf -d <all-apps db> --no-http < afenda/tools/export_openapi_shell.py
# gate the OpenAPI contract change against a base ref, and write the CHANGELOG.md section for
# the current API_VERSION (afenda/addons/afenda_api_docs/api_version.py)
.venv/Scripts/python -m afenda.tools.api_diff check --base-ref origin/main
.venv/Scripts/python -m afenda.tools.api_diff changelog --base-ref origin/main
```

A `[REBRAND]` apply, or an upstream merge, changes generated help text and therefore the
committed OpenAPI asset's descriptions (field `help`, model docstrings): regenerate the asset
with the exporter above and commit the result. That is a descriptive-only change to the
contract (no operation, schema or requirement changed), so it needs no `API_VERSION` bump.

## Pull requests

`.claude/skills/steward/SKILL.md` is binding on every pull request into `main`, for agents and
people alike: what "done" means (CI green on the head SHA, no conflict, no open thread, a
current Verification table, the owner's go-ahead), the order events are worked, the
diagnose-first procedure for a red check (log line → cause as `path:line` → guard test RED →
one fix GREEN → gates once → one push; the same fix failing twice stops for a report), and
the merge (rebase and merge) and post-merge steps. `.github/PULL_REQUEST_TEMPLATE.md` asks for
the evidence, and the `pr evidence` check (`afenda-pr.yml`, `afenda/tools/pr_evidence.py`)
fails a PR whose description lacks a printed test count or a commit id of the PR, and every push
that opens or updates it goes through `/preflight` and the push gate (Gotchas). Spec:
`docs/superpowers/specs/2026-09-26-pr-stewardship.md`.

## Branches and commits

- **One branch: `main`** — the product, what production runs; GitHub's default; CI and `deploy/redeploy.sh` use it. Branch short-lived work off it. (Renamed from `afenda/deidentify-phase1` on 2026-09-25; GitHub redirects the old name, but push to `main`.)
- Upstream is the `upstream` remote (`odoo/odoo` `19.0`). Retired branches are tags under `archive/`: `archive/19.0` (never the product), `archive/upstream-19.0` (the fork's orphan anchor), `archive/brand-identity`, `archive/cloud-api-hardening`, `archive/industry-packs-wip` (unfinished industry packs — resume from there).
- The checkout is shallow and the fork's anchor is an orphan root commit, so `git merge --ff-only upstream/19.0` refuses — see `afenda/README.md` for the one-time local re-anchor that fixes it.
- Commit subjects use Odoo tags: `[ADD]`, `[FIX]`, `[IMP]`, `[REBRAND]`.
- Stage explicit paths, never `git add -A`: the rebrand script can leave 23,291 changed files (119 hand-authored, 23,172 rebrand-generated) under `addons/` and `odoo/`.
- Upstream `.gitignore` ignores all dotfiles, so `.claude/` files need `git add -f`. The doc kit under `.agents/` is untracked on purpose.

## Gotchas

- The auth-page crystal bear (`crystal_bear.svg`, `auth_bear.xml`) is the tenant signature (owner, 2026-09-26): pinned by `test_tenant_signature.py` and denied to agent edits; design around it, never in it.
- `git status` on the whole tree takes about two minutes; scope it to paths.
- The `web,test_http` suite has known unrelated failures: wkhtmltopdf missing, `WebSuite.test_check_suite`, `WebManifestRoutesTest` colliding with afenda_brand. Run it once at the end, not per fix.
- Never review rebrand rule changes by applying to the tree; the corpus diff shows every distinct rewrite first.
- New files under `.claude/agents/` appear in the Agent tool only after a session restart.
- Never read `exit = 0` from an Odoo test run as evidence; read the printed count. `log_level = warn` silences the INFO result line, so a *passing* suite would print nothing and "40 passed" would look identical to "0 collected". `afenda/odoo.conf` now sets `log_handler = odoo.tests:INFO` to restore it, so the count prints unasked (a CLI `--log-handler` accumulates with it rather than replacing it, so the count survives unless you override `odoo.tests` itself).
- A test class that does not subclass Odoo's `BaseCase` is discovered and then silently dropped by `TagsSelector` (`odoo/tests/tag_selector.py:88-90`); the skip logs at DEBUG, which `log_level = warn` hides. `afenda_brand`'s `test_every_test_class_would_actually_be_collected` guards every addon against this.
- Several Claude sessions may share this one worktree, so they share one `.git/index`. The exposure is the next bare `git commit` by anyone, not your `git add`: use `git commit --only -F msgfile -- <paths>` (options before the `--`), staging and committing in one shell invocation.
- Look at a file before `cat >` onto it, and re-check `git log` on paths you are about to write; a peer session may have committed there since you last read.
- Cloning a database for a parallel lane must copy the filestore too (`filestore/<db>` under Odoo's data dir, path from `odoo.tools.config`), or every attachment-backed field breaks and the failures read as code regressions.
- `.claude/hooks/rerun_guard.py` (a PreToolUse hook) blocks a gate command (a test suite,
  `api_diff`, `corpus`, `scan_identity`, `pr_evidence`, `afenda.tools.check`) the third time it
  runs on an unchanged tree, counted across sessions and sub-agents. Cite the earlier count, change code, or stop and report; the hook fails
  open on any internal error.
- `git commit --only <path>` refuses a path git does not track yet ("pathspec … did not match any file(s) known to git"): `git add` it (`git add -f` under `.claude/`) in the same shell call first.
- The scoped fingerprint (`afenda/tools/_git_identity.py`'s `SCOPED_PATHS`, shared by `rerun_guard.py` and `check.py`'s dirty-tree refusal) covers `afenda .github .claude docs CLAUDE.md deploy` only (an unscoped diff costs about two minutes per call), so a `[REBRAND]` apply or an upstream merge is invisible to it: the first run after one is new evidence; say so where you cite it.
- `.claude/hooks/push_gate.py` (PreToolUse) blocks a `git push` whose tip tree (the full commit tree, so a `[REBRAND]` apply needs a new stamp) has no passing stamp in `.git/afenda-check/`, a push chained to other commands, and always the three GitHub-write MCP tools; `/preflight` earns the stamp. `disableAllHooks`, a wrapper script, an alias, or a raw `gh api`/`curl` write all bypass it — branch protection on `main` is the real backstop, not the hook.
- Ask "does this code call X" with an AST walk, not grep: grep matches the name inside docstrings, including ones stating it is deliberately *not* called.
