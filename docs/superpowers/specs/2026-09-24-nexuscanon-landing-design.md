# nexuscanon.com landing page, invite-only access, and the DigitalOcean DNS zone

Date: 2026-09-24. Status: **approved by the user ("Build it") after a live proposal.**
Revised the same day: the page section below describes the design the user approved after
further proposals and shipped in `71bde977a`. It supersedes the first, light-only version of
this spec (`b1b3bf091`, `b6851e8a5`).

## Goal

`nexuscanon.com` and `www.nexuscanon.com` show one minimal page that says what AFENDA xForge
is and offers two ways in. The ERP at `app.nexuscanon.com` becomes invitation-only. DNS moves
from Vercel to DigitalOcean. Vercel was a test and is dropped.

## The page (as shipped, `71bde977a`)

One screen, black and white, where typography is the only decoration. Ink `#0A0A0A` ground,
paper `#F7F7F5` type.

- **Header:** the AFENDA xForge dark lockup (`addons/web/static/img/odoo_logo_dark.svg`, byte
  copy), in its own colours: the one colour on the page. On the right, **Sign in** (quiet) and
  **Request access** (underlined), linking to `<PUBLIC_URL>/web/login` and
  `<PUBLIC_URL>/request-access`.
- **`<h1>`: The truth of your business, kept.** Set as `The truth` / `of your business,` in
  Source Sans 3 at weight 250, over **kept.** in weight 900 at roughly three times the size.
  Hairline against heavy is the black-and-white contrast.
- **Note**, in small tracked capitals: *Every decision, every change, every consequence.
  Recorded with who, when and why.*
- **Footer:** *AFENDA xForge · nexuscanon.com* and *Hosted in Singapore · Invitation only*.
- **Entrance:** a CSS title sequence. The lines fade up out of a blur in turn; with reduced
  motion everything is simply there.

Constraints:
- no JavaScript, and no inline script or style, so the CSP is plain `default-src 'self'`;
- no request outside its own origin;
- one self-hosted font: the Source Sans 3 variable woff2, keeping its 200–900 axis so both
  weights are real, not synthesized;
- one fixed theme: no `prefers-color-scheme` switching;
- WCAG AA contrast;
- the whole page fits one screen, with no horizontal overflow, from 320 px up.

Measured on the shipped CSS: headline and actions 18.5:1; the muted text (note, footer, Sign
in at rest) 8.0:1, the lowest on the page. One screen with no scrolling from 320×568 to
1920×1080. `afenda/tools/tests/test_deploy_static.py` guards
these constraints.

Rejected on the way, and not to be reintroduced: the light-only page, a star-trail
(Polaris) canvas, a canvas "forge" animation, and a four-scene scrolling page.

## Access is by invitation (in `afenda_runtime`)

- `auth_signup.invitation_scope = b2b` ("on invitation"). Upstream 19.0 sets `b2c` on install
  (`addons/auth_signup/data/ir_config_parameter_data.xml:5`). Fresh databases get `b2b` from
  `afenda_runtime` data. Existing databases get it once, through a version-bump migration.
  Neither path overrides a tenant who later chooses otherwise.
- `GET /request-access`, a public route:
  - if the current company has a valid email (the tenant sets it in **Settings → Companies**),
    redirect to `mailto:<email>?subject=Access request — AFENDA xForge`;
  - otherwise, render a plain "Access to AFENDA xForge is by invitation" page.
  - No new model, and no outgoing-mail dependency.

## Serving

- `deploy/site/` holds `index.html`, `site.css`, the dark lockup (checked byte-equal to its
  generated source by a test) and the woff2 font.
- nginx serves it on the bare domain. `www` redirects permanently to the bare domain. Locally
  it is served on `:8081`, next to the app on `:8080`.
- `PUBLIC_URL` is substituted into the page at nginx start, so no URL is hard-coded.
- One Let's Encrypt certificate covers `app.`, the bare domain and `www.`.
- The deploy `init` also runs `module upgrade` on an existing database, so a new AFENDA module
  version applies on redeploy.

## DigitalOcean DNS zone (applied later, with the user's `doctl`)

| Name | Type | Value |
|---|---|---|
| `@` | A | droplet IP |
| `www` | CNAME | `@` |
| `app` | A | droplet IP |
| `@` | MX 10 / 20 / 50 | `mx.zoho.com` / `mx2.zoho.com` / `mx3.zoho.com` |
| `@` | TXT | `v=spf1 include:zohomail.com ~all` |
| `@` | TXT | `zoho-verification=zb25766137.zmverify.zoho.com` |
| `zmail._domainkey` | TXT | (Zoho DKIM key, copied verbatim from the Vercel inventory) |
| `_dmarc` | TXT | `v=DMARC1; p=none;` |
| `@` | CAA | `0 issue "letsencrypt.org."` (the DigitalOcean API requires the trailing dot on input; `dig` should answer `0 issue "letsencrypt.org"`) |

Dropped:
- Vercel's apex ALIAS;
- **the wildcard**;
- the `pki.goog` and `sectigo.com` CAA entries;
- Resend (the `send.` MX, the `send.` SPF record, `resend._domainkey`).

The registration stays at Name.com via Vercel, with auto-renew on (expires 2026-12-07). After
the switch, the Membrane Vercel connection is revoked. Vercel projects are not touched.
