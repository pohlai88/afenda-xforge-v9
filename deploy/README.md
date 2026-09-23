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
landing page), `dns/` (the DigitalOcean zone), `make-secrets.sh`, `backup.sh`,
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
   it so the stored renewal config is webroot plus the reload hook:

   ```bash
   certbot certonly --webroot -w /var/www/certbot --cert-name app.nexuscanon.com \
       -d app.nexuscanon.com -d nexuscanon.com -d www.nexuscanon.com \
       --force-renewal \
       --deploy-hook 'cd /srv/afenda/deploy && docker compose exec -T nginx nginx -s reload'
   certbot renew --dry-run          # must report success for app.nexuscanon.com
   ```

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
   40 2 * * *  /srv/afenda/deploy/backup.sh /var/backups/afenda >> /var/log/afenda-backup.log 2>&1
   ```

   Copy `/var/backups/afenda` off the host, and prune it; the script never
   deletes old backups.

### Optional: zero egress

Adding `compose.proof.yaml` to `COMPOSE_FILE` in production
(`COMPOSE_FILE=compose.yaml:compose.tls.yaml:compose.proof.yaml`) puts
xforge, init and db on an `internal` network with no outbound route at all;
only nginx keeps a normal network. Nothing in G0 needs egress. With it on,
outgoing email over SMTP is blocked until a relay reachable from that
network is provided.

## Upgrades

Check out the new tag, `docker compose build`, then `docker compose up -d`.
`init` reruns: it skips `db init` on the existing database, installing an
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
locally: `index.html`, `lockup.svg` and `fonts/`. It is light-only, runs no
JavaScript and names no host: its two links are written `__PUBLIC_URL__/...`,
and `nginx/40-afenda-site.sh` replaces that with `PUBLIC_URL` (from `.env`,
default `http://localhost:8080`) each time nginx starts. After changing the
page or `PUBLIC_URL`, `docker compose up -d nginx` (or `restart nginx`)
applies it. `www.nexuscanon.com` redirects to `nexuscanon.com`.

`lockup.svg` is a byte copy of `addons/web/static/img/odoo_logo.svg`, the
generated product lockup; `afenda/tools/tests/test_deploy_static.py` fails
when they differ. After the lockup is regenerated, from the repository root:

```bash
cp addons/web/static/img/odoo_logo.svg deploy/site/lockup.svg
```

### Regenerating the site fonts

The two woff2 files are subsets (Basic Latin, Latin-1, dashes, quotes,
ellipsis) of the brand fonts in `afenda_brand`. From the repository root,
with `fontTools` and `brotli` in `.venv`:

```bash
.venv/Scripts/python -m fontTools.subset afenda/addons/afenda_brand/static/fonts/SourceSerif4-Semibold.ttf --unicodes="U+0020-007E,U+00A0-00FF,U+2013-2014,U+2018-201D,U+2026" --flavor=woff2 --output-file=deploy/site/fonts/SourceSerif4-Semibold.woff2
.venv/Scripts/python -m fontTools.subset afenda/addons/afenda_brand/static/fonts/SourceSans3-VF.ttf --unicodes="U+0020-007E,U+00A0-00FF,U+2013-2014,U+2018-201D,U+2026" --flavor=woff2 --output-file=deploy/site/fonts/SourceSans3.woff2
```

nginx serves `/fonts/` as immutable for a year and the file names carry no
hash, so a changed font needs a new file name (and its `@font-face` rule
updated) to reach browsers that cached the old one.

## Moving DNS to DigitalOcean

The zone is `dns/nexuscanon.com.records` (tab-separated
`type name data priority ttl`). It has no wildcard and no Resend records.
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

`restore.sh` drops and recreates the `afenda` database from `afenda.dump`,
replaces `filestore/afenda`, then restarts `xforge` and reloads nginx. This
sequence was verified end to end: the restored database kept the original's
`database.create_date`, and the logo was served from the restored filestore.

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
