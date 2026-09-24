#!/usr/bin/env bash
# Move the existing afenda database to the least-privilege role afenda_app,
# or back to xforge with --rollback. Backup first; idempotent; the app is
# stopped while ownership moves, so no request or cron creates an object
# under the old owner mid-way.
#
#   deploy/migrate-db-role.sh --yes
#   deploy/migrate-db-role.sh --rollback --yes
#
# Tables go before sequences: ALTER TABLE carries the sequences and indexes
# its columns own, and ALTER SEQUENCE on such a sequence is refused.
# Extension members (pg_trgm) stay with the superuser. REASSIGN OWNED is not
# used: it would also hand over the postgres and template databases. The
# ownership change is one transaction with a 5 s lock timeout, and it raises
# unless every object ends up owned by the target.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"
usage() { echo "usage: $0 [--rollback] --yes" >&2; exit 2; }
target=afenda_app
if [ "${1:-}" = "--rollback" ]; then target=xforge; shift; fi
[ "$#" -eq 1 ] && [ "$1" = "--yes" ] || usage

docker compose exec -T db test -s /run/secrets/db_app_password \
    || { echo "migrate-db-role: the db container has no db_app_password secret; run make-secrets.sh and 'docker compose up -d db' first" >&2; exit 1; }

./backup.sh "${BACKUP_ROOT:-/var/backups/afenda}"

restart_xforge() {
    docker compose start xforge >/dev/null
    docker compose exec -T nginx nginx -s reload || true
}
docker compose stop xforge
trap restart_xforge EXIT

if [ "$target" = afenda_app ]; then
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U xforge -d postgres <<'SQL'
\set pw `cat /run/secrets/db_app_password`
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'afenda_app') AS create_role \gset
\if :create_role
CREATE ROLE afenda_app LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\endif
ALTER ROLE afenda_app PASSWORD :'pw';
SQL
fi
docker compose exec -T db psql -1 -v ON_ERROR_STOP=1 -U xforge -d afenda -v target="$target" <<'SQL'
SET LOCAL lock_timeout = '5s';
SELECT set_config('afenda.target', :'target', true);
ALTER DATABASE afenda OWNER TO :"target";
DO $$
DECLARE r record; t text := current_setting('afenda.target'); left_over int;
BEGIN
  FOR r IN SELECT format('ALTER %s %I.%I OWNER TO %I',
                         CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END,
                         n.nspname, c.relname, t) AS q
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
              AND pg_get_userbyid(c.relowner) <> t
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
  LOOP EXECUTE r.q; END LOOP;
  FOR r IN SELECT format('ALTER SEQUENCE %I.%I OWNER TO %I', n.nspname, c.relname, t) AS q
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'S' AND pg_get_userbyid(c.relowner) <> t
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('e', 'a'))
  LOOP EXECUTE r.q; END LOOP;
  FOR r IN SELECT format('ALTER FUNCTION %s OWNER TO %I', p.oid::regprocedure, t) AS q
             FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND pg_get_userbyid(p.proowner) <> t
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
  LOOP EXECUTE r.q; END LOOP;
  SELECT count(*) INTO left_over FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
     AND pg_get_userbyid(c.relowner) <> t
     AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e');
  IF left_over > 0 THEN
    RAISE EXCEPTION 'migrate-db-role: % objects are not owned by %', left_over, t;
  END IF;
  RAISE NOTICE 'migrate-db-role: every object in afenda is owned by %', t;
END $$;
SQL
echo "migrate-db-role: afenda now owned by $target"
