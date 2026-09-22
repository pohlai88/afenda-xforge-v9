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
.venv/Scripts/python -m afenda.tools.scan_identity   # must print 0 remaining
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
.venv/Scripts/python -m afenda.tools.scan_identity     # exit 1 if any Odoo identity remains
.venv/Scripts/python -m unittest discover -s afenda/tools/tests -t . -v
```

Rules live in `afenda/tools/rules.py`; names and domain in
`afenda/addons/afenda_brand/brand.py`. A line ending in `# noqa: rebrand`
is never rewritten.

Rule changes are reviewed on the corpus, never on the tree:
`python -m afenda.tools.corpus diff` shows exactly what a rule change alters;
after review, `python -m afenda.tools.corpus golden` and commit both files.
