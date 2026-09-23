#!/usr/bin/env bash
# Back up the afenda database and its filestore into one timestamped folder.
#
#   deploy/backup.sh BACKUP_ROOT        (e.g. /var/backups/afenda; keep it out of the repo)
#
# xforge is stopped for the duration so the dump and the filestore describe
# the same moment; it is started again on exit, even after a failure.
# pg_dump runs inside the db container, so the client always matches the
# server version.
#
# Output: BACKUP_ROOT/<UTC timestamp>/afenda.dump   (pg_dump -Fc)
#         BACKUP_ROOT/<UTC timestamp>/filestore.tgz (filestore/afenda)
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash: keep container paths as written

[ "$#" -eq 1 ] || { echo "usage: $0 BACKUP_ROOT" >&2; exit 2; }
root=$(mkdir -p "$1" && cd "$1" && pwd)   # resolved before the cd below
cd "$(dirname "$0")"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$root/$stamp"
mkdir -p "$out"

restart_xforge() { docker compose start xforge >/dev/null; }
docker compose stop xforge
trap restart_xforge EXIT

echo "backup: dumping database afenda"
docker compose exec -T db pg_dump -U xforge -Fc afenda > "$out/afenda.dump"
# A dump pg_restore cannot list is not a backup.
docker compose exec -T db pg_restore -l < "$out/afenda.dump" > /dev/null

echo "backup: archiving filestore/afenda"
docker compose run --rm --no-deps -T --entrypoint tar xforge \
    -C /var/lib/afenda/filestore -czf - afenda > "$out/filestore.tgz"
tar -tzf "$out/filestore.tgz" > /dev/null

echo "backup: done -> $out"
ls -l "$out"
