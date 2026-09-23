# nexuscanon.com landing page, invite-only access, and the DigitalOcean DNS zone

Date: 2026-09-24. Status: **approved by the user ("Build it") after a live proposal.**

## Goal

`nexuscanon.com` and `www.nexuscanon.com` show one minimal page that says what AFENDA xForge
is and offers two ways in. The ERP at `app.nexuscanon.com` becomes invitation-only. DNS moves
from Vercel to DigitalOcean. Vercel was a test and is dropped.

## The page (approved exactly as proposed)

Four elements, centred on paper, filling the screen:

1. The AFENDA xForge lockup, `addons/web/static/img/odoo_logo.svg`. **Light theme only**, by
   the user's instruction (2026-09-24): no dark mode. The page declares
   `color-scheme: light`, so browsers never auto-darken it.
2. `<h1>`: **The truth of your business, kept.**, in Source Serif 4 Semibold.
3. **Request access**, the only filled button (Ledger Blue), linking to
   `<PUBLIC_URL>/request-access`.
4. **Sign in**, a quiet text link to `<PUBLIC_URL>/web/login`.

Constraints:
- no JavaScript;
- no request outside its own origin;
- self-hosted fonts as woff2;
- WCAG AA contrast;
- no horizontal overflow from 320 px up.

The proposal measured, in light: headline 16.6:1, button 10.4:1, Sign in 7.1:1. The HTML is
2.6 KB.

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

- `deploy/site/` holds the page, the lockup (checked byte-equal to its generated source by a
  test) and the woff2 fonts.
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
| `@` | CAA | `0 issue "letsencrypt.org"` |

Dropped:
- Vercel's apex ALIAS;
- **the wildcard**;
- the `pki.goog` and `sectigo.com` CAA entries;
- Resend (the `send.` MX, the `send.` SPF record, `resend._domainkey`).

The registration stays at Name.com via Vercel, with auto-renew on (expires 2026-12-07). After
the switch, the Membrane Vercel connection is revoked. Vercel projects are not touched.
