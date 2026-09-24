# AFENDA xForge: deployable anywhere, zero Odoo S.A. dependency (G0)

## Context

The product (`afenda/deidentify-phase1`, `product_name = 'AFENDA xForge'`) is an Odoo 19.0
Community source fork that has **no deploy path**. There is no Dockerfile, no production
config, and no CI. `afenda/odoo.conf` is dev-only, with `workers=0`, `max_cron_threads=0` and
`list_db=True`. Today's goal is one database for one tenant, built and run with **no call to
anything Odoo S.A. operates**. The build must not use `nightly.odoo.com`. At runtime, neither
the server nor users' browsers may contact `iap.odoo.com`, `fonts.odoocdn.com`,
`services.odoo.com` or the Odoo app store. The deploy is proven locally in Docker first, then
served at `app.nexuscanon.com`. **Zero hand edits to root `odoo/` or `addons/`.**

**Strategy: adapters at the seams.** Every Odoo coupling is replaced in one of three
sanctioned places, and upstream merges keep working:
1. **Configuration**, which needs no code.
2. An **`_inherit` override** in a new AFENDA module. This is the adapter; its default
   behaviour is "service not available", with no network call.
3. A **rebrand rule**, for text inside upstream files. It is re-applied automatically after
   each upstream merge.

**What the research and the review established:**
- **Build our own image from our tree, run it with Docker Compose on a VPS, put nginx in
  front.** Among the proven approaches this is the fastest that fits a repo keeping upstream
  at its root. Doodba and camptocamp would force the layout to be remapped.
- **At least 4 workers.** At 2 or 3, wkhtmltopdf PDF rendering deadlocks (odoo/odoo#199880).
- **nginx is the only proxy with a verified 19.0 websocket configuration.**
- **A backup is `pg_dump` plus the filestore.** Either one alone is incomplete.
- **Every claim from the review agent was checked in source.** Four were spot-verified by
  hand: `odoo/cli/server.py:37-44` refuses a database user named `postgres`;
  `service/db.py:444-456` makes `list_dbs` ownership-scoped only when `dbfilter` is set; the
  dev venv is Python 3.11.9; `rl-renderPM` is pinned for win32 only.

## Rulings

| # | Decision | Evidence | Cost if wrong |
|---|---|---|---|
| R1 | Image base `python:3.11-slim-bookworm`, not 3.12 | The tests run on 3.11.9 (`.venv/pyvenv.cfg`), so the deployed pins are the ones tested. On 3.12, reportlab 4.1 needs `rl-renderPM`, which `requirements.txt` installs only on win32 (`:91`), so barcodes break (`odoo/tools/barcode.py:30`) | Moving to 3.12 later is a separate change, already planned in the platform spec |
| R2 | `db_name=afenda` and **no** `dbfilter` | With `dbfilter` set, a restored database owned by another role disappears (`service/db.py:450-455`). With `db_name` alone, Odoo uses it directly (`:444-448`) | None |
| R3 | Initialise with `odoo-bin db init --password`, then `module install` | `-i` leaves the login as admin/admin (`odoo/cli/db.py:54-87,203-213`) | None |
| R4 | Neutralize partner autocomplete at `_request_partner_autocomplete`, not `_contact_iap` | `_contact_iap` goes through `iap.account.get`, which commits a new row from a separate cursor (`iap_account.py:171-190`). Returning `(False, False)` gives every caller empty results with no toast (`res_partner.py:94-160`) | Low |
| R5 | Remove the CDN fonts with a **rebrand rule**, not an asset `replace` | `fonts.scss` is also bundled by `html_builder` (`__manifest__.py:36`) and removed by path in `mass_mailing` (`:85`), and a copied file would break its `./lato` relative paths | Low. It lowers `BASELINE` to 10826 |
| R6 | Deploy from a tag on `afenda/deidentify-phase1`. `19.0` reconciliation, CI, S3, Redis and the job kernel are deferred | None of them block G0 | None |
| R7 | Proof of independence is structural: run the whole stack with `xforge` on an `internal: true` Docker network (no internet route) | If it installs, logs in, prints PDFs and runs cron with no route out, it depends on nothing outside | None |

## Tasks

Dispatch T1, T2 and T3 **in parallel**. They share no files. T4 and T5 follow in order.

**T0. Commit the CLAUDE.md discipline rules** (inline, already edited).
- Files: `CLAUDE.md` and `.claude/odoo-agent-rules.md` (`git add -f`).
- Commit `[IMP] CLAUDE.md: execution discipline, no trial-and-error, gates once`.

**T1. Rebrand rule that stops the CDN font fetches** (inline or `odoo-backend-dev`). Files: `afenda/tools/rules.py`, `tests/test_rebrand.py`, `tests/corpus/golden.txt`, `scan_identity.py`, `afenda/README.md:90-93`.
- Add this rule:
  ```python
  Rule("noto_cdn_local",
       re.compile(r"url\('https://fonts\.odoocdn\.com/fonts/noto/(NotoSans(?:Arabic|Hebrew|Telugu)?)-#\{\$type\}\.(?:woff2|woff|ttf)'\) format\('(?:woff2|woff|truetype)'\)"),
       r"local('\1-Regular')", suffixes=frozenset({".scss"}))
  ```
  Match the constructor API in `rules.py` exactly.
- Tests: each of the 12 source forms is rewritten, and a second pass changes nothing.
- Order of commands: `corpus diff` (expect exactly the 12 lines at `corpus.txt:33038-33049`) → `corpus golden` → `rebrand` dry run (expect 12 in 1 file) → `rebrand --apply` → `scan_identity`. Set `BASELINE=10826` in the same commit.
- Two commits: `[IMP] afenda/tools: serve report fonts locally, not from the Odoo CDN`, then `[REBRAND] drop fonts.odoocdn.com from the report assets`.

**T2. New module `afenda/addons/afenda_runtime`** (`odoo-backend-dev`, then `odoo-reviewer`).
- `depends`: `afenda_brand`, `iap`, `partner_autocomplete`, `base_import_module`.
- `data/ir_config_parameter.xml` (`noupdate`, `<function model="ir.config_parameter" name="set_param">`) sets each of these to `http://127.0.0.1:9`: `iap.endpoint`, `sms.endpoint`, `snailmail.endpoint`, `html_editor.olg_api_endpoint`, `html_editor.media_library_endpoint`, `iap.partner_autocomplete.endpoint`, `enrich.endpoint`, `reveal.endpoint`. **Never** set `iap_vies.endpoint`; only two values are allowed (`base_vat/models/res_partner.py:263-268`).
- `models/iap_autocomplete_api.py`: `_request_partner_autocomplete(self, action, params, timeout=15)` returns `(False, False)`.
- `models/res_partner.py`: `autocomplete_by_vat` returns `[]`, so there is no VIES fallback (`partner_autocomplete/models/res_partner.py:115-118`).
- `models/ir_module.py`:
  - `_get_modules_from_apps(...)` returns `[]` (`base_import_module/models/ir_module.py:410-436`);
  - `_get_industry_categories_from_apps()` returns `[]`;
  - `button_immediate_install_app()` raises `UserError`.
- `tests/test_no_odoo_host.py`:
  - patch `odoo.modules.module.current_test` to `False`; the early returns are at `iap_tools.py:113` and `iap_autocomplete_api.py:20`;
  - put a recorder on `requests.Session.send` that raises `ConnectionError`;
  - exercise each entry point;
  - assert every recorded host is `127.0.0.1` and every entry point returns its Null value.
- Verify with `--test-tags /afenda_runtime`. **Read the count.**
- Commit `[ADD] afenda_runtime: null adapters for Odoo-hosted services`.

**T3. Deploy files** (`general-purpose` agent). All are new, under `deploy/` unless stated.
- **`Dockerfile`**, multi-stage `python:3.11-slim-bookworm`.
  - Build stage installs `build-essential libpq-dev libldap2-dev libsasl2-dev curl ca-certificates`, runs `pip install -r requirements.txt` into `/opt/venv`, and downloads `wkhtmltox_0.12.6.1-3.bookworm_${TARGETARCH}.deb` from GitHub, checked with `sha256sum -c` against a hash computed once and pinned.
  - Runtime stage installs `libpq5 libldap-2.5-0 libsasl2-2 libmagic1 fontconfig fonts-noto-core fonts-noto-cjk gsfonts ca-certificates` and `./wkhtmltox.deb`, then runs `fc-cache -f`.
  - It creates the user `afenda`, with a home directory, and `mkdir+chown /var/lib/afenda /etc/afenda`.
  - It copies `odoo-bin odoo addons afenda/addons afenda/oca` to `/opt/afenda`, with `COPY --chmod=755` for the scripts.
  - `ENTRYPOINT` runs the entrypoint, and the command runs `/opt/venv/bin/python /opt/afenda/odoo-bin` directly: the gevent child re-execs `sys.argv[0]` (`server.py:950-953`).
- **`entrypoint.sh`** renders `/etc/afenda/odoo.conf` (`chmod 600`) from environment variables:
  - `workers=4`, `max_cron_threads=1`, `list_db=False`, `proxy_mode=True`, `db_name=afenda`;
  - `data_dir=/var/lib/afenda`, `gevent_port=8072`;
  - `admin_passwd` = a pbkdf2 hash taken from a secret file (`config.py:207,1036-1046`);
  - `publisher_warranty_url=http://127.0.0.1:9/`;
  - memory limits sized per worker, and `addons_path=/opt/afenda/addons,/opt/afenda/afenda/addons,/opt/afenda/afenda/oca/server-brand,/opt/afenda/afenda/oca/web`.
  It then `exec`s the given command with `-c`. Database credentials come from `PGHOST/PGUSER/PGPASSWORD`. **Never** set `PGDATABASE` (`config.py:372`).
- **`compose.yaml`** has four services:
  - `db`: `postgres:16` with `POSTGRES_USER=xforge`, `POSTGRES_DB=postgres`, the password from a secret, a `pg_isready` healthcheck and a named volume.
  - `init`: a one-shot service that runs `db init afenda -c $RC --password …`, then `module install afenda_brand afenda_runtime -c $RC`, then an `odoo-bin shell -c $RC` script that sets `web.base.url`, `web.base.url.freeze=True` and `report.url=http://127.0.0.1:8069`, and ends with `env.cr.commit()` (`shell.py:147-150`). It is idempotent: it skips when the database already exists.
  - `xforge`: `depends_on` `init: service_completed_successfully`, with the `data_dir` volume.
  - `nginx`: the only published port.
  - `compose.proof.yaml` overrides the network with `internal: true` (R7).
- **`nginx/afenda.conf`**:
  - the `map $http_upgrade $connection_upgrade` block;
  - `/websocket` goes to `xforge:8072` with the Upgrade and Connection headers;
  - `/` goes to `xforge:8069`;
  - headers `X-Forwarded-Host/For/Proto` and `X-Real-IP`;
  - `proxy_read_timeout 720s`, `client_max_body_size 128m`, `location ~ ^/web/database { return 404; }`;
  - TLS is terminated here, and only here: `proxy_mode` trusts exactly one hop (`http.py:190`);
  - `nginx/afenda.tls.conf` is the VPS variant with certbot paths.
- **`backup.sh` / `restore.sh`**: `docker compose exec db pg_dump -Fc` (the server's own client, so no v15/v16 mismatch), plus a tar of the `filestore/afenda` volume taken while `xforge` is stopped, and the reverse for restore.
- **Other new files:**
  - `deploy/README.md`: the VPS recipe (clone `--recurse-submodules`, an A record for `app.nexuscanon.com`, secrets, certbot, `compose up`, a backup cron). Do **not** publish wildcard DNS for nexuscanon.com.
  - `.dockerignore`: `/.git`, `/.venv`, `/.agents`, `/docs` (root only, never `**/docs`), `**/__pycache__`.
  - `.gitattributes`: `deploy/** text eol=lf`.
  - `afenda/tools/tests/test_deploy_static.py`: no file under `deploy/`, and no `Dockerfile`, contains `odoo.com` or `odoocdn`; the Dockerfile has no `nightly.`; the `.dockerignore` excludes nothing under `afenda/addons`.
- Commit `[ADD] deploy: source-built image, compose stack, nginx, backup`, with `git add -f` for the dotfiles.

**T4. Local proof** (orchestrator, run once, in order; `docker compose -f compose.yaml -f compose.proof.yaml`):
1. `build` succeeds. The build log shows no request to an Odoo host.
2. `up`. `init` exits 0. `xforge` becomes healthy.
3. Through nginx on :8080, `/web/login` returns 200 with "AFENDA xForge" in the page, and `/web/database/manager` returns 404.
4. Log in with the generated admin password (local throwaway only).
5. `/websocket` upgrades with **101**.
6. A PDF prints: `report.url` works, and 4 workers do not deadlock.
7. `ir_cron.lastcall` advances within 2 minutes.
8. All of this with **no internet route** (R7).
9. `backup.sh`, then `compose down -v`, `restore.sh`, log in: the data is present.

**T5. Final gates, once each, then commit.**
- Tools suite (≥ 138 OK plus the new tests).
- `/afenda_brand,/afenda_api_docs,/afenda_brand_digest,/afenda_runtime`, reading the count.
- `scan_identity` at 10826 with delta +0.
- `odoo-reviewer` on T2 and T3.
- Then ask the user before `git push` and before touching a VPS.

## Verification

Covered by T4 (end-to-end in Docker, with no egress) and T5 (suites, identity gate, review).
Following CLAUDE.md: during T1 to T3, each edit runs only its narrowest test, and nothing
passing is rerun.

## Needs the user

- The VPS itself: an Ubuntu or Debian box with Docker and SSH.
- The DNS A record for `app.nexuscanon.com`.
- The production secrets (database password and master password), placed as files on the VPS.
- Approval to push.

Everything else is executed without stopping.

## Go-live record (2026-09-23)

Live at `https://app.nexuscanon.com`, landing page at `https://nexuscanon.com`.

- **Host:** DigitalOcean droplet `afenda-app-sgp1`, region `sgp1`, `s-4vcpu-8gb`, Ubuntu 24.04,
  Docker Compose v5.5.1. Cloud firewall `afenda-app` (tag `afenda`) admits 22, 80, 443 only.
  SSH is key-only (`passwordauthentication no`).
- **Code:** `/srv/afenda`, shallow clone of `afenda/deidentify-phase1` at `5d04085c2` through a
  read-only GitHub deploy key, `.env` = `compose.yaml:compose.tls.yaml`.
- **DNS:** nameservers moved from Vercel to DigitalOcean; the zone is
  `deploy/dns/nexuscanon.com.records`, applied by `deploy/dns/apply-do-dns.sh` (11 records).
- **TLS:** one Let's Encrypt certificate for `app.`, the apex and `www`; webroot renewal with
  the nginx reload script in `/etc/letsencrypt/renewal-hooks/deploy/` (`35cbb7050`);
  `certbot renew --dry-run` succeeded.
- **Proof:** the T4 proof, pointed at the live URL and extended with five edge checks (HSTS,
  Secure session cookie, landing page, `www` and `http` redirects), printed
  `17/17 checks passed`. Only 22, 80 and 443 listen publicly.
- **Backup:** `backup.sh` run once by hand (folder 700, files 600); cron 02:40 daily.
- **Mail:** Zoho verified end to end after the move: a reply from `no-reply@nexuscanon.com`
  reached Gmail with SPF, DKIM (`d=nexuscanon.com`, `s=zmail`) and DMARC all `pass`.

Found on the way:

- `doctl compute droplet create --ssh-keys` takes a fingerprint; looking the key up by name
  straight after `ssh-key import` returned empty and produced a keyless droplet.
- DigitalOcean blocks outbound SMTP (25, 465, 587) on this droplet: `smtp.zoho.com` times out on
  all three. The ERP cannot send invitation email until that is solved.
- `iap.odoo.com` resolves from the host. Independence rests on the null adapters
  (`iap.endpoint` = `http://127.0.0.1:9`, checked by the proof), not on DNS; the optional
  zero-egress mode in `deploy/README.md` removes the route as well.

App mail (2026-09-23, after go-live):

- The ERP relays through Resend: outgoing server `Resend`, `smtp.resend.com:2587`,
  `starttls_strict`, FROM filter `nexuscanon.com`, a sending-only key scoped to that domain
  (entered by the owner). Alias domain `nexuscanon.com` sends as `no-reply@nexuscanon.com`.
- Resend domain `nexuscanon.com` (region ap-northeast-1) verified: DKIM `resend._domainkey`,
  CNAMEs `send` and `rsend` (`a24b8e20b`); open and click tracking off.
- End to end: a `mail.mail` sent by the live ERP reached Gmail's inbox with `dkim=pass`
  (`d=nexuscanon.com`, `s=resend`), `spf=pass` (`rsend.nexuscanon.com`) and `dmarc=pass`
  at `p=quarantine`; Resend reports it delivered.
- Open: replies go to `catchall@nexuscanon.com`, which has no mailbox yet.

Independence audit (2026-09-23, live host at `66558f62`):

- Runtime traffic: a 150 s capture of every outbound TCP SYN and DNS query while the full
  proof ran (login, websocket, PDF, cron, web client, `/request-access`) saw DNS lookups for
  `app.nexuscanon.com` only and TCP only to the host's own address and DigitalOcean's metadata
  service (169.254.169.254, its monitoring agent). Nothing reached Odoo S.A. or any other third
  party.
- Service endpoints in the database: `iap.endpoint`, `iap.partner_autocomplete.endpoint`,
  `enrich.endpoint`, `reveal.endpoint`, `sms.endpoint`, `snailmail.endpoint`,
  `html_editor.media_library_endpoint` and `html_editor.olg_api_endpoint` are all
  `http://127.0.0.1:9`. The weekly "Publisher: Update Notification" cron posts to
  `publisher_warranty_url = http://127.0.0.1:9/` from the rendered `odoo.conf` (the upstream
  default in `odoo/tools/config.py:215` is still `services.odoo.com`, so the deploy's config
  line is what keeps it dead).
- Browser: the login page, the web client and its 6 asset bundles (9.8 MB) name no Odoo or
  OpenERP host. The only foreign load targets belong to features a user must trigger (video
  embeds, Unsplash, licence links).
- Build: images from Docker Hub (`python:3.11-slim-bookworm`, `postgres:16`,
  `nginx:1.27-alpine`), packages from Debian and PyPI, wkhtmltopdf from GitHub checked against
  pinned SHA-256; `test_no_vendor_host_in_deploy_files` guards the deploy files in CI.
- Hosting and DNS: the .com registry and 1.1.1.1, 8.8.8.8 and 9.9.9.9 delegate `nexuscanon.com`
  to DigitalOcean; the host, firewall, DNS, object storage (backups) and monitoring are on
  DigitalOcean; mail goes out through Resend and in through Zoho. DMARC reports go to
  `no-reply@nexuscanon.com`.

Restore drill (2026-09-23): the 22:59 backup, pulled from the Spaces bucket (SHA-256 equal to
the host's original), restored into a throwaway local stack. The restored database carried
production's `database.uuid`, the Resend server and alias domain; the branded login page, the
company logo and a 477 KB asset bundle were served from the restored filestore. Found on the
way: `restore.sh` must run with the stack's own `COMPOSE_FILE` (README, Backup and restore).

G1 role rehearsal (2026-09-24, local `afenda-deploy` stack holding the restored production copy,
38 modules, source `e5f65888`):

- Image `afenda/xforge:local` `sha256:77e28122…` built from `git archive e5f65888` plus the two
  OCA submodules, not the working tree, which held a peer session's uncommitted `afenda_brand`
  edits. `make-secrets.sh`: `wrote db_app_password`, `keeping existing` for `db_password`,
  `admin_password` and `master_password_hash`.
- `migrate-db-role.sh --yes`: backup `20260924T035905Z` (dump 2,444,155 B, filestore 2,349,482 B),
  `CREATE ROLE`, `ALTER ROLE`, `ALTER DATABASE`,
  `NOTICE: migrate-db-role: every object in afenda is owned by afenda_app`, exit 0.
- `docker compose up -d`: `init` exited 0 as `afenda_app@db`, `module upgrade --outdated` ran
  `afenda_brand` 19.0.1.0.4 → 19.0.1.0.5 and `afenda_runtime` 19.0.1.1.0 → 19.0.1.2.0 with both
  post-migrate scripts; `xforge` healthy. The 19.0.1.2.0 migration took the invitation
  marketing out: the pre-migration dump's `mail_template` data held `12+ million` and
  `page/tour` once each, and afterwards none of the four `auth_signup` templates contains
  either.
- Verified as the app role: `afenda_app super=false`; sessions on `afenda` other than `xforge`:
  `afenda_app`; objects in `public` not owned by `afenda_app` (extension members aside): `0`;
  `/web/health` `{"status": "pass"}`; `AFENDA xForge` on `/web/login`: 2;
  `SEQ OK as afenda_app` from `odoo-bin shell` creating an `ir.sequence` (rolled back, 0
  `g1-check` rows left); `module upgrade afenda_brand afenda_runtime` exit 0, 0 ERROR lines.
- Backup and restore as the app role: backup `20260924T040337Z`, `restore: done`, database
  owner `afenda_app`, objects not owned by `afenda_app`: `0`, `/web/health` pass.
- Rollback: the pre-Task-3 `compose.yaml` (from `80b22da2f^`) with `compose.proof.yaml` recreated
  db, init and xforge; `init` exited 0 as `xforge@db`, `/web/health` pass, the app's sessions
  `xforge`, ownership still `0` off `afenda_app`. Forward again with the current files: `init`
  exit 0, `/web/health` pass, the app's sessions `afenda_app`.
- Found: `docker compose start xforge` in the backup, restore and migrate restart traps also
  starts the existing `init` container, so during the migration the pre-migration `init` (as
  `xforge`) ran twice, once after ownership had moved. Here it had nothing outdated to upgrade
  and created no objects (ownership `0` afterwards), but it would create superuser-owned
  objects if the running image ever carried a newer module version than the database.
  Closed by the follow-up "restart only the app after backups and restores": all three traps
  now start the existing `xforge` container by id (`docker start "$(docker compose ps -aq
  xforge)"`), so none of them starts `init` any more.

G1 on the live host (2026-09-24, Task 5 of docs/superpowers/plans/2026-09-24-afenda-g1-hardening.md):

- Deployed `943d1d4a4c8f4820191a64de6c90fd0f0ea07a4e` (CI green: `0 failed, 0 error(s) of 72 tests`, run as the NOSUPERUSER role on a fresh database); rollback target recorded first: `66558f6232710c9b48f26ce7f462575c5ae8f1e6`.
- 05:52Z backup cron held (one line commented), pinned commit checked out, `db_app_password` generated, image built; `docker compose up -d db`; `migrate-db-role.sh --yes`: `every object in afenda is owned by afenda_app`, exit 0; `redeploy.sh 943d1d4a4…`: `/web/health passes`.
- Verified: `afenda_app super=false`; app connections `afenda_app`; database owner `afenda_app`; 0 objects owned by anyone else; `afenda_brand 19.0.1.0.5` (icon-cache migration) and `afenda_runtime 19.0.1.2.0` (invitation text) applied; 0 mail templates with the user-count claim or `/page/tour`; Resend server `true 2587 starttls_strict`; `SEQ OK as afenda_app` with the DDL rolled back; as `afenda_app` a PDF rendered (`%PDF`), 11 crons have run, service endpoints `http://127.0.0.1:9`, HSTS and redirects unchanged; cron restored (one active line) and `offsite.sh` run by hand (`0 differences`).
- The proof script's admin login failed: the `admin` user was written at 05:23:22Z, before this run, and `secrets/admin_password` no longer matches. The password was not touched; the owner confirms or refreshes the file. The checks that needed that session were run as `afenda_app` instead (above).

Hardening follow-ups on the live host (2026-09-24, 06:53Z–06:54Z):

- Deployed `47793654e88b2d8cb94eda71b69223b0907a5533` with `redeploy.sh`. It carries the app-only restart traps (`da9bf790f`) and the restore that re-runs `init` (`62cba13b0`). CI was green first: `afenda-ci` passed, and `afenda-image` reported `0 failed, 0 error(s) of 72 tests`. Rollback target: `943d1d4a4c8f4820191a64de6c90fd0f0ea07a4e`. Result: `/web/health passes`, exit 0.
- Verified:
  - `afenda_app super=false createdb=true`.
  - App connections come from `afenda_app`.
  - 0 objects in `public` are owned by anyone other than `afenda_app`.
  - Module versions `afenda_brand 19.0.1.0.5` and `afenda_runtime 19.0.1.2.0`.
  - One `docker start` restart line in each of `backup.sh`, `restore.sh` and `migrate-db-role.sh`, and `restore.sh` re-runs `init`.
  - One active backup cron line.
  - `db` and `nginx` were not recreated; `xforge` is healthy.
  - `/web/health` returns pass, and the landing page returns 200.
- `NOCREATEDB` applied on the owner's go (07:12Z, the README's `ALTER ROLE afenda_app NOCREATEDB`): the role went from `createdb=true` to `super=false createdb=false createrole=false login=true`, 7 `afenda_app` sessions stayed connected, `/web/health` passed and `/web/login` returned 200. To undo: `ALTER ROLE afenda_app CREATEDB`.

Auth pages release (2026-09-24, 18:49Z-18:53Z):

- Pushed `68b0b99133ac5dfbefab4a63dfde93e311045d06`, the auth release squashed from 17 local commits; industry packs excluded as unfinished. Then pushed `8336f07379e448dc5976dcb65235d754ab223b4f`, test_crystal_bear on the stdlib XML parser, because afenda-ci's tools job has no lxml.
- CI on `8336f0737`:
  - afenda-ci: `Ran 273 tests ... OK`;
  - afenda-image: `0 failed, 0 error(s) of 86 tests` at the raised floor of 86.
- Production modules before the deploy: `auth_signup` and `auth_totp` installed. They are now afenda_brand dependencies.
- `redeploy.sh 8336f0737…`: `/web/health passes`, exit 0; rollback target `47793654e88b2d8cb94eda71b69223b0907a5533`.
- Verified on the live host:
  - afenda_brand 19.0.1.0.6 and the `afenda_brand.auth_bear` view present; no ERROR in the init log;
  - `afenda_app super=false createdb=false`, 0 objects owned by another role;
  - Resend `true 2587 starttls_strict`, one backup cron line;
  - /web/login: h1 "Growth is kept, not found.", the inline bear, "Request access", no tagline, no odoo.com;
  - the live frontend bundle carries the one focus ring, the height-bound headline and the bear scales, and no `#017e84`, which also releases the teal rule `3ba94c99c`;
  - /web/reset_password: h1 "Roots remember the way back." with one back action; /web/signup without a token 404; /web/database/manager 404;
  - at 1280x633 the sign-in page fits without a scrollbar, with no console errors.
