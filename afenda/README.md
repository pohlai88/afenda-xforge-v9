# AFENDA xForge layer

Everything AFENDA-specific lives in this folder. The `addons/` and `odoo/`
folders at the repository root are unmodified upstream Odoo 19.0 Community, so
upstream updates merge cleanly. What the product must do, and why it is built
this way, is in [SPEC.md](SPEC.md).

```
afenda/
  addons/afenda_brand/   the AFENDA identity, plus the Odoo S.A. service blocks
  oca/server-brand/      OCA debranding modules (git submodule, branch 19.0)
  oca/web/               OCA web modules: favicon, PWA, no bubbles (git submodule, branch 19.0)
  oca/server-tools/      OCA server tools: module_change_auto_install (git submodule, branch 19.0)
  odoo.conf              local development configuration
SPEC.md                  requirements, architecture, Definition of Done, roadmap
```

## First run (Linux)

Prerequisites: Python 3.10–3.14 (3.12 recommended), PostgreSQL 14+ (16
recommended), and the build libraries for `psycopg2` and `python-ldap`
(Debian/Ubuntu: `libpq-dev libldap2-dev libsasl2-dev`). PDF reports need
[wkhtmltopdf 0.12.6.1 with patched Qt](https://github.com/wkhtmltopdf/packaging/releases).

```bash
git submodule update --init --depth 1
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt rl-renderPM   # rl-renderPM: barcode images on Linux
.venv/bin/python odoo-bin -c afenda/odoo.conf -d afenda -i afenda_brand --stop-after-init
.venv/bin/python odoo-bin -c afenda/odoo.conf -d afenda
```

Then open http://localhost:8169. `odoo.conf` expects PostgreSQL on
127.0.0.1:5444 with a role named `odoo` that has `CREATEDB` (no superuser
needed); override with `--db_port`, `--db_user`, `--db_password` or edit the
file. On Windows use `.venv\Scripts\python` instead of `.venv/bin/python`.

## Tests

The same command CI runs (`.github/workflows/afenda.yml`):

```bash
.venv/bin/pip install ruff && .venv/bin/ruff check afenda/addons
.venv/bin/python odoo-bin -c afenda/odoo.conf -d afenda_test -i afenda_brand \
    --test-tags /afenda_brand --stop-after-init
```

The log must report `0 failed, 0 error(s) of N tests` with N > 0. If an upstream merge adds a new
Odoo S.A. host, `test_upstream_odoo_hosts_are_reviewed` fails on purpose: see
[SPEC.md §5](SPEC.md#5-security-and-the-self-hosted-policy).

## What `afenda_brand` changes

Installing `afenda_brand` pulls in the OCA modules and applies the identity:

| Where a user sees it | What changes |
|---|---|
| Browser tab | "AFENDA xForge" instead of "Odoo", favicon replaced |
| Login page | AFENDA logo, no "Powered by Odoo" link |
| Web client | Ledger Blue primary color, Source Sans 3 and Source Code Pro (self-hosted woff2), paper background (white when printed), tabular figures on money |
| Settings | "AFENDA xForge 19.0" edition block, Enterprise upsells removed (`remove_odoo_enterprise`), odoo.com links removed (`disable_odoo_online`) |
| Emails | "Powered by Odoo" footer removed (`mail_debranding`), white-on-Ledger-Blue buttons |
| Portal | Odoo branding removed (`portal_debranding`) |
| PWA / mobile | App name "AFENDA", theme color Ledger Blue (`web_pwa_customize`) |
| Companies | AFENDA colors and favicon, also for companies created later; default logo is the AFENDA lockup (treated as a placeholder, so it stays out of customer emails until a real logo is uploaded); a company still named "My Company" is renamed "AFENDA" at install |
| Discuss | The system bot is "AFENDA Bot", with no Odoo onboarding chat; the #general welcome post reads "Welcome to AFENDA xForge!" |
| API | `/doc` explorer titled "AFENDA xForge API" in Ledger Blue; JSON-2 errors never include server tracebacks (see "API" below) |
| Odoo S.A. services | IAP, SMS, postal mail, lead enrichment, editor media/AI endpoints point at a closed local port; the VIES cron and "Odoo.com Accounts" login are kept off (re-checked at every start); IAP and SMS apps are not auto-installed unless another app requires them. See SPEC.md §5 |

If you also install the `website` app, add `website_debranding` from
`oca/server-brand` to remove the website footer branding.

Brand values (colors, names) are defined once in `addons/afenda_brand/brand.py`
and mirrored in `static/src/scss/primary_variables.scss`.

## API

Every tenant exposes Odoo 19's external API on its own subdomain; there is no
shared API host. `dbfilter = ^%d$` binds `acme.afenda.app` to the `acme`
database, and an `X-Odoo-Database` header cannot point anywhere else.

- **Keys.** A user creates one under Preferences > Account Security > *New API
  Key* (password confirmation required). Keys act as that user, with that
  user's access rights; ordinary users get at most 90 days, administrators
  may create keys without expiry. Revoke them on the same screen.
- **JSON-2** (preferred): `POST /json/2/<model>/<method>` with a JSON object of
  named arguments (`ids`, `context`, then the method's parameters). The
  response is the bare result.

  ```bash
  curl https://acme.afenda.app/json/2/res.partner/search_read \
    -H "Authorization: bearer $AFENDA_API_KEY" -H "Content-Type: application/json" \
    -d '{"domain": [["is_company", "=", true]], "fields": ["name", "email"], "limit": 10}'
  ```

- **Errors** return `{name, message, arguments, context, debug}` with a status
  of 401 (bad key), 403 (access), 404 (unknown model or record), 422 (user or
  validation error) or 500. `afenda_brand` never sends the server traceback
  (`debug` is empty) and replaces the message of a 500 with "Internal server
  error"; the server log keeps the details. `name` keeps Odoo's exception
  class so existing Odoo client libraries work unchanged.
- **Explorer.** Administrators browse every model, field and method, and try
  calls, at `/doc` ("AFENDA xForge API").
- **XML-RPC and JSON-RPC** (`/xmlrpc/2`, `/jsonrpc`) still work, with an API
  key in place of the password, but are deprecated upstream (removal planned
  for Odoo 22). Build new integrations on JSON-2.
- **Browsers.** The API sends no CORS headers: call it from servers, or from
  pages served by the same tenant.

## Production on a VPS

Follow Odoo's [Deploying Odoo](https://www.odoo.com/documentation/19.0/administration/on_premise/deploy.html)
guide; this section lists only what AFENDA does differently or insists on.
Reference box: Ubuntu 24.04, 4 vCPU, 8 GB RAM, SSD, PostgreSQL 16 on the same host.

**Tenancy.** One PostgreSQL database per customer, routed by subdomain
(`acme.afenda.app` → database `acme`) with `dbfilter = ^%d$`.

### 1. Server configuration (`/etc/afenda/odoo.conf`)

```ini
[options]
addons_path = /opt/afenda/app/addons,/opt/afenda/app/afenda/addons,/opt/afenda/app/afenda/oca/server-brand,/opt/afenda/app/afenda/oca/web,/opt/afenda/app/afenda/oca/server-tools
server_wide_modules = base,rpc,web,module_change_auto_install
data_dir = /var/lib/afenda
logfile = /var/log/afenda/odoo.log
; A long random string. Never leave it unset: the default master password is "admin".
admin_passwd = CHANGE-ME
list_db = False
dbfilter = ^%d$
proxy_mode = True
x_sendfile = True
http_interface = 127.0.0.1
; Workers: (2 x CPU + 1) processes in total, cron included, and about 6
; concurrent users per worker. 4 vCPU -> 8 workers + 1 cron.
workers = 8
max_cron_threads = 1
; Memory limits are virtual memory: keep the 19.0 defaults (2048/2560 MiB).
limit_time_cpu = 60
limit_time_real = 120
limit_time_real_cron = 900
; Per process. PostgreSQL max_connections >= (workers + cron) x 8 + 32 + 10.
db_maxconn = 8
db_maxconn_gevent = 32
publisher_warranty_url = http://127.0.0.1:9/

[module_change_auto_install]
modules_disabled = iap,iap_mail,iap_crm,partner_autocomplete,snailmail,snailmail_account,sms,crm_sms,crm_iap_enrich,crm_iap_mine
```

### 2. systemd (`/etc/systemd/system/afenda.service`)

```ini
[Unit]
Description=AFENDA xForge
After=network-online.target postgresql.service
Requires=postgresql.service

[Service]
User=afenda
Group=afenda
ExecStart=/opt/afenda/.venv/bin/python /opt/afenda/app/odoo-bin -c /etc/afenda/odoo.conf
Restart=on-failure
KillMode=mixed
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

### 3. nginx (TLS via certbot)

```nginx
upstream afenda      { server 127.0.0.1:8069; }
upstream afenda_bus  { server 127.0.0.1:8072; }
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 443 ssl;
    http2 on;
    server_name *.afenda.app;
    # ssl_certificate / ssl_certificate_key: managed by certbot (wildcard via DNS challenge)

    client_max_body_size 128m;          # Odoo's own upload cap
    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;
    proxy_set_header X-Forwarded-Host $http_host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;

    add_header Strict-Transport-Security "max-age=31536000" always;
    # Browsers never fetch fonts from Odoo's CDN (fonts.odoocdn.com).
    add_header Content-Security-Policy "font-src 'self' data:" always;

    location /websocket {
        proxy_pass http://afenda_bus;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
    location / {
        proxy_redirect off;
        proxy_pass http://afenda;
    }
    # x_sendfile: nginx streams attachments and asset bundles itself, so a slow
    # download never holds an Odoo worker.
    location /web/filestore {
        internal;
        alias /var/lib/afenda/filestore;
    }

    gzip on;
    gzip_types text/css text/plain text/xml application/json application/javascript image/svg+xml;
}
```

Rate-limit `/web/login` and `/web/reset_password` with `limit_req`, and give
`/json/`, `/xmlrpc/` and `/jsonrpc` their own `limit_req` zone keyed on the
client address, so one integration cannot starve a tenant's workers.

### 4. Block Odoo S.A. at the network

The application-level blocks in `afenda_brand` are for a clean UX; the network
is the guarantee. Make the server's resolver answer nothing useful for Odoo
S.A. domains, e.g. with dnsmasq as the local resolver:

```
address=/odoo.com/0.0.0.0
address=/odoocdn.com/0.0.0.0
```

Check: `getent hosts iap.odoo.com` returns `0.0.0.0`. An outbound allow-list
proxy (`Environment=HTTPS_PROXY=…` in the unit) is the stricter alternative.

### 5. PostgreSQL

Start from [pgtune](https://pgtune.leopard.in.ua/) for "web application", then
keep `shared_buffers` at 15–20 % of RAM (Odoo needs the rest),
`effective_cache_size` about 50 %, `random_page_cost = 1.1` on SSD, and
`max_connections` as computed in step 1. The application role is not a
superuser. Do not put PgBouncer in transaction mode in front of Odoo: the bus
and cron workers rely on `LISTEN/NOTIFY`.

### 6. Backups and restore drill

- Nightly: `click-odoo-backupdb` (from `pip install click-odoo-contrib` in the
  same venv) dumps the database with its filestore; ship it off the box.
- Hourly: back up `/var/lib/afenda/filestore` with restic or borg.
- Weekly: restore the latest backup to a scratch database, run
  `odoo-bin neutralize -d <copy>` (turns off crons, mail servers and
  webhooks), log in, open an invoice PDF.
- Targets: RPO ≤ 24 h, RTO ≤ 2 h. For minutes of RPO add pgBackRest (WAL archiving).

### 7. Upgrades

1. `git fetch` upstream and merge its `19.0` into this repository;
   `git submodule update --remote` for the OCA branches.
2. Restore production to a staging database, `odoo-bin neutralize`, then
   `click-odoo-update -c /etc/afenda/odoo.conf -d <staging>` (updates only
   modules whose code changed). Run the tests.
3. Same `click-odoo-update` on production during a maintenance window, after a backup.

### 8. Accounting configuration for every tenant

Posted entries are immutable, and corrected only by reversal (SPEC.md §4):

- On every journal, tick **Secure Posted Entries with Hash**. Posting then
  hashes the entry, reset-to-draft is refused and the setting cannot be
  turned off. Side effects: vendor bills are no longer auto-posted, and
  posting asks for a confirmation.
- Close each period with the **hard lock date** (Accounting > Lock Dates). It
  only moves forward.

### 9. Monitoring

`GET /web/health` returns 200 when the server is up. Alert on it, on
`logfile` ERRORs, on disk space for `data_dir` and on backup age.
