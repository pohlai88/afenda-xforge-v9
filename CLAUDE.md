# AFENDA xForge (Odoo 19.0)

This repository is upstream Odoo 19.0 plus the AFENDA layer under `afenda/`.
Root `odoo/` and `addons/` are pristine upstream: never hand-edit them. Custom work
goes under `afenda/addons/`. See `afenda/README.md` for the layout and run steps.

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

- `upstream-19.0` is pristine odoo/odoo, never edited. `19.0` is upstream plus the `[REBRAND]` commit plus `afenda/`. Feature work branches off `19.0`.
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
