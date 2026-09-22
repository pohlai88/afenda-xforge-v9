# Shared rules for the Odoo 19 agents

Every agent under `.claude/agents/odoo-*.md` reads this file first; it is binding.
Edit rules here rather than in each agent.

## Version purity: Odoo 19.0 only

Facts from the kit changelog (`docs/developer/reference/backend/orm/changelog.md`):

- `odoo.osv` is deprecated; `record._cr`, `record._context`, `record._uid` are
  deprecated (use `self.env.cr`, `self.env.context`, `self.env.uid`).
- `read_group` is deprecated; use `_read_group` in backend code and
  `formatted_read_group` as the public API.
- SQL constraints and indexes are model attributes: `models.Constraint(...)`,
  not `_sql_constraints`.
- Controller type `json` is now `jsonrpc`.
- `name_get` is gone; read or compute `display_name`, search via
  `_search_display_name`.
- `check_access`, `has_access`, `_filtered_access` combine access rights and
  record rules.
- `@api.private` marks Python methods not exposed to RPC.
- Domains: `odoo.Domain` API exists; the ORM lives in `odoo/orm/`.
- View XML: no `attrs` or `states`; use Python-expression attributes such as
  `invisible="state != 'draft'"`. The list view tag is `<list>`, never `<tree>`.

## Authority and citation

- Kit at `.agents/Odoo_19_Developer_LLM_Kit/`. Authority: `source/` > `docs/` >
  `indexes/` > `knowledge/`.
- Reference pages for API facts; tutorials and how-tos for workflow.
- Autodoc gaps (`indexes/autodoc-directives.json`): resolve by reading the repo's
  own `odoo/` and `addons/` source. Never invent docstrings.
- Cite docs by `source_path` + `source_blob_sha`; cite source by `path:line`.
- When unsure, ask `odoo-docs-librarian` rather than guessing.

## Security

Retrieve both `docs/developer/reference/backend/security.md` and the relevant ORM
material before writing anything that touches access rights, record rules, groups,
`sudo()`, `with_user()`, `company_id`, or controller `auth`.

## Frontend extension order

Registry, then service, then hook or component, then view architecture, then
`patch()` only when no extension point suffices and the reason is stated in a
comment.

## AFENDA layering

- Root `odoo/` and `addons/` are pristine upstream. Never hand-edit them.
- All custom work goes under `afenda/addons/<module>/`.
- Branding text and image changes go through `afenda/tools/` rules and their
  corpus golden test (`afenda/tools/tests/test_corpus.py`), never ad-hoc edits.
- Brand values are defined once in `afenda/addons/afenda_brand/brand.py` and
  mirrored in `static/src/scss/primary_variables.scss`.

## Environment

- Python: `.venv/Scripts/python` only. Never install into the global interpreter.
- Server: port 8169 (`.claude/launch.json` config `odoo-afenda`). Tests: port 8179.
- PostgreSQL: superuser `odoo`, trust auth, `127.0.0.1:5444`, database `afenda`.
- Test command (Git Bash; the env prefix stops MSYS from mangling `/module` tags):

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -u <module> --test-enable \
  --test-tags "/<module>" --stop-after-init --http-port 8179
```

- Never run `git status` on the whole tree (about two minutes). Use
  `git diff --quiet -- <paths>` or `git status -- <paths>`.
