# AFENDA-owned API contract and generated documentation assets: design

Date: 2026-09-25. Status: **proposed, awaiting owner approval.** It follows
`2026-09-23-afenda-docs-generation-design.md`, which built the live `/docs/openapi.json`
and `/docs/api`.

## Goal (owner, 2026-09-25)

Documentation that is **AFENDA's own asset**, generated from our running system rather than
cloned or copied from Odoo. There are two deliverables, in this order:

1. **The API asset** (this spec, buildable). The JSON-2 API has a contract on AFENDA's
   terms. Its OpenAPI description is a versioned, committed, reviewable file set, and API
   changes are detected and listed between releases.
2. **The functional reference** (outlined here, specified separately after phase 1). It is
   generated end-user documentation (apps, screens, fields, statuses, access), with no hand
   writing, since the owner rejected hand-written guides.

## Where we are (verified in the tree)

- `afenda_api_docs.openapi.build_document(env, app)` builds OpenAPI 3.1 from the live
  registry, for the calling user: field schemas from `fields_get` and operations from
  `get_public_method`. It is served per request at `/docs/openapi.json` (`auth='user'`) and
  rendered by vendored Redoc at `/docs/api`.
- `info.version` is the constant `"2"` (`openapi.py:423`). Nothing is versioned or committed,
  so no two releases can be compared.
- **The error contract is Odoo's, including tracebacks.** `Json2Dispatcher.handle_error`
  (`odoo/http.py:2666-2688`) sends `serialize_exception` (`odoo/http.py:469-479`) for every
  error, 500s included. The body carries `name: "odoo.exceptions.AccessError"`, the exception
  `arguments` and `context`, and `debug`: the full server traceback. Any authenticated API
  caller receives our stack traces, and the published Error schema documents Odoo's shape.
- The retired line `archive/cloud-api-hardening` (commit `0eccdfa11`, not on `main`) already
  replaced this with RFC 9457 Problem Details, in `afenda_brand/models/ir_http.py`, with
  tests. That is reusable prior art, not a merge candidate: the line predates `main`'s layout.
- Upstream Odoo 19 ships its own explorer at `/doc` (`addons/api_doc`). It is not OpenAPI
  and not ours; this design does not depend on it.

## Phase 1: the API asset

### 1.1 Error contract: RFC 9457 Problem Details (security fix first)

- **What changes:** every `/json/2` error becomes `application/problem+json` with these fields:
  - `type`: an AFENDA URI, `https://www.nexuscanon.com/docs/api/errors#<code>`;
  - `title`: the HTTP reason phrase;
  - `status`;
  - `detail`: the user-safe message;
  - `code`: a stable AFENDA code, e.g. `access_denied`, `validation_error`, `not_found`,
    `unauthorized`, `internal_error`.
- **What is removed:** no exception class, arguments, context or traceback is ever sent. A
  500 logs its traceback server-side under a correlation id, which is returned as `instance`.
- **Where:** an override of the JSON-2 error path in `afenda_runtime`. That module holds
  production runtime behaviour, and production installs it. Never an edit under root `odoo/`.
  Port the design and tests from `0eccdfa11`, and re-verify every Odoo 19 hook it used against
  this tree.
- **Docs:** the OpenAPI `Error` schema, and the 401/403/404/422/500 responses, describe
  Problem Details.
- **Tests:** shape and codes for each class of error; no `debug`, `name` or `odoo` in any
  error body; 500s carry an `instance` id that matches a log line.

### 1.2 A stable, versioned document

- **`info.version`:** the AFENDA API version, `MAJOR.MINOR.PATCH`, kept in one place
  (`afenda_api_docs/api_version.py`) and bumped by the rule in 1.4. `x-afenda-build` carries
  the commit.
- **Determinism:** the same registry always gives byte-identical output. Keys are sorted,
  lists have a defined order, prose is in `en_US`, and there are no timestamps. A test proves
  it (build twice, compare).
- **operationIds:** `model.method` already, now declared stable. Renaming one is a breaking
  change under 1.4.

### 1.3 Committed asset files, checked like the guides

- **Files:** `docs/api/openapi/<app>.json`, one per supported app, plus `core.json`. These are
  the asset: owned, versioned in git, diffable in every PR.
- **Supported apps:** the product's actual footprint, which is the industry packs' dependency
  set: core, `contacts`, `product`, `sale`, `purchase`, `stock`, `mrp`, `point_of_sale`,
  `account`. Adding an app is a one-line change to a list in `afenda/tools/export_openapi.py`.
- **Generated as:** a dedicated API-reference role. That is an internal user with each
  supported app's manager group, never superuser, so the published document shows what a
  fully privileged integrator can reach and nothing `su`-only.
- **Tool:** `afenda/tools/export_openapi.py` runs through `odoo-bin shell` against a database
  with the supported apps installed. CI already builds exactly that database: the
  `afenda-image` job installs the packs, which pull in every supported app.
- **Gate:** CI regenerates the files and fails if they differ from the committed ones ("the
  API changed: run export_openapi and commit"). This is the same golden-file discipline as
  the rebrand corpus and the guides. So an API change can never ship silently: it shows up as
  a JSON diff in the PR.

### 1.4 Change detection and the changelog

- **Tool:** `oasdiff` (Apache-2.0, off the shelf) runs in CI on every PR, comparing
  `docs/api/openapi/` between `main` and the PR.
- **PR check:** it prints the change list and fails the check on a **breaking** change
  (removed operation, field or enum value, a newly required parameter, a changed type), unless
  the PR also bumps the API MAJOR version.
- **Version rule:** additive changes bump MINOR; fixes that don't change the contract bump
  PATCH.
- **Changelog:** `docs/api/CHANGELOG.md` is regenerated from oasdiff output when the version
  changes: the API's own release notes, written by the tool.

### 1.5 Client SDKs (release artifacts, not committed)

- **Generators:** off the shelf. `openapi-typescript` produces TypeScript types, and
  `openapi-python-client` produces a Python client, both from the committed files.
- **Where:** built in CI and attached to a GitHub Release when the API version changes. That
  lets a partner integrate without reading Odoo code.
- **Before it ships:** needs a smoke test that it compiles and imports.

### 1.6 Publishing

- `/docs/api` keeps serving the live, per-user document.
- The committed files are also served read-only at `/docs/api/spec/<app>.json` for signed-in
  users.
- **Not** published anonymously on `nexuscanon.com`. A public full model list is an owner
  decision, off by default.

### Acceptance for phase 1

- **Errors:** no `/json/2` response anywhere contains `debug`, `odoo.` or a traceback, shown
  by a test that forces a 500.
- **Determinism:** `export_openapi` twice gives identical bytes; CI fails on a stale
  committed file.
- **Breaking-change gate:** a deliberately breaking test change is caught by the oasdiff
  check, and an additive one is not.
- **Validity:** every committed document validates against the OpenAPI 3.1 meta-schema and
  contains no Odoo identity in prose (the existing `test_identity` rules, applied to the
  files).
- **Size:** each committed document stays under 1 MiB (today `base` is 995 KiB). If it does
  not, narrow what the document includes and record the reason.

## Phase 2: the functional reference (outline; its own spec follows phase 1)

**Generated from the registry**, per supported app:
- the menu tree;
- each menu's screens (window actions → views);
- each screen's fields, with label, help, required, and selection values;
- the record statuses (selection fields named `state`);
- who can see or edit it (groups and ACLs).

**Help links:** every in-product `documentation=` link becomes a generated page that
describes the setting it sits on: its label and help text, and the module it enables. So the
138 help links land on real content instead of a redirect.

**Pipeline:** the existing one. Generated Markdown is committed, `build_docs` produces QWeb,
`test_build_docs_sync` keeps them aligned, prose aliasing runs, and the identity crawl covers
the output.

**Known limit:** only about 27% of fields have help text. Pages list what the system knows
and no more, and they will be thin where Odoo wrote little. They are complete as a
reference, not as a tutorial.

## Ownership and licensing

- **Source:** everything is generated from our running code and registry. Odoo's user
  documentation (believed CC BY-SA) is neither read nor copied.
- **Licence of the output:** the labels and help strings it reuses come from LGPL-3 source
  code, which may be redistributed under its terms. The generated output is therefore ours to
  publish, with the LGPL notice that already covers the code. This is an engineering reading,
  not legal advice.
- **Identity:** it stays out of prose by the same aliasing and identity tests as today. Wire
  values stay verbatim.

## Out of scope

- Hand-written guides (owner decision).
- G2.
- Public anonymous publication.
- Versioned `/docs/<version>/` URLs (the version segment stays accepted and ignored).
- Documenting XML-RPC or `/jsonrpc`.

## Decisions needed from the owner

1. **Approve phase 1 as written**, including the new error format. It changes what API
   callers receive. If no outside system calls `/json/2` yet (only you know this), now is the
   cheapest moment to change it.
2. **Confirm the supported-app list** in 1.3, or name other apps.
3. **SDKs (1.5): now, or later?** They are optional for phase 1's value.
