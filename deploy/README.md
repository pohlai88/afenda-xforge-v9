# AFENDA xForge deployment

A source-built image and a four-service compose stack:

| Service | Role |
|---|---|
| `db` | `postgres:16`, role `xforge`, volume `db-data` |
| `init` | one-shot: `db init` (first run only), `module install afenda_brand afenda_runtime`, `module upgrade --outdated` on an existing database, system parameters |
| `xforge` | the server: 4 workers, 1 cron thread, gevent on 8072, volume `xforge-data` (`/var/lib/afenda`) |
| `nginx` | the only published ports; the one proxy hop in front of `proxy_mode`; serves the landing page (`site/`) |

Files: `Dockerfile` (built from the repository root), `entrypoint.sh` (renders
`/etc/afenda/odoo.conf` from the environment), `init.sh` + `init_params.py`,
`compose.yaml`, `compose.proof.yaml` (no route out), `compose.tls.yaml` (VPS),
`nginx/afenda.conf`, `nginx/afenda.tls.conf`, `nginx/40-afenda-site.sh`
(writes `PUBLIC_URL` into the landing page at nginx start), `site/` (the
landing page), `dns/` (the DigitalOcean zone), `make-secrets.sh`, `backup.sh`
(with `prune-backups.sh`), `offsite.sh` (copies backups off the host),
`redeploy.sh` (one-command upgrade),
`restore.sh`.

Run every command below from `deploy/`.

## Local

```bash
docker compose build
./make-secrets.sh              # needs the image: it hashes the master password with it
docker compose up -d
# http://localhost:8080, login `admin`, password in secrets/admin_password
# http://localhost:8081, the landing page; its links point at PUBLIC_URL
```

Independence proof (xforge, init and db on an `internal: true` network):

```bash
docker compose -f compose.yaml -f compose.proof.yaml up -d
```

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
   and `master_password` cannot be recovered from the stack.
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
./redeploy.sh                   # the branch head; or ./redeploy.sh <commit or tag>
```

It refuses a checkout with tracked changes, backs up first, fetches the ref
(shallow) with its submodules, builds, starts the stack, and ends with
`redeploy: …/web/health passes; now at <commit>`. A failed build puts the
previous commit back by itself. A failure after the stack started prints the
commit and the backup to return to, because `init` may already have upgraded
the database.

What it runs underneath: check out the new commit, `docker compose build`,
then `docker compose up -d`. `init` reruns: it skips `db init` on the existing database, installing an
already-installed module is a no-op, and then it runs
`module upgrade --outdated afenda_brand afenda_runtime`. That upgrades a
module only when its manifest `version` on disk is newer than the one the
database recorded (`odoo/cli/module.py`), so bumping the version is what
ships new module data, and a plain restart reloads nothing. To force an
upgrade without a version bump:

```bash
docker compose run --rm init sh -c '/opt/venv/bin/python /opt/afenda/odoo-bin module upgrade -c "$RC" afenda_brand afenda_runtime'
```

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
the VPS, `.env` sets it). A restore drill on a stack started with
`-f compose.yaml -f compose.proof.yaml` but no `.env` restored the data, then
restarted `init` from `compose.yaml` alone; the internal `backend` network came
back without the `db` alias and `init` failed with "could not translate host
name db". `docker compose down` (never `-v`) and `up -d` with the original files
repaired it, and the restored data was intact.

`restore.sh` drops and recreates the `afenda` database from `afenda.dump`,
replaces `filestore/afenda`, then restarts `xforge` and reloads nginx. This
sequence was verified end to end: the restored database kept the original's
`database.create_date`, and the logo was served from the restored filestore.

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
