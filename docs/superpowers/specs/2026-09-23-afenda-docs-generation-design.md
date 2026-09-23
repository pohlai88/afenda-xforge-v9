# AFENDA xForge generated documentation — design

Date: 2026-09-23. Supersedes the "Phase 3 (post-launch): generated
documentation" section of `2026-09-22-odoo-deidentification-design.md`,
which was a direction rather than a buildable design and is wrong in
three places (recorded under Corrections below).

## Goal

Serve `/docs` with documentation generated from the running system, so it
is always current and carries no Odoo identity. Two audiences, confirmed
in conversation: external integrators calling the JSON API, and end users
who click a help icon in Settings.

## What exists today

- `/docs` and `/docs/<path:subpath>` are answered by
  `afenda_brand.controllers.main.AfendaDocsController`, which renders a
  "coming soon" placeholder for every path.
- The help item in the user menu opens `BRAND["docs_path"]` (`/docs/`).
- 117 `documentation="/applications/..."` attributes across Settings
  views now resolve same-origin. The `documentation_link` widget builds
  `"/docs/" + serverVersion + path`, so the live shape is
  `/docs/19.0/applications/finance/...`.

All three currently land on the placeholder.

## The API surface being documented

`addons/rpc/controllers/json2.py:50`:

```python
@http.route('/json/2/<__model__>/<__method__>', methods=['POST'],
            auth='bearer', type='json2', readonly=_web_json_2_rpc_readonly,
            save_session=False)
```

The request body is JSON: `ids` (list of int), `context` (mapping), and
the remaining keys bound to the method signature via
`inspect.signature(func).bind(records, **kwargs)`. Errors are 404 for an
unknown model or method and 422 for a signature mismatch or for passing
`ids` to an `@api.model` method.

Which methods are callable is decided by `get_public_method`
(`odoo/service/model.py:45`): not `_`-prefixed, not in
`_UNSAFE_ATTRIBUTES`, not decorated `@api.private`, not a classmethod or
staticmethod.

**The generator calls that function rather than reimplementing the rule.**
Any reimplementation drifts, and the docs come to describe operations
that 404.

## Architecture

A single new module, `afenda/addons/afenda_api_docs`, depending on
`base`, `rpc` (owner of the `/json/2` route) and `afenda_brand` (owner of
the brand values). It takes the `/docs` route over from `afenda_brand`.

### Routes

| Route | Auth | Serves |
| --- | --- | --- |
| `/docs` | public | Landing page: guides and API reference |
| `/docs/<version>/applications/<path>` | public | Authored narrative pages |
| `/docs/applications/<path>` | public | Same, without a version segment |
| `/docs/api` | **user** | Vendored reference UI |
| `/docs/openapi.json` | **user** | OpenAPI 3.1 document, scoped by `?app=` |

The version segment is accepted and ignored. It exists only because the
web client's widget concatenates one; the generated documentation is not
versioned.

A path with no authored page renders a "not written yet" page naming the
setting it was reached from — never a 404, and never a redirect
off-origin.

### Why the OpenAPI document is scoped per app

The registry holds roughly 1,217 models and 10,869 field definitions. A
single document covering all of it is tens of megabytes, and no reference
UI will render it. `/docs/openapi.json?app=sale` emits only the models
that module defines, keeping each document in the low hundreds of
kilobytes. `/docs/api` presents an app picker.

Membership is resolved through `ir.model.data`, not through
`ir.model.modules`. The latter reads as the obvious choice and is not:
it is a non-stored computed field (`ir_model.py:241`,
`compute='_in_modules'` with no `store=True`), so it cannot appear in a
search domain and would have to be computed for all 1,217 models and
filtered in Python. The query is instead:

```python
env['ir.model.data'].search([('module', '=', app), ('model', '=', 'ir.model')])
```

which is stored and indexed.

With no `app` parameter, a curated core set is emitted — `res.partner`,
`res.users`, `product.template`, `sale.order`, `account.move`,
`stock.picking` — so the default URL is useful rather than empty. The set
is intersected with the registry first, since a model whose module is not
installed does not exist.

### The generator

Per model the calling user can read, for each method passing
`get_public_method`:

- **path**: `/json/2/{model}/{method}`, `post`
- **requestBody**: object with `ids` (array of integer), `context`
  (object), and one property per parameter of `inspect.signature(func)`,
  typed from the annotation where present and left untyped where not
- **responses**: `200`, plus `404` and `422` referencing a shared error
  schema built from the dispatcher's own error shape
- **components.schemas**: one schema per model from `fields_get()` —
  type, `required`, `readonly`, relation target for relational fields,
  and selection pairs

Generation is per request, with no cache in v1. If a document is observed
to take longer than about 500 ms to build, cache it in an `ormcache`
keyed on app, language, registry version and the caller's group set — the
key must include groups, because the document is already filtered by what
the caller can read.

### Brand aliasing

The single stated requirement: Odoo identity is aliased to AFENDA
automatically. Every string in the generated document falls into exactly
one of two classes, and conflating them breaks the API.

**Wire values — never aliased.** Model names, field names, method names,
parameter names, selection keys, and any identifier a caller must send
back verbatim. These really do carry the name: `odoobot_state` and
`odoobot_failed` on `res.users`, the selection key `delete_odoo`,
spreadsheet function names such as `ODOO.BALANCE` and `ODOO.FILTER.VALUE`,
and command identifiers such as `INSERT_ODOO_LIST`. Renaming any of them
in the documentation tells an integrator to send a value the server
rejects.

**Prose — always aliased.** `summary`, `description`, a field's `string`
and `help`, selection labels, a model's `_description`, and method
docstrings.

Aliasing is applied at the prose insertion points as the document is
built, never by scanning the finished JSON. That makes the split
structural rather than heuristic: a post-hoc scan of the assembled
document would have to guess which strings are keys, and would eventually
guess wrong on exactly the payload identifiers above.

The rules are the ordered brand rules from `afenda_brand`, with one
deliberate difference from the build-time rules in
`afenda/tools/rules.py`: **prose aliasing is case-insensitive on the
standalone word.** The file-level rules match only capitalised `Odoo`,
because a file contains imports, license headers and module paths where
lowercase `odoo` must survive. A prose field contains none of those, so
the roughly 10,800 lowercase occurrences the file rules deliberately skip
are precisely what a reader of these pages would otherwise see. Word
boundaries keep this safe: `\bodoo\b` does not match inside
`odoobot_state`.

A test pins the two rule sets against each other on shared cases, so the
runtime aliaser cannot drift from the build-time one. This is viable:
`afenda.tools.rules` imports cleanly from the repo root, which is where
`odoo-bin` runs, so the test can hold both rule sets side by side.

### The narrative half

Pages are authored as Markdown under `afenda_api_docs/docs/`, mirroring
the `documentation=` paths the Settings widget emits, and converted to
QWeb templates at build time by a new `afenda/tools/build_docs.py`. Both
the Markdown and the generated XML are committed, and a test asserts they
agree — the same golden-file discipline the corpus already uses.

Build time rather than request time because no Markdown library is
installed in the environment today, and this keeps the runtime free of a
new Python dependency. Rendering through QWeb also makes the pages
translatable by Odoo's normal mechanism.

Authoring is deliberately not generated. The `ir.model.fields` help text
proposed in the superseded spec covers about 2,910 of 10,869 field
definitions — roughly 27% — so a reference built from it is
three-quarters empty. The problem is not that the help text carries Odoo
identity; measurement shows only 6 of the scanner's 10,838 hits sit on a
`help=` line, all of them technical. The problem is that there is not
enough text to make a reference out of.

### The reference UI

Redoc (MIT), vendored as its standalone bundle into `static/lib/`. No
CDN: the page must work offline, same-origin, and carry no third-party
identity. It is a user-visible AFENDA surface and consumes the same
design tokens as the web client.

Redoc over Scalar or Swagger UI because it is read-only. `/json/2` is
`auth='bearer'`, so an in-page "try it" console cannot borrow the
browser session and would need an API key pasted into the page to do
anything — an interactive console here is a credential prompt wearing a
useful hat. A reference that only reads avoids that.

## Security

`/docs/openapi.json` and `/docs/api` are `auth='user'`. The superseded
spec said public. A listing of every model and field a caller can read is
an information-disclosure surface and should require a session; the
document is already filtered per user, which is meaningless if it can be
fetched anonymously. The narrative pages stay public.

## Verification

- The emitted document validates against the OpenAPI 3.1 meta-schema.
- Every path in the document resolves to a method that
  `get_public_method` accepts, asserted by calling it.
- Aliasing: a rendered page and a generated document contain no `Odoo` in
  prose, and `odoobot_state`, `delete_odoo` and `ODOO.BALANCE` survive
  verbatim where they are wire values.
- A crawl test over `/docs`, `/docs/api` and a narrative page, matching
  the existing `afenda_brand` crawl tests.
- `afenda/tools/scan_identity.py` must not rise above `BASELINE`
  (currently 10,838). This module adds user-visible text, so the gate
  applies to it directly.

## Corrections to the superseded spec

1. `/json/2` is served by the `rpc` module, not core `web`. The spec
   cited `odoo/http.py, routing_type = 'json2'`, which is the dispatcher,
   not the route.
2. The model reference generated from `ir.model` and `ir.model.fields`
   help text is dropped, on coverage.
3. `/docs/openapi.json` is `auth='user'`, not public.

## Out of scope

- Versioned documentation. The version segment is accepted and ignored.
- Documenting XML-RPC or `/jsonrpc`; `/json/2` is the documented surface.
- `paper-muncher` PDF rendering, which the superseded spec bundled into
  phase 3 and is unrelated to documentation.

## Sequencing note

`/docs` currently belongs to `afenda_brand`. Two controllers claiming one
route collide, so removing `afenda_brand`'s placeholder controller and
`docs_placeholder.xml` must happen in the same change that adds this
module. `afenda_brand` is being actively worked on by another session;
that removal is coordinated, not unilateral.

## Decisions taken in conversation

- Both audiences, not one: API reference and narrative pages.
- Generated from the live registry rather than a hand-maintained OpenAPI
  file, accepting that this needs a generator, because a hand-written
  file goes stale the moment a field changes.
- Off-the-shelf everywhere it is possible: OpenAPI 3.1 as the format, a
  vendored standard reference UI, the published meta-schema as the
  validator. The generator exists only because Odoo exposes one dynamic
  route, which standard introspecting generators render as a single
  meaningless path.
- Automatic Odoo-to-AFENDA aliasing is the one stated requirement, split
  into prose and wire values as above.
