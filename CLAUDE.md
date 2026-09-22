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
- Test command and the MSYS path fix are in `.claude/odoo-agent-rules.md`.
- Avoid `git status` on the whole tree; scope it to paths.
