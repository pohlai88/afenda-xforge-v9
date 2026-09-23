#!/usr/bin/env bash
# Restore a folder written by backup.sh. This REPLACES the afenda database
# and its filestore, so it refuses to run without --yes.
#
#   deploy/restore.sh BACKUP_DIR --yes
#
# The db service must be running. xforge is stopped for the duration and
# started again on exit.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash: keep container paths as written

usage() { echo "usage: $0 BACKUP_DIR --yes" >&2; exit 2; }
[ "$#" -eq 2 ] || usage
[ "$2" = "--yes" ] || usage

src=$(cd "$1" && pwd)
[ -s "$src/afenda.dump" ] || { echo "restore: $src/afenda.dump missing or empty" >&2; exit 1; }
[ -s "$src/filestore.tgz" ] || { echo "restore: $src/filestore.tgz missing or empty" >&2; exit 1; }
tar -tzf "$src/filestore.tgz" > /dev/null

cd "$(dirname "$0")"
docker compose exec -T db pg_restore -l < "$src/afenda.dump" > /dev/null

# nginx resolved the old xforge address when it started; reload it so it
# re-resolves the restarted container. A failed reload must not replace the
# exit status of the script that is ending, hence `|| true`.
restart_xforge() {
    docker compose start xforge >/dev/null
    docker compose exec -T nginx nginx -s reload || true
}
docker compose stop xforge
trap restart_xforge EXIT

echo "restore: replacing database afenda"
docker compose exec -T db dropdb -U xforge --if-exists --force afenda
docker compose exec -T db createdb -U xforge -O xforge afenda
docker compose exec -T db pg_restore -U xforge -d afenda --no-owner --role=xforge < "$src/afenda.dump"

echo "restore: replacing filestore/afenda"
docker compose run --rm --no-deps -T --entrypoint sh xforge -c \
    'set -e; mkdir -p /var/lib/afenda/filestore; rm -rf /var/lib/afenda/filestore/afenda; tar -C /var/lib/afenda/filestore -xzf -' \
    < "$src/filestore.tgz"

echo "restore: done from $src"
