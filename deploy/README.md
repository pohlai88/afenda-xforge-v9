# AFENDA xForge deployment

A source-built image and a four-service compose stack:

| Service | Role |
|---|---|
| `db` | `postgres:16`, volume `db-data`; bootstrap superuser `xforge` (backups, restores, `migrate-db-role.sh`) plus least-privilege `afenda_app` (what `init` and the server connect as) — see [Database roles](#database-roles) |
| `init` | one-shot: `db init` (first run only), `module install afenda_brand afenda_runtime afenda_api_docs`, `module upgrade --outdated` on an existing database, system parameters |
| `xforge` | the server: 4 workers, 1 cron thread, gevent on 8072, volume `xforge-data` (`/var/lib/afenda`) |
| `nginx` | the only published ports; the one proxy hop in front of `proxy_mode`; serves the landing page (`site/`) |

Files: `Dockerfile` (built from the repository root), `entrypoint.sh` (renders
`/etc/afenda/odoo.conf` from the environment), `init.sh` + `init_params.py`,
`compose.yaml`, `compose.proof.yaml` (no route out), `compose.tls.yaml` (VPS),
`nginx/afenda.conf`, `nginx/afenda.tls.conf`, `nginx/40-afenda-site.sh`
(writes `PUBLIC_URL` into the landing page at nginx start), `site/` (the
landing page), `dns/` (the DigitalOcean zone), `make-secrets.sh`, `backup.sh`
(with `prune-backups.sh`), `offsite.sh` (copies backups off the host),
`redeploy.sh` (one-command upgrade), `restore.sh`.

Run every command below from `deploy/`.

## Local

```bash
docker compose build
./make-secrets.sh              # needs the image: it hashes the master password with it
docker compose up -d
# http://localhost:8080, login `admin`, password in secrets/admin_password
#   -- only on a database this step just created. That file is spent after the
#   first init and is not kept in step with the account; see secrets/README.md.
# http://localhost:8081, the landing page; its links point at PUBLIC_URL
```

Independence proof (xforge, init and db on an `internal: true` network):

```bash
docker compose -f compose.yaml -f compose.proof.yaml up -d
```

## Updating the base images

Every base image is pinned as `<tag>@sha256:<digest>` (`compose.yaml`,
`Dockerfile` `ARG PYTHON_IMAGE`), so a rebuild never picks up a moved tag.
To take an update, resolve the tag's current index digest, replace it, and
ship it like any change:

    docker buildx imagetools inspect postgres:16 --format '{{json .Manifest.Digest}}'
    docker buildx imagetools inspect nginx:1.27-alpine --format '{{json .Manifest.Digest}}'
    docker buildx imagetools inspect python:3.11-slim-bookworm --format '{{json .Manifest.Digest}}'

Stay on the same postgres major version: a new major needs a dump and restore
(`backup.sh`, then `restore.sh` into a new volume), not a digest bump.

## VPS

Requires Docker Engine with the Compose plugin **>= 2.24.4**: `compose.tls.yaml`
uses the `!override` merge tag, which older Compose versions reject. Check with
`docker compose version`.

1. **DNS.** `nexuscanon.com` and `app.nexuscanon.com` → the VPS address, and
   `www` → `nexuscanon.com`. Publish no wildcard record. The zone is kept as
   code in `dns/`; see [Moving DNS to DigitalOcean](#moving-dns-to-digitalocean).
2. **Code.** Check out the release tag with its submodules (`afenda/oca/*`):

   ```bash
   git clone --recurse-submodules --branch <release-tag> <repository-url> /srv/afenda
   cd /srv/afenda/deploy
   ```

3. **Configuration.** Create `deploy/.env` (git ignores dotfiles):

   ```bash
   cat > .env <<'EOF'
   COMPOSE_FILE=compose.yaml:compose.tls.yaml
   PUBLIC_URL=https://app.nexuscanon.com
   EOF
   ```

   `PUBLIC_URL` becomes `web.base.url`, frozen, on every `init` run.
4. **Image and secrets.**

   ```bash
   docker compose build
   ./make-secrets.sh
   ```

   Keep a copy of `secrets/` somewhere safe outside the host; `db_password`
   and `master_password` cannot be recovered from the stack. `secrets/` also
   holds `db_app_password` once a host has run [Moving an existing
   host](#moving-an-existing-host) or `make-secrets.sh` has otherwise created
   it; refresh the off-host copy after that happens, or a restore of the
   secrets folder alone will be missing it.
5. **First certificate.** One certificate, lineage `app.nexuscanon.com`, for
   the three names nginx serves. Issue it before the stack is up, while port
   80 is still free:

   ```bash
   mkdir -p /var/www/certbot
   certbot certonly --standalone --cert-name app.nexuscanon.com \
       -d app.nexuscanon.com -d nexuscanon.com -d www.nexuscanon.com
   ```

   This stores `authenticator = standalone` in the renewal config, which can
   never renew once nginx holds port 80. Step 7 replaces it.
6. **Start.**

   ```bash
   docker compose up -d
   docker compose logs -f init     # ends with "afenda-init: done"
   ```

7. **Switch renewal to webroot, once.** nginx now serves
   `/.well-known/acme-challenge/` on port 80 from `/var/www/certbot`
   (`nginx/afenda.tls.conf`, mounted by `compose.tls.yaml`). Re-issue through
   it so the stored renewal config is webroot, after installing the nginx
   reload hook:

   ```bash
   cat > /etc/letsencrypt/renewal-hooks/deploy/afenda-nginx-reload.sh <<'EOF'
   #!/bin/sh
   # Reload the stack's nginx so it serves the renewed certificate.
   cd /srv/afenda/deploy && docker compose exec -T nginx nginx -s reload
   EOF
   chmod 755 /etc/letsencrypt/renewal-hooks/deploy/afenda-nginx-reload.sh
   certbot certonly --webroot -w /var/www/certbot --cert-name app.nexuscanon.com \
       -d app.nexuscanon.com -d nexuscanon.com -d www.nexuscanon.com \
       --force-renewal
   certbot renew --dry-run          # must report success for app.nexuscanon.com
   ```

   The reload is a script in `renewal-hooks/deploy/`, which certbot runs
   after every renewal. It cannot be a `--deploy-hook 'cd … && …'`:
   certbot checks that the hook's first word is a program on `PATH`, and
   `cd` is a shell builtin, so it refuses with "Unable to find deploy-hook
   command cd".

   A host whose certificate still covers `app.nexuscanon.com` alone: once the
   bare domain and `www` resolve to it, run this same command (the old
   config's one port-80 server is the default for every name, so it already
   serves their challenges), then deploy the new
   `nginx/afenda.tls.conf`, which expects all three names in the one
   certificate. Adding `-d` names to the existing `--cert-name` lineage
   replaces its name list.

   From here the distribution's certbot timer renews on its own; no cron
   line is needed for certificates. The one certificate covers `app.`, the
   bare domain and `www.`, so a broken apex or `www` record fails the whole
   renewal, `app.nexuscanon.com` included.
8. **Backups** (root crontab). The folder is private; `backup.sh` also runs
   with `umask 077`, because a dump holds password hashes, TOTP secrets and
   `database.secret`:

   ```bash
   install -d -m 700 /var/backups/afenda
   ```

   ```cron
   40 2 * * *  { /srv/afenda/deploy/backup.sh /var/backups/afenda && /srv/afenda/deploy/offsite.sh /var/backups/afenda spaces:afenda-backups-sgp1; } >> /var/log/afenda-backup.log 2>&1
   ```

   `backup.sh` keeps 14 days on the host (`KEEP_DAYS`), always including the
   newest backup; `offsite.sh` copies every backup off the host, checks the
   copy, and keeps 30 days there (`KEEP_REMOTE_DAYS`). See
   [Off-host copies](#off-host-copies) for the one-time rclone setup.

### Optional: zero egress

Adding `compose.proof.yaml` to `COMPOSE_FILE` in production
(`COMPOSE_FILE=compose.yaml:compose.tls.yaml:compose.proof.yaml`) puts
xforge, init and db on an `internal` network with no outbound route at all;
only nginx keeps a normal network. Nothing in G0 needs egress. With it on,
outgoing email over SMTP is blocked until a relay reachable from that
network is provided.

## Upgrades

One command, on the VPS, from `deploy/`:

```bash
./redeploy.sh <commit>           # the full commit id whose CI passed, e.g. ./redeploy.sh 4f8b2c1e9a7d3f0561c8e2b9a4d6f1c8e0b2a4d6
```

Always pass the commit explicitly. `redeploy.sh` defaults `ref` to `main` (`redeploy.sh:21`) but
only fetches it after `backup.sh` has already run (`redeploy.sh:37-38`), so a bare `./redeploy.sh`
can deploy whatever is on `main` at that later moment, not the commit the operator actually
checked CI for. Use the `main` commit whose `afenda-ci` and `afenda-image` runs both succeeded
(Actions tab), and pass its full 40-character SHA — not `main`, not a short SHA, not a tag.

It refuses a checkout with tracked changes, backs up first, fetches the ref
(shallow) with its submodules, builds, starts the stack, and ends with
`redeploy: …/web/health passes; now at <commit>`. A failed build puts the
previous commit back by itself. A failure after the stack started prints the
commit and the backup to return to, because `init` may already have upgraded
the database.

What it runs underneath: check out the new commit, `docker compose build`,
then `docker compose up -d`. `init` reruns: it skips `db init` on the existing database, installing an
already-installed module is a no-op (a module newly added to `MODULES` in `init.sh` is installed
here, on the existing database), and then it runs
`module upgrade --outdated afenda_brand afenda_runtime afenda_api_docs`. That upgrades a
module only when its manifest `version` on disk is newer than the one the
database recorded (`odoo/cli/module.py`), so bumping the version is what
ships new module data, and a plain restart reloads nothing. To force an
upgrade without a version bump:

```bash
docker compose run --rm init sh -c '/opt/venv/bin/python /opt/afenda/odoo-bin module upgrade -c "$RC" afenda_brand afenda_runtime afenda_api_docs'
```

### Deploying

Deploys are manual: after a merge to `main`, check the Actions tab for the commit whose
`afenda-ci` and `afenda-image` runs both succeeded, then run `./redeploy.sh <that commit's full
SHA>` on the host — e.g. `./redeploy.sh 4f8b2c1e9a7d3f0561c8e2b9a4d6f1c8e0b2a4d6`. Never run a
bare `./redeploy.sh`: it defaults to `main`'s current head (`redeploy.sh:21`) and fetches it only
after `backup.sh` has already run (`redeploy.sh:37-38`), so it can deploy a commit pushed after
the operator checked CI, not the one whose green run they verified. There is no automatic deploy
(removed 2026-09-26: it never ran and needed an SSH key into production).

## The landing page

`site/` is the page at `nexuscanon.com`, and at `http://localhost:8081`
locally: `index.html`, `site.css`, `lockup-dark.svg` and `fonts/`. It is one
screen in black and white, runs no JavaScript (its entrance is a CSS
animation) and names no host. Styles come only from `site.css`, never inline,
so the CSP in `nginx/` is plain `default-src 'self'` with no hash to keep in
step. Its two links are written `__PUBLIC_URL__/...`,
and `nginx/40-afenda-site.sh` replaces that with `PUBLIC_URL` (from `.env`,
default `http://localhost:8080`) each time nginx starts. After changing the
page or `PUBLIC_URL`, `docker compose up -d nginx` (or `restart nginx`)
applies it. `www.nexuscanon.com` redirects to `nexuscanon.com`.

`lockup-dark.svg` is a byte copy of `addons/web/static/img/odoo_logo_dark.svg`,
the generated product lockup for a dark ground, in its own colours;
`afenda/tools/tests/test_deploy_static.py` fails when they differ. After the
lockup is regenerated, from the repository root:

```bash
cp addons/web/static/img/odoo_logo_dark.svg deploy/site/lockup-dark.svg
```

### Regenerating the site font

The one woff2 file is a subset (Basic Latin, Latin-1, dashes, quotes,
ellipsis) of the variable Source Sans 3 in `afenda_brand`, keeping its full
200–900 weight axis: the page's hairline (250) and heavy (900) weights are
real, not synthesized. From the repository root, with `fontTools` and
`brotli` in `.venv`:

```bash
.venv/Scripts/python -m fontTools.subset afenda/addons/afenda_brand/static/fonts/SourceSans3-VF.ttf --unicodes="U+0020-007E,U+00A0-00FF,U+2013-2014,U+2018-201D,U+2026" --flavor=woff2 --output-file=deploy/site/fonts/SourceSans3.woff2
```

nginx serves `/fonts/` as immutable for a year and the file names carry no
hash, so a changed font needs a new file name (and its `@font-face` rule
updated) to reach browsers that cached the old one.

## Moving DNS to DigitalOcean

The zone is `dns/nexuscanon.com.records` (tab-separated
`type name data priority ttl`). It has no wildcard; app mail goes out through Resend (the `send.` records and `resend._domainkey`).
`dns/apply-do-dns.sh` creates the domain if it is absent and adds each record
that is not already there; it never deletes or changes a record. It needs
`doctl`, authenticated (`doctl auth init`).

1. Apply the zone:

   ```bash
   ./dns/apply-do-dns.sh <droplet-ipv4>
   ```

   A name left with two `A`/`CNAME` answers is listed at the end; remove the
   stale one in the DigitalOcean console.
2. Before switching, check every name against DigitalOcean's own servers:

   ```bash
   dig @ns1.digitalocean.com +short nexuscanon.com A
   dig @ns1.digitalocean.com +short www.nexuscanon.com CNAME
   dig @ns1.digitalocean.com +short app.nexuscanon.com A
   dig @ns1.digitalocean.com +short nexuscanon.com MX
   dig @ns1.digitalocean.com +short nexuscanon.com TXT
   dig @ns1.digitalocean.com +short zmail._domainkey.nexuscanon.com TXT
   dig @ns1.digitalocean.com +short _dmarc.nexuscanon.com TXT
   dig @ns1.digitalocean.com +short nexuscanon.com CAA   # expect: 0 issue "letsencrypt.org"
   ```

   The CAA answer must be exactly `0 issue "letsencrypt.org"`. If it shows
   anything else, or nothing, stop here and fix it before switching the
   nameservers: a wrong CAA record makes Let's Encrypt refuse the certificate.

3. The owner switches the domain's nameservers in Vercel to
   `ns1.digitalocean.com`, `ns2.digitalocean.com` and `ns3.digitalocean.com`.
4. Once `dig +short NS nexuscanon.com` lists the DigitalOcean servers: send
   and receive a test email through Zoho, and confirm that a made-up name
   does not resolve (`dig +short no-such-name.nexuscanon.com` prints
   nothing), so no wildcard survived.

## Backup and restore

```bash
./backup.sh /var/backups/afenda               # stops xforge briefly
./restore.sh /var/backups/afenda/<stamp> --yes # replaces the database and filestore
```

`restore.sh` works against a **running** stack: it execs into `db` and
restarts `xforge`. On a fresh host, bring the stack up first so `init` creates
an empty `afenda`, then restore over it:

```bash
docker compose up -d                          # init creates an empty afenda
./restore.sh /path/to/<stamp> --yes           # drops and replaces it and the filestore
```

Run `restore.sh` with the same `COMPOSE_FILE` the stack was started with (on
the VPS, `.env` sets it): `restore.sh` itself runs `init` deliberately, once
the data is restored, so a mismatched `COMPOSE_FILE` in that shell reaches
`init` too, not just `xforge`. A restore drill on a stack started with
`-f compose.yaml -f compose.proof.yaml` but no `.env` restored the data, then
ran `init` from `compose.yaml` alone; the internal `backend` network came
back without the `db` alias and `init` failed with "could not translate host
name db". `docker compose down` (never `-v`) and `up -d` with the original files
repaired it, and the restored data was intact.

`restore.sh` drops and recreates the `afenda` database from `afenda.dump`,
replaces `filestore/afenda`, reruns `init`, then restarts `xforge` and
reloads nginx. This sequence was verified end to end: the restored database
kept the original's `database.create_date`, and the logo was served from the
restored filestore.

Rerunning `init` matters because `restore.sh` restarts the existing `xforge`
container by id, not through `init`'s `depends_on`, so a plain restore would
otherwise leave whatever `web.base.url` and module versions the dump was
taken with. `init` on an already-initialised database skips `db init`, so
nothing there is destructive; it reapplies this host's `PUBLIC_URL` as
`web.base.url` (frozen) and `report.url`, and installs or upgrades any
outdated module — the same steps a fresh `redeploy.sh` runs. A restore from
another host's backup therefore ends up with this host's parameters, not the
source host's.

A restore run with the pre-G1 version of this script (before this branch
added `afenda_app` and `migrate-db-role.sh`) creates and restores the
database as `xforge`, so a host restored that way is left with `afenda`
owned by `xforge` regardless of what owned it before the dump was taken.
Before a later forward `redeploy.sh` against such a host, run
`./migrate-db-role.sh --yes` first, or `init`'s `afenda_app` connection will
get "permission denied" on those objects.

### Off-host copies

`offsite.sh` pushes `/var/backups/afenda` to a private DigitalOcean Spaces
bucket, `afenda-backups-sgp1`, with rclone. One-time setup, as root on the
VPS:

1. Create the bucket in the DigitalOcean console (Spaces Object Storage,
   region SGP1, private). Creating a bucket needs a full-access key, so it is
   not scripted.
2. Create an access key limited to that bucket, on a workstation with
   `doctl`, and write it straight into the VPS's rclone config without
   printing it:

   ```bash
   doctl spaces keys create afenda-backups --grants 'bucket=afenda-backups-sgp1;permission=readwrite' -o json \
     | python3 -c 'import json,sys; d=json.load(sys.stdin); k=d[0] if isinstance(d,list) else d; print("[spaces]\ntype = s3\nprovider = DigitalOcean\nendpoint = sgp1.digitaloceanspaces.com\nacl = private\nno_check_bucket = true\naccess_key_id = %s\nsecret_access_key = %s" % (k["access_key"], k["secret_key"]))' \
     | ssh root@<vps> 'apt-get install -y -q rclone >/dev/null && install -d -m 700 /root/.config/rclone && umask 077 && cat > /root/.config/rclone/rclone.conf'
   ```

   `no_check_bucket = true` stops rclone from trying to create the bucket,
   which a key limited to one bucket may not do.
3. Run `./offsite.sh /var/backups/afenda spaces:afenda-backups-sgp1` once
   by hand; it ends with `offsite: done`.

To restore from the bucket, copy one stamp back and restore it as usual:

```bash
rclone copy spaces:afenda-backups-sgp1/<stamp> /var/backups/afenda/<stamp>
./restore.sh /var/backups/afenda/<stamp> --yes
```

`backup.sh` writes `afenda.dump` (`pg_dump -Fc`, run by the db container's own
client) and `filestore.tgz` (`filestore/afenda` from the `xforge-data` volume),
both taken while `xforge` is stopped so they match.

## Database roles

Two PostgreSQL roles: `xforge` is the db container's bootstrap superuser,
used only by `backup.sh`, `restore.sh` and `migrate-db-role.sh`. `afenda_app`
is what `init` and the server connect as (`PGUSER`/`PGPASSWORD_FILE` in
`compose.yaml`'s `x-xforge-env`), and it owns the `afenda` database and every
object in it. On an empty volume, `db-init/10-afenda-app-role.sh` creates the
role on the db container's first start; an existing host moves ownership
across with `migrate-db-role.sh`.

`afenda_app` is created with `CREATEDB` only because a fresh host's first
`init` run creates the `afenda` database itself (`db init`). A fresh host
keeps it until that first `init` has created the database. On an initialized
host, removing it takes away the last privilege beyond owning `afenda`:

```bash
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U xforge -d postgres -c "ALTER ROLE afenda_app NOCREATEDB"
```

Nothing afterwards needs it back. `init` on an initialized database only
installs, upgrades and sets parameters (rehearsed: `docker compose run --rm -T
init`, a restart of `xforge` and `module upgrade afenda_runtime` all pass
without it). `restore.sh` drops and creates databases as `xforge`, so it is
unaffected. Re-running `migrate-db-role.sh` does not restore `CREATEDB`: it
creates the role only when it is absent and otherwise only resets its
password. The database manager stays closed (`list_db = False`), so the
server never creates or duplicates a database either.

### Moving an existing host

Run every command in this section from `/srv/afenda/deploy`. Avoid the daily
02:40 UTC backup cron: `backup.sh` stops and starts `xforge` with its own
trap and has no lock against `migrate-db-role.sh` or `redeploy.sh`, so a
collision during this window is possible. Hold the cron line for the
duration and restore it at the end:

```bash
crontab -l | sed 's|^\(40 2 .*backup.sh.*\)$|# \1|' | crontab -
```

```bash
prev=$(git -C /srv/afenda rev-parse HEAD)   # record it, for rollback
new=<the SHA the green CI run tested>       # record it: redeploy.sh below is pinned to this, not the branch head
git -C /srv/afenda fetch --depth 1 origin "$new"
git -C /srv/afenda checkout --detach FETCH_HEAD
git -C /srv/afenda submodule update --init --depth 1
./make-secrets.sh                            # adds only db_app_password
docker compose build                         # now, before migrating: shrinks the superuser window below to minutes
docker compose up -d db
./migrate-db-role.sh --yes                   # ends "every object in afenda is owned by afenda_app"
./redeploy.sh "$new"                         # pinned: a push by another session since $new was recorded is not deployed
```

The old `xforge`-connected server that `migrate-db-role.sh`'s own trap
restarts keeps running, still as the superuser, through the backup and
image build that follow — any object it creates in that window (for
example an `ir.sequence` for a new journal) ends up owned by `xforge`. After
`redeploy.sh` finishes, re-check ownership:

```bash
docker compose exec -T db psql -X -tA -U xforge -d afenda -c \
  "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p','v','m','S') and pg_get_userbyid(c.relowner)<>'afenda_app' and not exists (select 1 from pg_depend d where d.objid=c.oid and d.deptype='e')"
```

A non-zero count here means objects created during that window; run
`./migrate-db-role.sh --yes` once more (idempotent) and re-check before
treating anything else as a failure.

Restore the cron line, and confirm it took:

```bash
crontab -l | sed 's|^# \(40 2 .*backup.sh.*\)$|\1|' | crontab -
crontab -l | grep backup.sh
```

Rollback is `./redeploy.sh "$prev"` only: the app goes back to connecting as
the superuser `xforge`, which can use every object whatever its owner, so
ownership stays with `afenda_app` and nothing further needs to move. That
rebuild starts from `$prev`, older than what the `docker compose build`
above just cached, so its layers are not the ones sitting in the build
cache — expect the build alone to take ~10+ minutes, while the app keeps
running as before. The database stays at whatever module version the
redeploy left it, which is fine for the older code: `module
upgrade --outdated` only upgrades a module when the disk version is newer
than the one the database recorded.

## Notes

- `db_name = afenda` and no `dbfilter`: with a filter set, a restored database
  owned by another role would disappear from the list. `list_db = False` and
  nginx returns 404 for `/web/database*`.
- Never set `PGDATABASE` on the xforge or init services: Odoo reads it as
  `db_name`, and environment values override the config file. The entrypoint
  refuses to start if it is set.
- The image runs as the unprivileged user `afenda`. Secret files are mounted
  as they are on the host, so `make-secrets.sh` leaves them readable (644)
  inside a folder only the owner can enter (700).
