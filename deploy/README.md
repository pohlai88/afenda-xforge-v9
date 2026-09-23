# AFENDA xForge deployment

A source-built image and a four-service compose stack:

| Service | Role |
|---|---|
| `db` | `postgres:16`, role `xforge`, volume `db-data` |
| `init` | one-shot: `db init` (first run only), `module install afenda_brand afenda_runtime`, system parameters |
| `xforge` | the server: 4 workers, 1 cron thread, gevent on 8072, volume `xforge-data` (`/var/lib/afenda`) |
| `nginx` | the only published port; the one proxy hop in front of `proxy_mode` |

Files: `Dockerfile` (built from the repository root), `entrypoint.sh` (renders
`/etc/afenda/odoo.conf` from the environment), `init.sh` + `init_params.py`,
`compose.yaml`, `compose.proof.yaml` (no route out), `compose.tls.yaml` (VPS),
`nginx/afenda.conf`, `nginx/afenda.tls.conf`, `make-secrets.sh`, `backup.sh`,
`restore.sh`.

Run every command below from `deploy/`.

## Local

```bash
docker compose build
./make-secrets.sh              # needs the image: it hashes the master password with it
docker compose up -d
# http://localhost:8080, login `admin`, password in secrets/admin_password
```

Independence proof (xforge, init and db on an `internal: true` network):

```bash
docker compose -f compose.yaml -f compose.proof.yaml up -d
```

## VPS

Requires Docker Engine with the Compose plugin **>= 2.24.4**: `compose.tls.yaml`
uses the `!override` merge tag, which older Compose versions reject. Check with
`docker compose version`.

1. **DNS.** One `A` record, `app.nexuscanon.com` → the VPS address. Publish no
   wildcard record for `nexuscanon.com`.
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
5. **First certificate.** Issue it before the stack is up, while port 80 is
   still free:

   ```bash
   mkdir -p /var/www/certbot
   certbot certonly --standalone -d app.nexuscanon.com
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
   certbot certonly --webroot -w /var/www/certbot -d app.nexuscanon.com \
       --force-renewal \
       --deploy-hook 'cd /srv/afenda/deploy && docker compose exec -T nginx nginx -s reload'
   certbot renew --dry-run          # must report success for app.nexuscanon.com
   ```

   From here the distribution's certbot timer renews on its own; no cron
   line is needed for certificates.
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
`init` reruns: it skips `db init` on the existing database, and installing an
already-installed module is a no-op. Upgrading module data (`module upgrade`)
is a separate, deliberate step:

```bash
docker compose run --rm init sh -c '/opt/venv/bin/python /opt/afenda/odoo-bin module upgrade -c "$RC" afenda_brand afenda_runtime'
```

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
