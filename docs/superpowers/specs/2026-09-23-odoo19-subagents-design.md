# Odoo 19 developer sub-agents — design

Date: 2026-09-23
Status: approved in chat (location: native Claude Code project agents; model: opus for all)

## Goal

Give this repository a set of Claude Code sub-agents that do Odoo 19.0 development
work grounded in the version-locked documentation kit at
`.agents/Odoo_19_Developer_LLM_Kit/` and in the Odoo 19.0 source that sits at the
repository root, while respecting the AFENDA layering rules.

## What the kit provides

- `source/`: byte-exact official RST at odoo/documentation commit
  `8174b8bfbd3247e59208bf853bd7f6c47bec946c` (authority level 1).
- `docs/`: normalized Markdown with provenance front matter (level 2).
- `indexes/` and `chunks/`: symbols (362), code examples (1,234), cross-references,
  anchors, concepts, autodoc directive list (124), RAG chunks (547) (level 3).
- `knowledge/`: three derived maps (architecture, frontend extension order, security)
  (level 4, not normative).
- `scripts/query.py`: regex search over `docs/`.
- Coverage boundary: autodoc-generated docstrings are absent. The matching Odoo
  19.0 source is at the repository root (`odoo/`, `addons/`), so agents resolve those
  gaps by reading source and citing file and line.

## Architecture

Layered set of six agents. Each agent is a Markdown file under `.claude/agents/`
with frontmatter `name`, `description`, `tools`, `model`.

| Agent | Role | Tools | Model |
|---|---|---|---|
| `odoo-docs-librarian` | Read-only lookup. Answers "what does Odoo 19 say about X" with citations (source path + blob SHA, or repo file:line for autodoc gaps). | Read, Grep, Glob, Bash | opus |
| `odoo-backend-dev` | Builds server-side code: models, fields, compute/onchange, constraints, data files, actions, controllers, mixins, manifests, QWeb PDF reports. | all | opus |
| `odoo-frontend-dev` | Builds web-client JS: Owl components, registries, services, hooks, JS fields/views/client actions, asset bundles, HOOT tests. Walks the extension-map order before `patch()`. | all | opus |
| `odoo-ui-dev` | Builds view XML and xpath inheritance, view attributes, SCSS inheritance and primary variables, icons, web-client theming. | all | opus |
| `odoo-reviewer` | Read-only review of a diff against the kit's rules and AFENDA layering. | Read, Grep, Glob, Bash | opus |
| `odoo-test-runner` | Runs Python test tags with the known environment; returns only failures with tracebacks. Reports HOOT run instructions. | Bash, Read, Grep | opus |

Optional later, same template: `odoo-website-theme-dev`, `odoo-upgrade-dev`,
`odoo-l10n-accounting-dev`.

## Shared rules (inlined in every agent prompt)

1. Odoo 19.0 only. Do not apply behavior from other versions. Known 19.0 facts from
   the kit changelog: `odoo.osv` deprecated; `record._cr`, `record._context`,
   `record._uid` deprecated; `read_group` deprecated in favor of `_read_group`;
   constraints and indexes are model attributes; `json` controllers are `jsonrpc`;
   `name_get` gone, use `display_name`; `check_access`/`has_access` combine rights and
   rules. View XML: no `attrs`/`states`, use Python-expression attributes; `list`
   view, not `tree`.
2. Authority order: `source/` > `docs/` > `indexes/`,`chunks/` > `knowledge/`.
   Reference pages for API facts, tutorials and how-tos for workflow.
3. Autodoc gaps: check `indexes/autodoc-directives.json`; resolve by reading the
   repo's own `odoo/` or `addons/` source; never invent docstrings.
4. Cite docs by `source_path` and `source_blob_sha`; cite source by `path:line`.
5. Security semantics from the security and ORM references are preserved; retrieve
   both before authorization-sensitive code.
6. Frontend: registry, then service, then hook or component, then view
   architecture, then `patch()` only as a last resort with a stated reason.
7. AFENDA layering: root `odoo/` and `addons/` are upstream and are never hand-edited.
   New work lives under `afenda/addons/`. Branding text or image changes go through
   `afenda/tools/` rules, not ad-hoc edits.
8. Environment: run Python only from `.venv/Scripts/python`; never install into the
   global interpreter. Server port 8169, test port 8179, PostgreSQL on 127.0.0.1:5444.
   Test command runs from Git Bash with `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"`.
9. Never `git status` on the whole tree; use `git diff --quiet -- <paths>`.

## Data flow

- Main session or any builder calls `odoo-docs-librarian` for a citation-backed
  answer; the librarian returns a compact brief, not file dumps.
- Builders implement in `afenda/addons/<module>/`, write tests alongside, then hand
  the module name to `odoo-test-runner`.
- `odoo-reviewer` receives a diff spec (paths or a git ref range) and returns
  findings ranked by severity with a citation for each rule it applies.

## Error handling

- Librarian: if a term is not in the kit, say so and point to the source file it
  would live in; do not extrapolate from other versions.
- Test runner: if PostgreSQL on 5444 is not reachable, stop and print the cluster
  recreate commands; do not create a cluster on its own. Known unrelated failures in
  `web,test_http` (wkhtmltopdf missing, WebSuite.test_check_suite,
  WebManifestRoutesTest colliding with afenda_brand) are listed and not counted.
- Reviewer: never edits; if it cannot verify a claim in the kit or source it says
  "unverified" rather than asserting.

## Testing the agents

- Frontmatter of each file parses (name, description, tools, model present).
- Each agent's description carries trigger phrases so the main session delegates
  correctly.
- Smoke check: invoke the librarian with a known symbol (`Model._check_company`,
  an autodoc gap) and confirm it returns the repo source location with a line number.

## Also in scope

- A root `CLAUDE.md` note pointing to the kit and the agents, since the kit's own
  `CLAUDE.md` only applies when working inside its folder.
