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
5. **Certificate.** Issue it before nginx first starts, while port 80 is free:

   ```bash
   mkdir -p /var/www/certbot
   certbot certonly --standalone -d app.nexuscanon.com
   ```

6. **Start.**

   ```bash
   docker compose up -d
   docker compose logs -f init     # ends with "afenda-init: done"
   ```

7. **Renewal and backups** (root crontab):

   ```cron
   17 3 * * *  certbot renew --webroot -w /var/www/certbot --quiet --deploy-hook "cd /srv/afenda/deploy && docker compose exec nginx nginx -s reload"
   40 2 * * *  /srv/afenda/deploy/backup.sh /var/backups/afenda >> /var/log/afenda-backup.log 2>&1
   ```

   Copy `/var/backups/afenda` off the host, and prune it; the script never
   deletes old backups.

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
