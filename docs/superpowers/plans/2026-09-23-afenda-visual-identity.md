# AFENDA xForge visual identity — implementation plan

Date: 2026-09-23. Spec: `docs/superpowers/specs/2026-09-22-odoo-deidentification-design.md`
(text de-identification, done) plus the design context and decisions in
`C:\Users\dlbja\.claude\plans\provide-me-the-current-glimmering-puzzle.md`.

## Context

Odoo 19.0 Community is white-labeled as AFENDA xForge. Text de-identification is
converged (`scan_identity` = 0). The `afenda_brand` addon swaps the accent color and font
family only. This plan replaces Odoo's *visual* identity: semantic colors, navbar, login,
PDF reports, email, app icons, and the images that still carry the Odoo wordmark.

Decisions (user, 2026-09-23): tokens plus key screens; generate all 108 app icons;
navbar Ink #0F172A.

## Global constraints (binding for every task)

- Odoo 19.0 only. Root `odoo/` and `addons/` are upstream and are never hand-edited.
  Sanctioned ways to change them: `afenda/tools/rebrand.py` text rules (through the
  corpus golden test) and `afenda/tools/brand_images.py` image targets. Everything else
  lives in `afenda/addons/afenda_brand/` (abbreviated `ADDON/`) or a sibling addon.
- Brand values come from `ADDON/brand.py` (`BRAND` dict) and are mirrored in
  `ADDON/static/src/scss/primary_variables.scss`. Never hard-code a brand hex elsewhere
  except where SCSS variables cannot reach (inline email styles, offline page), and then
  use the exact values below.
- Brand values: primary Ledger Blue `#1E3A8A`; ink `#0F172A`; paper `#F7F7F5`; graphite
  `#4B5563`; hairline `#E5E7EB`; ember `#C2410C` (attention, unposted, overdue); verified
  `#15803D` (posted, reconciled); flag `#B91C1C` (error, locked); on_primary `#FFFFFF`.
  Fonts self-hosted under `ADDON/static/fonts/`: Source Sans 3 (UI), Source Serif 4
  Semibold (display only, never global headings), Source Code Pro (references, money;
  tabular figures). Mark: "A over a double total rule", never an X. Tagline: "The truth
  of your business, kept."
- Principles: quiet by default (color means a state), calm surfaces, dense data,
  precision not decoration.
- View XML: `<list>` not `<tree>`; no `attrs`/`states`. Frontend: registry, service,
  hook, view architecture before `patch()`.
- Tests: Odoo `HttpCase`/`TransactionCase` under `ADDON/tests/`, tagged
  `post_install`, `-at_install`; tools tests are `unittest` under `afenda/tools/tests/`.
- Environment: Python only via `.venv/Scripts/python`. Odoo tests (Git Bash, repo root):
  `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -u afenda_brand --test-enable --test-tags "/afenda_brand" --stop-after-init --http-port 8179`
  Tools tests: `.venv/Scripts/python -m unittest discover afenda/tools/tests`.
- Git: stage explicit paths only, never `git add -A` (another session's rebrand script
  leaves thousands of modified upstream files). Never `git status` on the whole tree;
  use `git status -- afenda docs`. Commit subjects use `[ADD]`, `[FIX]`, `[IMP]`.
  One commit per task. Do not push.
- Verified upstream facts to rely on: `mail.res.company.email_primary_color` is the
  button TEXT color (default #FFFFFF) and `email_secondary_color` is the button FILL
  (default #875A7B). Company `font` Selection keys equal `@font-face` family names
  (`Open_Sans` pattern in `addons/web/static/fonts/fonts.scss:82-104`) and are emitted
  raw by `web.styles_company_report` (`addons/web/views/report_templates.xml:921-1017`).
  wkhtmltopdf ignores variable-font axes. `ir.ui.menu.web_icon_data` is computed from
  the icon file when `web_icon` is written. The `res_config_edition` OWL template is
  unprefixed upstream.

---

### Task 1: Design tokens in SCSS

Files: `ADDON/static/src/scss/primary_variables.scss` (rewrite),
`ADDON/static/src/scss/primary_variables.dark.scss` (new), `ADDON/static/src/scss/backend.scss`,
`ADDON/brand.py`, `ADDON/__manifest__.py`, `ADDON/tests/test_branding.py`.

1. Rewrite `primary_variables.scss`. Every declaration ends with `!default` (the file is
   prepended into `web._assets_primary_variables`, so first wins; `!default` lets the
   dark file override). Keep the existing 10 overrides and add:

   | Variable | Value |
   |---|---|
   | `$o-success` | `#15803D` |
   | `$o-warning` | `#C2410C` |
   | `$o-danger` | `#B91C1C` |
   | `$o-info` | `#4B5563` |
   | `$o-theme-text-colors` | `("success": #15803D, "info": #4B5563, "warning": #C2410C, "danger": #B91C1C)` (match upstream map shape in `addons/web/static/src/scss/primary_variables.scss`) |
   | `$o-main-text-color` | `#0F172A` |
   | `$border-color` | `#E5E7EB` (Bootstrap variable; upstream sets it in `bootstrap_overridden.scss:97`; leave `$o-gray-*` untouched) |
   | `$o-main-favorite-color` | `#A16207` |
   | `$o-main-code-color` | `#4B5563` |
   | `$o-enterprise-action-color` | `#1E3A8A` |
   | `$o-headings-font-family` | same list as `$o-font-family-sans-serif` |
   | `$o-border-radius` / `$o-border-radius-sm` / `$o-border-radius-lg` | `o-to-rem(3px)` / `o-to-rem(2px)` / `o-to-rem(4px)` (check how upstream declares them and match the form) |
   | `$o-navbar-background` | `#0F172A` |
   | `$o-navbar-border-bottom` | `1px solid #0B1120` |
   | `$o-navbar-badge-bg` | `#C2410C` |
   | `$o-default-report-font` | `"Source Sans 3"` |
   | `$o-colors` | `(#9CA3AF, #A33A3A, #B5651D, #A16207, #3B6EA8, #7C4F7F, #9A6B4F, #2F8F8A, #3448A8, #A8447A, #4C8A56, #6B5FA8)` in that order |
   | `$o-color-palettes` | redefine the whole map from `addons/html_editor/static/src/scss/html_editor.variables.scss:119-149` with `base-1` colors `o-color-1: #1E3A8A, o-color-2: #E5E7EB, o-color-3: #F7F7F5, o-color-4: #FFFFFF, o-color-5: #0F172A`; keep `base-2` exactly as upstream; keep any other keys the map has upstream |

   Wrap both font stacks with the upstream helper so non-Latin fallback returns:
   `$o-font-family-sans-serif: o-add-unicode-support-font(("Source Sans 3", -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif)) !default;` and the same
   for the monospace stack. `o-add-unicode-support-font` is defined in
   `addons/web/static/src/scss/utils.scss:211`, which precedes the primary-variables
   include in every bundle. Leave `$o-spacer`, `$o-statusbar-height`, `$o-font-size-base`
   unchanged.

2. New `primary_variables.dark.scss`, all `!default`: `$o-webclient-background-color:
   #0B1120`, `$o-view-background-color: #111827`, `$o-main-text-color: #E5E7EB`,
   `$o-brand-primary: #3B5BDB`, `$o-main-link-color: #A5B4FC`, `$border-color: #1F2937`,
   `$o-navbar-background: #0B1120`, `$o-navbar-border-bottom: 1px solid #1F2937`.
   Register in the manifest: `"web.assets_web_dark": [("before", "afenda_brand/static/src/scss/primary_variables.scss", "afenda_brand/static/src/scss/primary_variables.dark.scss")]`.
   Verify that `web.assets_web_dark` exists in `addons/web/__manifest__.py`; if the
   bundle name differs in 19.0, use the real one and note it in the report.

3. `ADDON/brand.py`: add `"on_primary": "#FFFFFF"`, `"favorite": "#A16207"`, and
   `"tags": [the 12 hexes above]`. Update the header comment listing keys.

4. `backend.scss`: after the change, if the compiled backend CSS no longer contains
   `#71639e`, delete the `.o-we-tablepicker` rule and its comment. If it still does,
   keep the rule and say so in the report.

5. Tests in `ADDON/tests/test_branding.py`, method
   `test_backend_theme_uses_brand_colors_and_fonts`: assert the compiled `web.assets_web`
   CSS contains `#15803d`, `#c2410c`, `#b91c1c`, `#0f172a`, `#e5e7eb`; and does NOT
   contain `#28a745`, `#ffac00`, `#dc3545`, `#f3cc00`, `#d2317b`, `#f0cda8`, `#71639e`
   (adjust or drop the existing table-picker exception loop accordingly); and that the
   string `unicode support noto` appears in the CSS (lowercased). Keep existing assertions.

6. Run the `/afenda_brand` tests. Commit: `[IMP] afenda_brand: semantic color tokens, ink navbar, tag palette, dark variables`.

Risks to check in the browser if possible (`.venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda`, port 8169): navbar entry contrast on ink; `$o-list-group-active-bg` derived from `$o-info` (Settings list selection still visible); required-field input borders.

---

### Task 2: Hard-coded hex surfaces and the email color fix

Files: `ADDON/views/webclient_templates.xml`, `ADDON/controllers/__init__.py` (new),
`ADDON/controllers/webmanifest.py` (new), `ADDON/__init__.py`, `ADDON/hooks.py`,
`ADDON/models/res_company.py`, `ADDON/tests/test_branding.py`.

1. In `webclient_templates.xml` add two inherits:
   - `web.webclient_bootstrap`: `<xpath expr="//meta[@name='theme-color']" position="attributes"><attribute name="content">#1E3A8A</attribute></xpath>`.
   - `web.webclient_offline`: `<xpath expr="//style" position="after">` a second
     `<style>` with: `body{background:#F7F7F5;color:#0F172A;font-family:"Source Sans 3",-apple-system,"Segoe UI",Roboto,Arial,sans-serif}` and a rule that makes the
     page's button Ledger Blue with a 3px radius (read the upstream template at
     `addons/web/views/webclient_templates.xml` around line 313 for the exact button
     selector). Later `<style>` wins; do not copy the template.

2. New controller `ADDON/controllers/webmanifest.py`: subclass
   `odoo.addons.web.controllers.webmanifest.WebManifest`, re-declare the route
   `/web/manifest.scoped_app_manifest` with the same route options as upstream
   (`addons/web/controllers/webmanifest.py` around line 144), call `super()`, decode
   the JSON body, set `theme_color` and `background_color` to `BRAND["primary"]` and
   `BRAND["paper"]`, return `request.make_json_response(...)` with the same headers.
   Pattern reference: `afenda/oca/web/web_pwa_customize/controllers/webmanifest.py:45-70`.
   Import the controllers package from `ADDON/__init__.py`.

3. Email color fix. `hooks.py` currently writes `email_primary_color` = primary and
   `email_secondary_color` = ink, which is inverted (primary is the button TEXT,
   secondary is the button FILL). Change to `email_secondary_color` = `BRAND["primary"]`
   and `email_primary_color` = `BRAND["on_primary"]`. In `models/res_company.py` redeclare
   `email_primary_color = fields.Char(default=...)` and `email_secondary_color =
   fields.Char(default=...)` with the same values so newly created companies inherit
   (same pattern the file already uses for `logo`).

4. Tests:
   - `test_company_defaults`: replace the inverted assertion with
     `email_secondary_color.upper() == BRAND["primary"]` and
     `email_primary_color.upper() == "#FFFFFF"`; assert the same on the newly created
     company already exercised by that test.
   - New `test_theme_meta_and_offline`: `/app` HTML contains
     `<meta name="theme-color" content="#1E3A8A"/>` (match the exact serialization Odoo
     emits); `/web/offline` HTML contains `#1E3A8A` and not `#714B67`.
   - New `test_scoped_app_manifest`: `self.url_open("/web/manifest.scoped_app_manifest?app_id=mail&path=/app/discuss")` returns JSON with `theme_color` equal to `BRAND["primary"]` (case-insensitive). If the route needs a different query shape in 19.0, read the upstream controller and adapt.

5. Run the `/afenda_brand` tests. Commit: `[FIX] afenda_brand: email CTA colors, theme-color meta, offline page, scoped-app manifest`.

---

### Task 3: Login page and PWA icons

Files: `ADDON/views/webclient_templates.xml`, `ADDON/controllers/home.py` (new),
`ADDON/controllers/webmanifest.py`, `ADDON/static/src/scss/login.scss` (new),
`ADDON/__manifest__.py`, `ADDON/tests/test_branding.py`.

1. Login layout (extend the existing `afenda_brand.login_layout` inherit of `web.login_layout`):
   - set the body class: `<xpath expr="//t[@t-set='body_classname']" position="attributes"><attribute name="t-value">'o_afenda_login'</attribute></xpath>` (verify the upstream `t-set` name at `addons/web/views/webclient_templates.xml:110-135`);
   - widen the card: xpath on the `div` with class `o_database_list`, `position="attributes"`, `style` → `max-width: 360px;`;
   - after the logo `img` (alt "Logo" upstream; verify) add `<p t-if="afenda_tagline" class="o_afenda_tagline mt-2 mb-0" t-out="afenda_tagline"/>`.
2. New `ADDON/controllers/home.py`: `class Home(odoo.addons.web.controllers.home.Home)`,
   override `web_login(self, *args, **kw)`: `response = super().web_login(*args, **kw)`;
   if the response has a `qcontext` attribute, set `response.qcontext["afenda_tagline"] = BRAND["tagline"]`; return it. Register in `controllers/__init__.py`.
3. New `login.scss` in `web.assets_frontend`:
   `.o_afenda_login { background: #F7F7F5; }`
   `.o_afenda_login .o_database_list { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 3px; }`
   `.o_afenda_tagline { font-family: "Source Serif 4", Georgia, serif; font-weight: 600; color: #4B5563; font-size: .95rem; }`
   The wordmark stays inside the company logo lockup; "Log in" is already `btn-primary`.
4. PWA maskable icons: in `ADDON/controllers/webmanifest.py` also subclass the OCA
   controller `odoo.addons.web_pwa_customize.controllers.webmanifest.WebManifest` (read
   it to find the method that builds the icon list) and set `"purpose": "any maskable"`
   on every icon it returns. The tile art keeps the mark inside the 80% safe zone already.
5. Tests: `test_login_page_is_branded` additionally asserts `BRAND["tagline"]` and
   `o_afenda_login` in the HTML. New `test_frontend_css_has_login_surface`: find the
   `web.assets_frontend` CSS `<link>` in `/web/login`, fetch it, assert `.o_afenda_login`
   and `#f7f7f5` present. `test_pwa_manifest_is_branded` asserts every icon's `purpose`
   contains `maskable`.
6. Run the `/afenda_brand` tests. Commit: `[IMP] afenda_brand: login surface with tagline, maskable PWA icons`.

Note: the database manager is a static HTML file upstream; it is already covered by
the text rules and `logo2.png`. Do not attempt to restyle it.

---

### Task 4: PDF report defaults and fonts

Files: `ADDON/models/res_company.py`, `ADDON/hooks.py`, `ADDON/static/fonts/` (new static
TTFs), `ADDON/static/src/scss/fonts_report.scss` (new), `ADDON/static/src/scss/report.scss`
(new), `ADDON/__manifest__.py`, `ADDON/tests/test_report.py` (new),
`ADDON/tests/__init__.py`, `ADDON/tests/test_branding.py`.

Decisions: layout `web.external_layout_standard`; company font `Source_Sans_3` added to
the Selection; report colors primary = ink `#0F172A`, secondary = graphite `#4B5563` (a
document has no action, so not Ledger Blue); `report_header` stays empty (the tagline is
a product slogan and does not belong on a customer's invoice).

1. Static font instances (wkhtmltopdf cannot use variable fonts): add to
   `ADDON/static/fonts/` `SourceSans3-Regular.ttf`, `SourceSans3-Semibold.ttf`,
   `SourceSans3-Bold.ttf`, `SourceSans3-It.ttf`, `SourceSerif4-Semibold.ttf`,
   `SourceCodePro-Regular.ttf`. Generate them from the existing variable fonts with
   fontTools (`.venv/Scripts/python -m pip install fonttools` into the venv only;
   `fontTools.varLib.instancer.instantiateVariableFont` with `{"wght": 400}` etc.; Source
   Serif 4 also has an `opsz` axis, pin it to its default). If instancing fails for any
   face, report BLOCKED with the error rather than downloading files.
2. `fonts_report.scss`: `@font-face` rules for family `"Source_Sans_3"` (weights 400,
   600, 700 and italic 400), `"Source Sans 3"` (same faces), `"Source Serif 4"` (600),
   `"Source Code Pro"` (400), all with absolute `url(/afenda_brand/static/fonts/...)`.
3. `report.scss`: scoped to `.o_report_layout_standard` and `.o_company_` layouts (check
   upstream body classes in `addons/web/views/report_templates.xml` around line 502):
   `font-variant-numeric: tabular-nums` on `.o_main_table td.text-end`, `#total td`,
   `.o_total`, `.o_price_total`, `td.o_list_number`; `h2 { font-family: "Source Serif 4",
   Georgia, serif; font-weight: 600; }`; table rules `border-color: #E5E7EB`.
4. Manifest: `"web.report_assets_common": ["afenda_brand/static/src/scss/fonts_report.scss", "afenda_brand/static/src/scss/report.scss"]`.
5. `models/res_company.py`: `font = fields.Selection(selection_add=[("Source_Sans_3", "Source Sans 3")], default="Source_Sans_3", ondelete={"Source_Sans_3": "set default"})`;
   `external_report_layout_id` default = `lambda self: self.env.ref("web.external_layout_standard", raise_if_not_found=False)`;
   `primary_color` default `BRAND["ink"]`; `secondary_color` default `BRAND["graphite"]`.
   These are `base`/`web` fields; check exact field definitions in
   `odoo/addons/base/models/res_company.py:88-94`.
6. `hooks.py`: for existing companies write `font`, `external_report_layout_id`,
   `primary_color`, `secondary_color` only where the current value is still the upstream
   default (`Lato`, empty, empty, empty) so admin choices survive `-u`. Also change the
   existing `primary_color`/`secondary_color` entries (currently primary and ink) to ink
   and graphite. Writing these fields regenerates the `web.asset_styles_company_report`
   attachment.
7. Tests: new `test_report.py::TestReport(HttpCase)`: `base.main_company.font ==
   "Source_Sans_3"`; `external_report_layout_id == env.ref("web.external_layout_standard")`;
   the report CSS bundle (`env["ir.qweb"]._get_asset_link_urls("web.report_assets_common")`
   or the equivalent 19.0 API; read `addons/web/models/ir_qweb.py`) fetched via
   `url_open` contains `Source_Sans_3`, `/afenda_brand/static/fonts/SourceSans3-Regular.ttf`,
   `tabular-nums`; the attachment with url `/web/static/asset_styles_company_report.scss`
   (see `addons/web/models/models.py` around line 2233 for how it is named) decodes to
   text containing `Source_Sans_3` and `#0F172A`. `test_company_defaults`: a newly created
   company gets the font, layout and colors. Optional PDF smoke: skip with
   `self.skipTest` when `ir.actions.report._get_wkhtmltopdf_state()` is not `ok`.
8. Run the `/afenda_brand` tests. Commit: `[IMP] afenda_brand: report layout, fonts and colors for PDF documents`.

---

### Task 5: Remaining Odoo wordmark images

Files: `afenda/tools/brand_images.py`, `afenda/tools/tests/test_brand_images.py`.

Add TARGETS and SIZES entries and the kinds to render them. Reuse `lockup_png()`,
`tile_png()`, `_mark()`; parameterise rather than duplicate.

| Path | Kind | Size | Rendering |
|---|---|---|---|
| `addons/web/static/img/nologo.png` | `lockup_png` | (180, 79) | as `logo.png` |
| `addons/web/static/img/logo_inverse_white_206px.png` | `lockup_white_png` (new) | (627, 206) | lockup with white wordmark and a white mark without tile, transparent background |
| `odoo/addons/base/static/img/logo_white.png` | `lockup_white_png` | (600, 194) | same |
| `odoo/addons/base/static/img/demo_logo_report.png` | `lockup_faint_png` (new) | (621, 196) | `lockup_png` with every alpha value scaled to 12% (a watermark) |
| `addons/web/static/img/default_icon_app.png` | `tile_png` | (180, 180) | existing tile |
| `addons/web/static/img/enterprise_upgrade.jpg` | `blank_jpg` (new) | (1, 1) | white JPEG; the file is unreferenced upstream |

Read each original's pixel size with Pillow before choosing SIZES and use the
original's size where it differs from the table (report the actual values).

Tests (`test_brand_images.py`): extend the size table with the new targets; new
`test_white_lockups_have_no_dark_pixels` (for every opaque pixel, max(R,G,B) > 200);
new `test_faint_watermark_alpha` (max alpha <= 40). Run
`.venv/Scripts/python -m unittest afenda.tools.tests.test_brand_images`, then
`.venv/Scripts/python -m afenda.tools.brand_images` to render, then
`.venv/Scripts/python -m afenda.tools.scan_identity` (must print 0 remaining).

Commit both the tool change and the rendered images, staging each rendered path
explicitly: `[REBRAND] render AFENDA over remaining Odoo wordmark images`.

---

### Task 6: Email layouts and digest

Files: `ADDON/views/mail_templates.xml` (new), `ADDON/__manifest__.py`,
`afenda/addons/afenda_brand_digest/` (new addon: `__init__.py`, `__manifest__.py`,
`views/digest_templates.xml`, `tests/__init__.py`, `tests/test_digest_layout.py`),
`ADDON/tests/test_identity.py`, `ADDON/tests/test_branding.py`.

1. `mail_templates.xml` inherits `mail.mail_notification_layout` and
   `mail.mail_notification_light` (`addons/mail/data/mail_templates_email_layouts.xml`,
   lines 4 and 96) with attribute-only xpaths, no template copies:
   - `//body` style: `font-family:'Source Sans 3','Segoe UI',Helvetica,Arial,sans-serif; color:#0F172A;` (no `@font-face` in email; the stack is a fallback chain);
   - the outer frame table with `background-color: #F1F1F1` (light layout) → `#F7F7F5`; the inner 590px table gets `border:1px solid #E5E7EB`;
   - the footer cell with `font-size:11px` gets `border-top:1px solid #E5E7EB; padding-top:12px; color:#4B5563;`;
   - the "Powered by" anchor (styled with `email_secondary_color`, around lines 87 and 161) is replaced by `<img t-att-src="company.get_base_url() + '/afenda_brand/static/img/logo_email.png'" height="16" alt="AFENDA xForge"/>` followed by muted text. Check whether OCA `mail_debranding` already strips the anchor; if the anchor is gone at render time, place the image where the footer company links end instead.
   - Leave the CTA cell alone: it reads `email_secondary_color`, which Task 2 set to Ledger Blue, and its `border-radius: 3px` already matches.
2. Digest: new sibling addon `afenda_brand_digest` (`auto_install: True`, depends
   `["afenda_brand", "digest"]`, license LGPL-3, category Hidden/Tools) with one view that
   appends to `digest.digest_mail_layout` a `<style>` after the upstream one: `a { color: #1E3A8A !important; } body { color: #0F172A !important; }`. Do not replace the upstream style block.
3. Tests:
   - `test_identity.py::test_notification_email_body`: also assert `#1E3A8A` in
     `body_html`, and `#875A7B`, `#F1F1F1`, `Verdana` absent, `logo_email.png` present.
   - new `test_branding.py::test_email_cta_contrast`: render `mail.mail_notification_layout` through `env["ir.qweb"]._render` with a minimal context including `button_access={"url": "/x", "title": "View"}`, `has_button_access=True`, `company=base.main_company`, and parse the CTA cell's `background:` and the anchor's `color:`; assert `#1E3A8A` and `#FFFFFF`.
   - `afenda_brand_digest/tests/test_digest_layout.py` (`TransactionCase`): render `digest.digest_mail_layout` for `digest.digest_digest_default` (read `addons/digest/models/digest.py` for the render entry point, or render the template directly) and assert `#1E3A8A` present and the last `<style>` contains `a { color: #1E3A8A`.
4. Run the `/afenda_brand` tests and `--test-tags /afenda_brand_digest` (install the new addon with `-i afenda_brand_digest` once). Commit: `[IMP] afenda: email notification and digest layouts in AFENDA colors`.

---

### Task 7: App icons for all 108 modules

Files: `afenda/tools/app_icons.py` (new), `afenda/tools/brand_images.py`,
`afenda/tools/requirements.txt` (new), `afenda/tools/tests/test_app_icons.py` (new),
`ADDON/hooks.py`, `ADDON/tests/test_branding.py`.

1. Generator `afenda/tools/app_icons.py`, called from `brand_images.render_all()` after
   the TARGETS loop:
   - discover `sorted(root.glob("addons/*/static/description/icon.png"))`; for each
     module render a PNG at the file's original pixel size; render an SVG only where
     `icon.svg` already exists next to it (`viewBox="0 0 50 50"`); never create files
     upstream does not ship;
   - tile: rounded rectangle, radius 20% of the side, fill `#1E3A8A`; glyph white,
     occupying about 52% of the tile; modules without a mapping get the AFENDA mark
     (`brand_images.MARK_SVG_INNER` / `_mark`) in white on a graphite `#4B5563` tile so
     technical modules recede behind apps;
   - glyphs from the FontAwesome 4 TTF already in the tree,
     `addons/web/static/src/libs/fontawesome/fonts/fontawesome-webfont.ttf`: PNG via
     Pillow `ImageFont.truetype` + `draw.text` with supersampling like `tile_png`; SVG
     via `fontTools.ttLib.TTFont` + `fontTools.pens.svgPathPen.SVGPathPen` emitting one
     `<path>` scaled into the tile;
   - `APP_GLYPHS: dict[str, str]` module → FontAwesome codepoint hex, at least these:
     account f0d6, contacts f2b9, crm f0f2, sale f291, purchase f0d1, stock f1b2,
     mrp f085, project f0ae, project_todo f046, hr f0c0, hr_holidays f073,
     hr_attendance f017, hr_expense f09d, hr_recruitment f0b1, hr_timesheet f1da,
     hr_skills f0a3, calendar f133, mail f075, board f0e4, website f0ac,
     website_sale f07a, website_blog f040, website_slides f19d, website_forum f086,
     point_of_sale f0d6, event f145, im_livechat f27a, lunch f0f5, fleet f1b9,
     maintenance f0ad, mass_mailing f0e0, mass_mailing_sms f10b, sms f10b, survey f0cb,
     repair f1b3, gamification f091, data_recycle f1b8, payment f09d,
     spreadsheet_dashboard f0ce, utm f0e8, base f013, web f009. Every codepoint must
     exist in the font's cmap (test enforces it).
   - `afenda/tools/requirements.txt`: `pillow`, `fonttools`. Install fonttools into the venv only.
2. `ADDON/hooks.py`: after the existing steps, for every `ir.ui.menu` with no parent and a
   `web_icon`, write `web_icon` back to itself so `web_icon_data` recomputes from the new
   file on existing databases.
3. Tests:
   - `afenda/tools/tests/test_app_icons.py`: build a temp root with fixture
     `addons/x/static/description/icon.png` (100x100) and `icon.svg`, run the generator on
     it, assert the PNG is 100x100 with a transparent corner pixel and a `#1E3A8A` or
     `#4B5563` mid-edge pixel, the SVG starts with `<svg` and contains `#1E3A8A` and
     neither `#985184` nor `#1AD3BB`; assert every `APP_GLYPHS` codepoint is in the FA
     cmap; assert a module without a mapping gets a graphite tile.
   - `ADDON/tests/test_branding.py::test_app_icons_are_branded`: for root menus with
     `web_icon`, decode `web_icon_data` with Pillow and probe a mid-edge pixel for
     `#1E3A8A` or `#4B5563`; `self.url_open("/mail/static/description/icon.svg").text`
     contains no `#985184`.
4. Run tools tests, then `.venv/Scripts/python -m afenda.tools.brand_images` to render
   all icons, then `scan_identity` (0), then the `/afenda_brand` tests (the hook runs on
   `-u`). Commit in two commits: `[ADD] afenda/tools: app icon generator` (tools, tests,
   hook) and `[REBRAND] render AFENDA app icons` (the rendered `icon.png`/`icon.svg`
   files, staged with an explicit glob `addons/*/static/description/icon.png` and
   `addons/*/static/description/icon.svg`).

---

### Task 8: Last-resort surfaces and housekeeping

Files: `ADDON/static/img/empty_state.svg` (new), `ADDON/static/src/scss/backend.scss`,
`ADDON/static/src/js/effects.js` (new), `ADDON/static/src/js/user_menu.js` (new),
`ADDON/static/src/xml/error_dialogs.xml` (new), `ADDON/models/ir_http.py` (new),
`ADDON/models/__init__.py`, `ADDON/data/config_data.xml` (delete), `ADDON/__manifest__.py`,
`ADDON/tests/test_branding.py`, `afenda/README.md`.

1. Empty states: draw `empty_state.svg` as one quiet ink-line illustration (a ledger page
   outline in `#4B5563` stroke with the double total rule in `#1E3A8A`, 120x80 viewBox,
   no text). In `backend.scss` override the three upstream classes from
   `addons/web/static/src/views/view.scss` (`o_view_nocontent_smiling_face`,
   `o_view_nocontent_neutral_face`, `o_view_nocontent_empty_folder`; check the exact
   selectors and whether they use `:before` with `background-image`) to use
   `url(/afenda_brand/static/img/empty_state.svg)`.
2. Rainbow man: `effects.js` registers `rainbow_man` in `registry.category("effects")`
   with `{ force: true }` as a function that shows a success notification with the
   message and no image (read `addons/web/static/src/core/effects/effect_service.js` for
   the effect signature). "Quiet by default."
3. Error dialog: `error_dialogs.xml` OWL-inherits `web.ErrorDialog` and changes the
   title from "Oops!" to "Something went wrong" (read
   `addons/web/static/src/core/errors/error_dialogs.xml` for the attribute to target).
4. Help menu item: `models/ir_http.py` overrides `session_info()` to add
   `afenda_docs_url = BRAND["docs_path"]`; `user_menu.js` registers `afenda_help` in
   `registry.category("user_menuitems")` at sequence 20, description "Help", opening
   `session.afenda_docs_url` in a new tab (pattern in
   `addons/web/static/src/webclient/user_menu/user_menu_items.js`).
5. Housekeeping: delete `data/config_data.xml` and its manifest entry (`hooks.py` is the
   single writer of `web.web_app_name`); add `portal_debranding` to `depends` (the
   module exists under `afenda/oca/server-brand`); register the new JS/XML files in
   `web.assets_backend`.
6. README `afenda/README.md`: update the "What afenda_brand changes" table for navbar
   ink, semantic colors, login tagline, report defaults, email CTA, app icons, digest
   addon; note `fonts.odoocdn.com` as the one remaining external request.
7. Tests in `test_branding.py`: CSS contains `/afenda_brand/static/img/empty_state.svg`
   and the override rule appears after the last upstream `smiling_face.svg` rule
   (`rfind` ordering as the existing table-picker assertion does); the `web.assets_web`
   JS contains `afenda_help` and `"rainbow_man"`; `Oops!` absent from the JS bundle;
   `/app` HTML `session_info` contains `"afenda_docs_url"`; `portal_debranding` module
   state is `installed`; `test_config_parameters` still passes.
8. Run the `/afenda_brand` tests. Commit: `[IMP] afenda_brand: quiet empty states, effects and errors, help item, housekeeping`.

---

### Task 9: Portal title attribute rule (rebrand tooling)

Files: `afenda/tools/rules.py`, `afenda/tools/tests/test_rebrand.py`,
`afenda/tools/tests/corpus/golden.txt`, `ADDON/tests/test_identity.py`.

1. Add a rule before `product` in `RULES`: name `title_attr`, pattern `title="odoo"`,
   replacement `title="{product}"` (product from `load_brand()`), suffixes `.xml`, `.html`.
2. `test_rebrand.py`: a case proving `title="odoo"` becomes `title="AFENDA xForge"` and
   that `title="OdooEditor"` (or similar identifier) is untouched.
3. Corpus workflow, in this order: `.venv/Scripts/python -m afenda.tools.corpus diff`
   (review the drift; only the `title="odoo"` line should change), then
   `.venv/Scripts/python -m afenda.tools.corpus golden`, then
   `.venv/Scripts/python -m afenda.tools.rebrand` (dry run; report the totals), then
   `--apply`, then `.venv/Scripts/python -m afenda.tools.scan_identity` (0).
4. `test_identity.py`: extend `TELLS` with `title="odoo"`; add `/my` to the public pages
   test with an authenticated session (`self.authenticate("admin", "admin")`).
5. Run tools tests and the `/afenda_brand` tests. Commit tooling and the applied file(s)
   together, explicit paths: `[REBRAND] portal title attribute`.
