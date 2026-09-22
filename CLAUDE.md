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
- Port 8069 is in a Windows reserved range and cannot be bound.

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
