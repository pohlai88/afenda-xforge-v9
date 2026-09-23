# AFENDA xForge layer

Everything AFENDA-specific lives in this folder. The `addons/` and `odoo/`
folders at the repository root are unmodified upstream Odoo 19.0, so upstream
updates merge cleanly.

```
afenda/
  addons/afenda_brand/   the AFENDA identity: logo, colors, fonts, titles, login, settings
  oca/server-brand/      OCA debranding modules (git submodule, branch 19.0)
  oca/web/               OCA web modules: favicon, PWA, no bubbles (git submodule, branch 19.0)
  odoo.conf              local development configuration
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

One external request remains in a stock install: `addons/web/static/fonts/fonts.scss`
loads the non-Latin Noto fallback faces from `fonts.odoocdn.com`. Latin text is
served entirely from `afenda_brand/static/fonts/`; the CDN is only reached when a
page renders CJK, Arabic or similar. Removing it is phase-2 work.

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

- `upstream-19.0`: pristine odoo/odoo. Never edit.
- `19.0`: `upstream-19.0` + the `[REBRAND]` commit + the `afenda/` layer. This deploys.

To take an Odoo update:

````bash
git fetch upstream 19.0
git checkout upstream-19.0 && git merge --ff-only upstream/19.0 && git push
git checkout 19.0 && git merge upstream-19.0        # resolve conflicts if any
.venv/Scripts/python -m afenda.tools.rebrand --apply # re-brands only what is new
.venv/Scripts/python -m afenda.tools.scan_identity   # must not rise above the baseline
git commit -am "[REBRAND] re-apply after upstream merge"
````

Note: `upstream/19.0` history is unrelated to our rewritten root, so the
first merge needs `--allow-unrelated-histories`; see the spec for why the
root was rewritten.

## De-identification tools

```bash
.venv/Scripts/python -m afenda.tools.rebrand           # dry run, per-rule counts
.venv/Scripts/python -m afenda.tools.rebrand --apply   # rewrite addons/ and odoo/
.venv/Scripts/python -m afenda.tools.brand_images      # AFENDA images over Odoo's logo paths
.venv/Scripts/python -m afenda.tools.scan_identity     # exit 1 if the count rose above BASELINE
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
`afenda/tools/scan_identity.py` and is **10,838**. If a change legitimately
lowers the count, lower `BASELINE` in the same commit so the new floor holds.

Rule changes are reviewed on the corpus, never on the tree:
`python -m afenda.tools.corpus diff` shows exactly what a rule change alters;
after review, `python -m afenda.tools.corpus golden` and commit both files.
