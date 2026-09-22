# Odoo de-identification for AFENDA xForge — design

Date: 2026-09-22. Status: approved in conversation, awaiting written review.

## Goal

Launch AFENDA xForge as a SaaS on top of Odoo 19.0 Community with no
Odoo identity visible to users, customers, email recipients, or anyone
inspecting the product from a browser, while keeping upstream Odoo
updates mechanical. A later rewrite into a TypeScript stack is out of
scope here and nothing in this design blocks it.

## What counts as identity

Surfaces, in the order a user meets them:

1. Screens: every string rendered by the web client, portal, website,
   login, error pages, database manager, PWA manifest.
2. Translations: `.po` and `.pot` files for all languages, since a user
   in French sees the French string.
3. Emails and PDFs: mail templates, notification layouts, digest,
   report titles, report layouts.
4. Links: every `odoo.com` URL (documentation, support, upsell, privacy).
5. Addresses: the `/odoo/...` URL prefix in the browser bar.
6. Images: Odoo logos and app icons shipped under `addons/*/static`.
7. Developer tools: `window.odoo` JavaScript global, the `@odoo/` module
   namespace visible in bundled sources.

Not identity, stays untouched: the Python package `odoo`, `odoo-bin`,
module technical names, database schema, source license headers
("Part of Odoo", "Odoo S.A."), `LICENSE` and `COPYRIGHT`. These are
invisible to a SaaS user and are the copyright notices the license
requires to remain.

## Architecture

### Branches

- `upstream-19.0`: pristine odoo/odoo, never edited. Fetched from the
  `upstream` remote.
- `19.0`: `upstream-19.0` + one rebrand commit produced by the script
  + the `afenda/` layer commits. This is what deploys.

Updating Odoo: fetch and merge `upstream` into `upstream-19.0`, merge
that into `19.0`, re-run the script, commit the delta. The script is
idempotent: it only changes what still says Odoo.

### Rebrand engine: `afenda/tools/rebrand.py`

- Walks `addons/` and `odoo/`, skipping `.git`, `.venv`, `afenda/`,
  binary files, and tests (`*/tests/*`) unless a rule opts in.
- Ordered rules, each a (file glob, regex, replacement, description).
  Rules match the standalone capitalized word `Odoo` (`\bOdoo\b`) and an
  explicit list of compounds (`OdooBot`, `Odoo S.A.` inside user-facing
  text only). Identifiers such as `OdooEditor`, `odoo.define`,
  `import odoo`, `@odoo/owl` never match phase-1 rules by construction.
- A protected-context list: lines that are license headers, `import`
  statements, or inside `# noqa: rebrand` markers are skipped.
- Dry-run mode prints per-rule counts and sample lines; apply mode writes.
- Reads names and domain from `afenda/addons/afenda_brand/brand.py`
  (product name, short name, bot name, domain).

### Phase 1 rules (launch blockers)

| Rule | Files | Replacement |
|---|---|---|
| Product name in text | xml, js, py, html, md, po, pot | `Odoo` → `AFENDA xForge` |
| Bot | same | `OdooBot` → `AFENDA Bot` |
| Links | all text files | `https://www.odoo.com/documentation/...` → `https://afenda.app/docs/...`; other `odoo.com` links → `https://afenda.app` |
| URL prefix | py routes, js router, xml/js hardcoded paths | `/odoo` → `/app`; `/odoo/<path>` → `/app/<path>`; the `odoo` router prefix constant |
| Database manager | `addons/web/static/src/public/database_manager.qweb.html` | wording |
| Error pages | `odoo/http.py` and `odoo/addons/base/...` templates | wording |
| Images | files matching `*odoo*logo*`, `odoo-icon-*`, `odoo_logo*` | replaced by AFENDA renders under the same file names |
| Config | `pwa`, `web.web_app_name` defaults | AFENDA defaults |

Translation files: for each `.po`/`.pot`, apply the product-name and
bot rules to `msgid` and `msgstr` lines only. Odoo matches translations
by `msgid`, so changing the source string in code and the `msgid` in
every `.po` keeps every language translated.

### Phase 2 rules (developer tools)

- `window.odoo` global → `window.afenda`: `var odoo =` definitions in
  templates, `odoo.` member access in JavaScript (335 uses), the asset
  loader's `odoo.define`/`odoo.loader`.
- `@odoo/` module namespace → `@afenda/` in import strings and manifest
  asset paths (4,072 imports).
- Applied only after phase 1 is green, in its own commit, because these
  can break JavaScript at scale and need the full web test run.

### Phase 3 (post-launch, content)

- `afenda/upstream/documentation`: shallow submodule of
  `odoo/documentation` at the 19.0 branch. Text rebranded by the same
  script, screenshots retaken on AFENDA, hosted at `afenda.app/docs`.
  Until then `afenda.app/docs` serves one "documentation coming soon"
  page.
- `paper-muncher` for PDF rendering, evaluated as a replacement for
  wkhtmltopdf.

## Verification

- `afenda/tools/scan_identity.py`: lists remaining `Odoo` and `odoo.com`
  on user-visible surfaces (everything except the protected contexts),
  exits non-zero if any. Runs in CI and after each upstream update.
- `afenda_brand` tests gain a crawl: login page, `/app`, Settings, a
  rendered `mail.mail_notification_layout`, a PDF report converted to
  text, the PWA manifest, and the database manager page; each asserts
  no `Odoo` and no `odoo.com`.
- Odoo's own `web` test tags run once after the URL prefix change and
  once after phase 2, using the existing `--test-tags` command in
  `afenda/README.md`.
- Existing 7 branding tests keep passing.

## Error handling and safety

- The script refuses to run on a dirty working tree and prints a
  dry-run summary before applying.
- Every apply is one commit prefixed `[REBRAND]` so it can be reverted.
- Protected contexts are enforced by tests in
  `afenda/tools/tests/test_rebrand.py` with fixture snippets (a license
  header, an import line, an `OdooEditor` identifier, a `.po` entry, a
  route decorator) proving what changes and what does not.

## Out of scope

- Renaming the Python package, JS class names, module technical names.
- Removing or altering license headers, `LICENSE`, `COPYRIGHT`.
- The TypeScript rewrite.
- Website themes (`design-themes`) unless the Website app ships.

## Decisions taken in conversation

- Depth: everything a user or a browser inspector can see; not the
  Python package.
- Domain placeholder: `afenda.app`, to be replaced once the real domain
  is known.
- Documentation: cloned now, rebranded in phase 3.
- Local development database keeps the default admin login.
