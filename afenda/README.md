# AFENDA xForge layer

Everything hand-authored for AFENDA lives in this folder. The `addons/` and
`odoo/` folders at the repository root are **not** pristine upstream: the identity
transform in `tools/` rewrites text and images across both, so an upstream merge
touches tens of thousands of files. Those rewrites are generated output, never
hand edits — which is what makes re-deriving them cheaper than merging them. See
`docs/superpowers/specs/2026-09-23-afenda-platform-architecture.md`.

```
afenda/
  addons/afenda_brand/        the AFENDA identity: logo, colors, fonts, titles, login, settings
  addons/afenda_api_docs/     /docs: user guides, and the API reference generated from the live registry
  addons/afenda_industry_base/    the industry preset contract (seed helper, test mixin)
  addons/afenda_industry_bakery/  the bakery preset: catalogue, bills of material, POS, replenishment
  addons/afenda_runtime/      null adapters for Odoo-hosted services: nothing leaves the deployment
  addons/afenda_brand_digest/ AFENDA colors in the periodic digest email (auto-installs)
  oca/server-brand/           OCA debranding modules (git submodule, branch 19.0)
  oca/web/                    OCA web modules: favicon, PWA, no bubbles (git submodule, branch 19.0)
  tools/                      the rebrand engine, icon generators, identity scanner
  odoo.conf                   local development configuration
```

## First run

```bash
git submodule update --init --depth 1
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -i afenda_brand --stop-after-init --without-demo=all
.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda
```

Then open http://localhost:8169. `odoo.conf` expects PostgreSQL on
127.0.0.1:5444 with a superuser named `odoo` and no password; change
`db_port`, `db_user` and `db_password` to match your server.

## What `afenda_brand` changes

Installing `afenda_brand` pulls in the OCA modules and applies the identity:

| Where a user sees it | What changes |
|---|---|
| Browser tab | "AFENDA xForge" instead of "Odoo"; AFENDA favicon, or the company's own if one is set (`web_favicon`) |
| Login page | AFENDA logo on a paper ground, one white card with a hairline edge, the tagline "The truth of your business, kept.", no "Powered by Odoo" link |
| Web client | Ledger Blue primary, Ink `#0F172A` navbar, paper background, Source Sans 3 / Source Serif 4 / Source Code Pro, tabular figures on every number |
| Semantic colors | Ember `#C2410C` attention, Verified `#15803D` posted, Flag `#B91C1C` error, replacing Odoo's green/orange/pink palette (light and dark schemes) |
| Apps menu | All 108 module icons redrawn as AFENDA tiles; unmapped modules and the base fallback get the AFENDA mark on graphite. Third-party payment-provider marks are deliberately left alone |
| Empty states | One ledger-page drawing instead of Odoo's smiling face, neutral face and folder |
| Effects and errors | The rainbow man is replaced by a one-line success notification; the error dialog says "Something went wrong", not "Oops!" |
| User menu | "Help" opens AFENDA's documentation; odoo.com entries removed (`disable_odoo_online`) |
| Settings | "AFENDA xForge 19.0" edition block, Enterprise upsells removed (`remove_odoo_enterprise`) |
| Emails | AFENDA notification and digest layouts: Ledger Blue call-to-action on white text, paper frame, hairline card edge, the AFENDA mark where "Powered by Odoo" linked out |
| Printed documents | Standard layout, Source Sans 3 (static instances the PDF engine can use), ink and graphite accents, hairline table rules, tabular figures |
| Portal | The footer "Powered by" line is replaced through `web.brand_promotion_message`, in this module. The record sidebar keeps its own "Powered by" line (`addons/portal/views/portal_templates.xml:282`), rebranded to the AFENDA lockup — see the OCA note below |
| PWA / mobile | App name "AFENDA", theme color Ledger Blue, maskable icons, branded offline page (`web_pwa_customize`) |
| Companies | Default logo is the AFENDA lockup; a company still named "My Company" is renamed "AFENDA" at install |

### The mark, and which colourway goes where

The Engineered X is declared once, in `afenda/tools/brand_images.py`, as
`MARK_ARMS`: four tapered wedges in a 100-unit frame, ink box 23..77, meeting at
a diamond void. Every raster and vector surface scales that one tuple — there is
no second copy of the shape in the repo, and `MarkGeometryTests` pins it against
a hand transcription of the artwork.

It ships in three approved colourways, and `TARGETS` is the only place that says
which surface gets which:

| Colourway | Ground | Radius | Mark | Where |
|---|---|---|---|---|
| `PRIMARY` | Ink `#09111F` | 22.5% | Two-tone: steel `#D9DEE5`/`#AAB3C0` west, Signal Blue `#659CFF`/`#1F6FFF` east | The badge, where it stands outside the running app: PWA and home-screen icons, the store listing, `afenda_brand`'s own icon set, the login lockup |
| `LIGHT` | White, `#E3E8EF` hairline | 22.5% | Two-tone: `#6C7581`/`#464F5A` west, `#1F6FFF`/`#0049C1` east | The badge on a surface that is already white and would otherwise read as a sticker |
| `IN_PRODUCT` | Ledger Blue `#1E3A8A` | 20% | White, one fill | Anything a signed-in user sees while working: the browser tab, the apps-menu fallback, the bot avatar, report artwork |

Two rules the pipeline enforces rather than documents. The bare mark — no tile,
on transparency — is always one fill (Ledger Blue): a two-tone step needs a known
ground behind it, and without one it reads as a gradient. And the 108 module
icons are untouched by all of this; they stay free-standing duotone glyphs, so
the apps menu never mixes a four-fill mark into a row of two-colour ones.

The lockup pairs the bare mark with the wordmark in Geist — `AFENDA` tracked
above, `xForge` below with the `x` in Signal Blue. Geist lives in
`afenda/tools/fonts/`, not in the addon: Odoo serves everything under
`<addon>/static/` over HTTP whatever the manifest says, so a typeface put there
would be reachable at a URL and would ship in every deployment for no runtime
reason. Keeping it beside the renderer is what makes "Geist never reaches the
product" structural rather than a convention. The generated SVG lockups carry
the wordmark as outlines rather than a `font-family`, so nothing downstream
needs the face either, and the product's type system stays Source Sans 3 /
Source Serif 4 / Source Code Pro.

No external font request remains in a stock install. `addons/web/static/fonts/fonts.scss`'s
non-Latin Noto fallback faces (Cyrillic, Hebrew, Arabic, Telugu) used to load from
`fonts.odoocdn.com`; the `noto_cdn_local` rebrand rule (`afenda/tools/rules.py`) rewrites
each `@font-face`'s `url(...) format(...)` term to `local(...)`, so the browser resolves
the face locally instead of reaching Odoo's CDN. Latin text is served entirely from
`afenda_brand/static/fonts/`.

### OCA dependencies

The rebrand rewrites Odoo's own strings, which turns out to defeat OCA debranding
modules that detect those strings. Audited at 2026-09-23:

| Module | What it is for | Still effective | Evidence |
|---|---|---|---|
| `disable_odoo_online` | Removes the odoo.com user-menu entries and stops the publisher-warranty ping | yes | `user_menuitems` still registers `support`/`odoo_account` (`addons/web/static/src/webclient/user_menu/user_menu_items.js:139-143`); `publisher_warranty.contract` still exists (`addons/mail/models/update.py:20`) and its cron still runs |
| `remove_odoo_enterprise` | Hides Enterprise-only modules and upsell settings | yes | `ir.module.module.to_buy` and `payment.provider.module_to_buy` still exist; `widget="upgrade_boolean"` is still used by `account`, `base_setup` and others |
| `web_favicon` | Per-company favicon | yes | `res.company.favicon` comes from it, the install hook writes it, and `web.layout` resolves it through `_get_favicon()` |
| `web_pwa_customize` | PWA name, colors and icons | yes | The install hook and `controllers/webmanifest.py` both build on it |
| `web_no_bubble` | Hides the tour pointer bubbles | yes | `.o_tour_pointer` is still the class `web_tour` renders (`addons/web_tour/static/src/js/tour_pointer/tour_pointer.xml:8`) |
| `mail_debranding` | Strips `<a href="…odoo.com…">` from outgoing mail | **no — dropped from `depends`** | It only acts when the body still contains an odoo.com anchor (`mail_render_mixin.py:28-32`). No `odoo.com` href survives anywhere in `addons/` or `odoo/`, so it never fires. Its own suite now fails on a rebranded database for the same reason |
| `portal_debranding` | Hides the login and portal "Powered by" | **no — not installed** | Its login xpath anchors on that same rewritten href (`views/web_login_debrand.xml:5-9`) and would raise on an unmatched xpath at install. The login line and `web.brand_promotion` are handled by `views/webclient_templates.xml` instead; the record-sidebar line it would also have hidden now reads "Powered by AFENDA", which is on-brand rather than an Odoo tell |

If you also install the `website` app, add `website_debranding` from
`oca/server-brand` to remove the website footer branding — and check first that
its own detection has not been defeated the same way.

Brand values (colors, names) are defined once in `addons/afenda_brand/brand.py`
and mirrored in `static/src/scss/primary_variables.scss`.

## Branches and upstream updates

- `main`: **the one branch** — the product, what production runs: the identity
  transform, the AFENDA modules, the tooling. Branch short-lived work off it.
- Upstream is the `upstream` remote (`odoo/odoo`, branch `19.0`), not a branch here.
- Retired branches are tags under `archive/` (2026-09-25): `archive/19.0` (the old
  default, which never carried the identity transform), `archive/upstream-19.0`
  (the pristine anchor, root `19ebd007c`), `archive/brand-identity`,
  `archive/cloud-api-hardening` (a cloud session's unmerged API work) and
  `archive/industry-packs-wip` (the unfinished industry preset packs).

### Taking an Odoo update

⚠️ **The procedure that used to be documented here could not run.** This checkout is
shallow (`.git/shallow`) and `upstream-19.0` is an orphan root commit, so
`git merge-base upstream/19.0 HEAD` returns nothing and
`git merge --ff-only upstream/19.0` refuses. `--allow-unrelated-histories` does not
apply to `--ff-only`, so the old note contradicted the old command.

Fix the ancestry once, then the update becomes routine. The fork's anchor
(`archive/upstream-19.0`, root `19ebd007c`) has a tree byte-identical to upstream
`2d1b7a131`, so a LOCAL anchor branch on the real upstream commit moves no content.
It stays local: the repository keeps one branch, `main`.

````bash
git fetch --unshallow upstream 19.0
git branch upstream-19.0 2d1b7a131
````

After that:

````bash
git fetch upstream 19.0
git checkout upstream-19.0 && git merge --ff-only upstream/19.0
git log upstream-19.0@{1}..upstream-19.0 --stat   # read this — it is the review
git checkout main && git merge upstream-19.0
.venv/Scripts/python -m afenda.tools.rebrand --apply  # re-brands only what is new
.venv/Scripts/python -m afenda.tools.scan_identity    # triage any rise, re-floor any drop
````

Then commit **explicit paths** — never `git commit -am` or `git add -A`. After a
rebrand run the working tree holds tens of thousands of modified files, and `-a`
would also sweep in anything a colleague has in flight in the same checkout:

````bash
git commit --only -F msgfile -- odoo addons afenda
````

The long-term fix is to stop storing generated output as source, so an upstream
merge touches the ~119 hand-authored files instead of 23,000. See
`docs/superpowers/specs/2026-09-23-afenda-platform-architecture.md`.

## De-identification tools

```bash
.venv/Scripts/python -m afenda.tools.rebrand           # dry run, per-rule counts
.venv/Scripts/python -m afenda.tools.rebrand --apply   # rewrite addons/ and odoo/
.venv/Scripts/python -m afenda.tools.brand_images      # AFENDA images over Odoo's logo paths
.venv/Scripts/python -m afenda.tools.scan_identity     # exit 1 if the count rose above BASELINE
.venv/Scripts/python -m afenda.tools.build_docs        # regenerate guide QWeb from Markdown
.venv/Scripts/python -m unittest discover -s afenda/tools/tests -t . -v
```

Rules live in `afenda/tools/rules.py`; names and domain in
`afenda/addons/afenda_brand/brand.py`. A line ending in `# noqa: rebrand`
is never rewritten.

### The identity baseline

`scan_identity` is a regression gate, not a zero-tolerance check. It scans
broader than the rewrite rules on purpose — case-insensitively, and without
reusing `RULES` — so a blind spot in the rules cannot also blind the check.
That breadth means it always finds identity the rules must *not* touch:
translator attribution in `.po` headers, the `odoo` package name in imports,
API payload identifiers third parties have registered, and spreadsheet formula
names such as `ODOO.PIVOT` that live inside saved documents.

So the expected steady state is a **non-zero** count. The gate is that it must
not rise. The current floor is recorded as `BASELINE` in
`afenda/tools/scan_identity.py` and is **10,826**. If a change legitimately
lowers the count, lower `BASELINE` in the same commit so the new floor holds.

Rule changes are reviewed on the corpus, never on the tree:
`python -m afenda.tools.corpus diff` shows exactly what a rule change alters;
after review, `python -m afenda.tools.corpus golden` and commit both files.

## Documentation at /docs

`/docs` is served by `afenda_api_docs`:

- **Guides** are authored as Markdown in `afenda/addons/afenda_api_docs/docs/`,
  mirroring the `documentation=` paths the product links to. `views/guides.xml`
  is generated from them by `python -m afenda.tools.build_docs` and committed;
  never hand-edit it (`afenda/tools/tests/test_build_docs_sync.py` fails if the
  two disagree). A link to a page with no guide yet redirects to `/docs`.
- **The API reference** is `/docs/api` (a vendored Redoc, no CDN) over
  `/docs/openapi.json`, an OpenAPI 3.1 document generated per request from the
  live registry for the signed-in user (`auth='user'`), scoped per app with
  `?app=<module>`.
- Odoo identity is aliased to AFENDA in prose only, never in wire values
  (model names, field names, selection keys); `tests/test_identity.py` crawls
  the pages and documents to hold that line. `scan_identity` does not cover
  `afenda/`, so those tests are this module's identity gate.
