# nexuscanon.com landing, invite-only access, and the DigitalOcean DNS zone: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the approved minimal landing page on `nexuscanon.com` and `www.`, make the ERP
invitation-only with a tenant-configured `/request-access`, and define the DigitalOcean DNS
zone as code.

**Architecture:**
- The page is static files in `deploy/site/`, served by the existing nginx container.
  `PUBLIC_URL` is filled in at nginx start.
- The access changes are an `_inherit`-free controller, data, and a version-bump migration in
  `afenda_runtime`.
- DNS is a record table plus a `doctl` script, applied later by the operator.

**Tech Stack:** Odoo 19.0 (`afenda_runtime`), nginx 1.27-alpine, POSIX sh, Python 3.11
`unittest`, fontTools (already in `.venv`), `doctl`.

**Spec:** `docs/superpowers/specs/2026-09-24-nexuscanon-landing-design.md`

**Approved page source:** `C:/Users/dlbja/AppData/Local/Temp/claude/C--JackProject-afenda-xforge-v9/25e80aba-8c94-4b65-a385-33b336a5e49c/scratchpad/landing-proposal/index.html`.
Take it verbatim except for the changes listed in Task 2.

## Global Constraints

- Read `CLAUDE.md` § Execution discipline and `.claude/odoo-agent-rules.md` first. Both are
  binding.
- Zero hand edits to root `odoo/` or `addons/`. `.venv/Scripts/python` only.
- Commit with `git commit --only -F msgfile -- <paths>`, one shell call. Never `git add -A`.
  Dotfiles need `git add -f`. Subjects use `[ADD]`/`[IMP]`/`[FIX]`. Messages end with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Read the printed test count, never the exit code. Run the narrowest test per edit. Do not
  rerun a passing gate.
- The page: no JavaScript, and no URL to any host except via the `__PUBLIC_URL__` placeholder.
  Fonts are self-hosted woff2.
- Headline text is exactly `The truth of your business, kept.`; the button reads
  `Request access`; the link reads `Sign in`.
- `auth_signup.invitation_scope` becomes `b2b`. Never set `iap_vies.endpoint`.
- Other sessions share this checkout. Touch only the files listed in your task.

---

### Task 1: Invitation-only access and `/request-access` in `afenda_runtime`

**Files:**
- Modify: `afenda/addons/afenda_runtime/__manifest__.py` (version → `19.0.1.1.0`; add the new
  data and views files)
- Modify: `afenda/addons/afenda_runtime/data/ir_config_parameter.xml` (add `b2b` inside the
  existing `noupdate="1"` block)
- Create: `afenda/addons/afenda_runtime/migrations/19.0.1.1.0/post-migrate.py`
- Create: `afenda/addons/afenda_runtime/controllers/__init__.py`, `controllers/request_access.py`
- Modify: `afenda/addons/afenda_runtime/__init__.py` (import `controllers`)
- Create: `afenda/addons/afenda_runtime/views/request_access_templates.xml`
- Test: `afenda/addons/afenda_runtime/tests/test_access.py`, registered in `tests/__init__.py`

**Interfaces:**
- Produces: `GET /request-access`, `auth='public'`, `type='http'`, `sitemap=False`.
  - **303** to `mailto:<company.email>?subject=Access%20request%20%E2%80%94%20AFENDA%20xForge`
    when `odoo.tools.email_normalize(company.email)` is truthy;
  - otherwise **200** with a page containing `Access to AFENDA xForge is by invitation.`
- Produces: `auth_signup.invitation_scope = 'b2b'` on fresh install (data) and on upgrade from
  `< 19.0.1.1.0` (migration).

- [ ] **Step 1: Ground the APIs.** Name the `path:line` for each of these before coding:
  - how auth_signup gates `/web/signup` under `b2b` (`addons/auth_signup/controllers/main.py`,
    the `signup_enabled` / `NotFound` path);
  - `request.redirect(..., local=False)` in `odoo/http.py`, including whether it accepts a
    `mailto:` scheme. If it rejects it, use `werkzeug.utils.redirect(url, 303)`;
  - which layout template an auth='public' page without `website` should `t-call`. Check how
    `afenda/addons/afenda_api_docs/controllers/landing.py` renders, and reuse that pattern,
    including its `no_footer` note;
  - `odoo.tools.email_normalize`.
- [ ] **Step 2: Write the failing tests** in `tests/test_access.py`, as an `HttpCase`
  subclass (an Odoo `BaseCase`, or it is dropped silently):
  ```python
  from odoo.tests import HttpCase, tagged

  @tagged("post_install", "-at_install")
  class TestInviteOnly(HttpCase):
      def test_signup_is_closed(self):
          self.assertEqual(self.env["ir.config_parameter"].sudo().get_param("auth_signup.invitation_scope"), "b2b")
          self.assertEqual(self.url_open("/web/signup").status_code, 404)

      def test_request_access_mails_the_company(self):
          self.env.company.email = "hello@example.com"
          r = self.url_open("/request-access", allow_redirects=False)
          self.assertEqual(r.status_code, 303)
          self.assertTrue(r.headers["Location"].startswith("mailto:hello@example.com?subject="))

      def test_request_access_without_email_explains(self):
          self.env.company.email = False
          r = self.url_open("/request-access", allow_redirects=False)
          self.assertEqual(r.status_code, 200)
          self.assertIn("Access to AFENDA xForge is by invitation.", r.text)

      def test_request_access_rejects_a_malformed_email(self):
          self.env.company.email = "not an email\r\nBcc: x@y.z"
          r = self.url_open("/request-access", allow_redirects=False)
          self.assertEqual(r.status_code, 200)
  ```
  If Step 1 shows that `/web/signup` under `b2b` answers something other than 404 (for
  example a redirect), assert what the source says and cite it in a comment.
- [ ] **Step 3: Run it and watch it fail.** Use `-u afenda_runtime --test-tags
  "/afenda_runtime:TestInviteOnly"`, with the MSYS prefix and `--http-port 8179`. Expect the
  failures and read the count.
- [ ] **Step 4: Implement.**
  - The data line:
    `<function model="ir.config_parameter" name="set_param" eval="('auth_signup.invitation_scope', 'b2b')"/>`
  - The migration:
    ```python
    def migrate(cr, version):
        # Fresh installs get this from data; an existing database gets it once here.
        cr.execute("UPDATE ir_config_parameter SET value = 'b2b' WHERE key = 'auth_signup.invitation_scope'")
    ```
  - The controller, with the template rendered through the pattern found in Step 1:
    ```python
    from urllib.parse import quote
    import werkzeug.utils
    from odoo import http
    from odoo.http import request
    from odoo.tools import email_normalize

    SUBJECT = quote("Access request — AFENDA xForge")

    class RequestAccess(http.Controller):
        @http.route("/request-access", type="http", auth="public", methods=["GET"], sitemap=False)
        def request_access(self):
            email = email_normalize(request.env.company.sudo().email or "")
            if email:
                return werkzeug.utils.redirect(f"mailto:{email}?subject={SUBJECT}", 303)
            return request.render("afenda_runtime.request_access_by_invitation")
    ```
  - The page says `Access to AFENDA xForge is by invitation.` plus one sentence: `Ask your
    administrator for an invitation.`
- [ ] **Step 5: Run the class and read the count**: 4 tests, 0 failed. Then run the full
  `/afenda_runtime` tag once, expecting 10 tests: 6 existing and 4 new.
- [ ] **Step 6: Commit.**
  `[IMP] afenda_runtime: invitation-only access and a tenant-configured /request-access`

### Task 2: The page, nginx, redeploy upgrades, and the DNS zone, all in `deploy/`

**Files:**
- Create: `deploy/site/index.html`, `deploy/site/lockup.svg`, `deploy/site/lockup-dark.svg`,
  `deploy/site/fonts/SourceSerif4-Semibold.woff2`, `deploy/site/fonts/SourceSans3.woff2`
- Create: `deploy/nginx/40-afenda-site.sh`
- Modify: `deploy/nginx/afenda.conf`, `deploy/nginx/afenda.tls.conf`, `deploy/compose.yaml`,
  `deploy/compose.tls.yaml` (only if a mount or port must change there), `deploy/init.sh`
- Create: `deploy/dns/nexuscanon.com.records`, `deploy/dns/apply-do-dns.sh`
- Modify: `deploy/README.md`
- Test: `afenda/tools/tests/test_deploy_static.py`, plus new cases in the same file

**Interfaces:**
- Consumes: `GET <PUBLIC_URL>/request-access` from Task 1 (a link only).
- Produces: nginx serves the site on container port 81, published on host `:8081` locally,
  and on the bare domain plus `www` on 443 in TLS.

- [ ] **Step 1: The page.**
  - Copy the approved proposal to `deploy/site/index.html`.
  - Replace both `https://app.nexuscanon.com` occurrences with `__PUBLIC_URL__`.
  - Point the `@font-face` rules at `fonts/*.woff2` with `format("woff2")`.
  - Remove the `Source Code Pro` face if it is present.
- [ ] **Step 2: Lockups.** Byte-copy `addons/web/static/img/odoo_logo.svg` to
  `deploy/site/lockup.svg` and `odoo_logo_dark.svg` to `lockup-dark.svg`.
- [ ] **Step 3: woff2 fonts.** Use the `.venv` fontTools with brotli. If
  `import brotli` fails, stop and report. Do not pip-install into anything but `.venv`, and ask
  first. Subset to Basic Latin plus the dash, ellipsis and quotes:
  ```bash
  .venv/Scripts/python -m fontTools.subset afenda/addons/afenda_brand/static/fonts/SourceSerif4-Semibold.ttf --unicodes="U+0020-007E,U+00A0-00FF,U+2013-2014,U+2018-201D,U+2026" --flavor=woff2 --output-file=deploy/site/fonts/SourceSerif4-Semibold.woff2
  .venv/Scripts/python -m fontTools.subset afenda/addons/afenda_brand/static/fonts/SourceSans3-VF.ttf --unicodes="U+0020-007E,U+00A0-00FF,U+2013-2014,U+2018-201D,U+2026" --flavor=woff2 --output-file=deploy/site/fonts/SourceSans3.woff2
  ```
  Add both commands to `deploy/README.md` under "Regenerating the site fonts".
- [ ] **Step 4: PUBLIC_URL substitution.** The official nginx image runs
  `/docker-entrypoint.d/*.sh` before starting. `40-afenda-site.sh`:
  ```sh
  #!/bin/sh
  set -eu
  : "${PUBLIC_URL:?PUBLIC_URL must be set}"
  rm -rf /usr/share/nginx/site && cp -R /usr/share/nginx/site-src /usr/share/nginx/site
  sed -i "s#__PUBLIC_URL__#${PUBLIC_URL}#g" /usr/share/nginx/site/index.html
  ```
  In the compose file:
  - mount `./site` to `/usr/share/nginx/site-src:ro`;
  - mount the script to `/docker-entrypoint.d/40-afenda-site.sh:ro` with mode 755 (the repo
    file is committed as `100755`);
  - pass `PUBLIC_URL` to nginx from `.env`, defaulting to `http://localhost:8080`;
  - publish `8081:81` in the base file.

  `compose.tls.yaml` already `!override`s the ports, so production exposes only 80 and 443.
- [ ] **Step 5: nginx.**
  - Plain conf: add `server { listen 81; root /usr/share/nginx/site; index index.html; location / { try_files $uri $uri/ =404; } }`.
  - TLS conf:
    - `server_name nexuscanon.com` on 443, with the same root and the same cert paths as `app`
      (one certificate, three names);
    - `www.nexuscanon.com` on 443 answers `return 301 https://nexuscanon.com$request_uri;`;
    - the port-80 server serves the ACME webroot for all three names and redirects everything
      else to https.
  - Add `add_header Cache-Control "public, max-age=300"` for `index.html`, and a year plus
    `immutable` for `/fonts/`.
- [ ] **Step 6: Redeploy upgrades.** In `deploy/init.sh`, when the database is already
  initialised, run `module upgrade $MODULES -c "$RC"` (`odoo/cli/module.py:33,168`) after
  `module install`, so a new module version such as Task 1's `19.0.1.1.0` applies on
  redeploy. Update the header comment.
- [ ] **Step 7: The DNS zone as code.**
  - `deploy/dns/nexuscanon.com.records`: tab-separated `type name data priority ttl`, with
    these exact records (IP placeholder `{{DROPLET_IP}}`):
    ```
    A	@	{{DROPLET_IP}}		3600
    CNAME	www	@		3600
    A	app	{{DROPLET_IP}}		3600
    MX	@	mx.zoho.com.	10	3600
    MX	@	mx2.zoho.com.	20	3600
    MX	@	mx3.zoho.com.	50	3600
    TXT	@	v=spf1 include:zohomail.com ~all		3600
    TXT	@	zoho-verification=zb25766137.zmverify.zoho.com		3600
    TXT	zmail._domainkey	v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCKreElUM6kSzo5FuRJTMh7RwGu3FL5iy0e2cWdeB+3wV11fSQPznrSC+RL9uhqLQFkIeZ7C+XFMwzROc+Ta3jSfFLCgTvE4rdhbCPe8YdWKtSNXSmNDrstz1jeD8AAMLC1tGLP9Tt8EO2knxwX86QHTnw1tcbPplqjpLUT+M6LjQIDAQAB		3600
    TXT	_dmarc	v=DMARC1; p=none;		3600
    CAA	@	0 issue "letsencrypt.org"		3600
    ```
  - `deploy/dns/apply-do-dns.sh <droplet-ip>`:
    - `set -eu`; fail if the IP is empty or not an IPv4 address;
    - create the domain with `doctl compute domain create nexuscanon.com` only if it is
      absent;
    - for each record, skip it if an identical `type`+`name`+`data` already exists
      (`doctl compute domain records list nexuscanon.com --format Type,Name,Data --no-header`),
      otherwise `doctl compute domain records create` with `--record-type`,
      `--record-name`, `--record-data`, `--record-priority` (MX only), `--record-ttl`;
      CAA takes `--record-flags 0 --record-tag issue --record-data letsencrypt.org`;
    - print a summary. **Never delete records.**
  - README: a "Moving DNS to DigitalOcean" section:
    1. run the script;
    2. check each name with `dig @ns1.digitalocean.com`;
    3. the user switches the nameservers in Vercel to `ns1/ns2/ns3.digitalocean.com`;
    4. verify email, and that a made-up subdomain does not resolve.
- [ ] **Step 8: Static tests.** Add to `afenda/tools/tests/test_deploy_static.py`:
  - the page contains no `<script`;
  - every `https?://` in `deploy/site/**` is absent. The only URL form allowed is
    `__PUBLIC_URL__/...`;
  - the exact headline, button and link texts;
  - both lockups are byte-equal to `addons/web/static/img/odoo_logo*.svg`;
  - both woff2 files exist and start with `wOF2`;
  - the records file contains no `*` name and no `send`/`resend` record, and contains all
    three Zoho MX records;
  - `init.sh` calls `module upgrade`;
  - the entry script uses `__PUBLIC_URL__` and requires `PUBLIC_URL`.

  Write them first and watch them fail, then implement, then run only this file and read the
  count.
- [ ] **Step 9: Configuration checks.** Run `docker compose -f deploy/compose.yaml config -q`,
  the same with `compose.proof.yaml`, and with `compose.tls.yaml`. Run `sh -n` on
  `40-afenda-site.sh`, `init.sh` and `apply-do-dns.sh`. Do not build or start anything.
- [ ] **Step 10: Commit.**
  `[ADD] deploy: the nexuscanon.com landing page, redeploy upgrades, and the DNS zone as code`

### Task 3: Local proof (controller, once, after Tasks 1 and 2)

- [ ] Rebuild the image. On the running `afenda-deploy` stack, run `up -d` so init executes
  `module upgrade`. Expected: the `afenda_runtime` migration runs and the scope is `b2b`.
- [ ] `http://localhost:8081/` returns 200:
  - its links resolve to `http://localhost:8080/request-access` and `/web/login`;
  - zero requests off its origin;
  - both lockups and both fonts return 200.
- [ ] `http://localhost:8080/web/signup` returns 404, and the login page has no sign-up link.
- [ ] `/request-access` returns 200 with the invitation page. Then set the company email with
  `odoo-bin shell` and a commit, and `/request-access` returns 303 to `mailto:`.
- [ ] `/web/login` still returns 200, admin can log in, and the proof checks from G0 still
  pass.
- [ ] Final gates, once each: the tools suite, the Odoo suites for the four modules, and
  `scan_identity`. Then a whole-branch review, then ask before pushing.
