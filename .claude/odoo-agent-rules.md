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
- Brand values the product *uses* are defined once in
  `afenda/addons/afenda_brand/brand.py` and mirrored in
  `static/src/scss/primary_variables.scss`. The mirroring is the point: it keeps
  the UI and the SCSS from drifting apart.
- Identity-artwork colour is the one carve-out. Shades that exist only inside a
  drawn mark, tile or badge live in `afenda/tools/brand_images.py`, not in
  `brand.py`, and are not mirrored into SCSS. They are renderer inputs, not
  tokens: putting them in `brand.py` would present them as colours the UI may
  use, which is the drift the rule above exists to prevent. A generator may
  therefore hold hexes that appear nowhere else — say so in its comments rather
  than claiming every value comes from `brand.py`.

## Evidence hierarchy

Authority for a claim about this repository's runtime behaviour, descending:

1. This fork's source at the release SHA — highest authority for runtime behaviour.
2. Observed execution or test output from that SHA.
3. AFENDA specs and ADRs — normative intent; any load-bearing claim here must
   cite (1) or (2).
4. Official Odoo 19 documentation — intended behaviour and operational guidance.
5. Upstream Odoo source — comparison and upgrade analysis, never assumed
   identical to this fork.
6. External articles and forum answers — context only, never authority.

This repository is a fork of Odoo 19.0 with roughly 23,000 files rewritten by
`afenda/tools/rebrand.py`, so a claim verified against upstream GitHub or
upstream docs can be wrong here. Example: an architecture document asserted
"exactly one cron role may exist, because N instances would run every job N
times." This fork's own `odoo/addons/base/models/ir_cron.py:365` uses
`FOR NO KEY UPDATE SKIP LOCKED`, and the comment at `:330-332` states the lock
exists precisely so concurrent workers do not take the same job — multiple
cron workers is the supported case. The claim was retracted only once someone
read the fork's source instead of reasoning from the general architecture.

A load-bearing claim (one a gate, a doc, or a review decision depends on)
takes this shape:

```
claim → afenda file:path:line → observed behaviour → conclusion
```

never the anti-pattern it replaces:

```
claim → external URL → assume the fork behaves the same
```

`grep` alone does not establish observed behaviour: a check of whether a
migration calls `refresh_app_icons` once matched the function name inside a
docstring that said it is deliberately *not* called, implying the opposite of
the truth. Confirming the call site actually executes (an AST walk, or
running it) is what makes the claim load-bearing; a text match on a name is
not evidence of behaviour.

## Correction ledger

When a documented claim turns out to be false, retract it in place rather
than silently editing the prose. Record each retraction as an entry:

- `id`: `AFD-ARCH-CORR-nnnn`, sequential.
- `previous_claim`: the exact claim being retracted.
- `evidence`: a list of `path:line` citations that disprove it.
- `disposition`: `RETRACTED` or `AMENDED`.
- `replacement`: the corrected claim, or none if the original is simply
  removed.
- `introduced_in`: where the false claim first appeared (commit, doc, or ADR).

Three false claims surfaced in one day and are worth keeping as the reason
this exists: `CLAUDE.md` said port 8069 "is in a Windows reserved range and
cannot be bound" when a vendor service simply held the port; `afenda/README.md`
called the root `addons/` and `odoo/` trees "unmodified upstream"; and a
branch the README called "This deploys" in fact reports `product_name =
'Odoo'`. Each was corrected because someone checked the evidence, and the
ledger entry is worth more than a silently corrected sentence — it tells the
next reader why the claim changed instead of leaving them to wonder whether
it was ever true.

## Metrics discipline

No report, release gate, or architectural metric may combine authored and
derived deltas into one "changed files" number. Authored delta is what a
human changed; derived delta is what a tool (`afenda/tools/rebrand.py`)
generated from a rule. `git diff` against upstream reports 23,291 changed
files; of those, roughly 119 are hand-authored and roughly 23,172 are
rebrand-generated, and 90% of the generated set is translation files.
`odoo/http.py` alone shows 26 changed lines, of which exactly 2 are
behavioural. Report the two counts separately: 23,291 is a distribution
footprint, not a measure of complexity or risk, and adding the two numbers
together destroys the only signal either one carries.

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
