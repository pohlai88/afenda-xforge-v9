#!/usr/bin/env bash
# Delete backup folders older than KEEP_DAYS days under BACKUP_ROOT.
#
#   deploy/prune-backups.sh BACKUP_ROOT KEEP_DAYS
#
# backup.sh calls it after a verified backup. Only folders named like its
# stamps (YYYYMMDDTHHMMSSZ) are candidates, so anything else an operator puts
# there stays, and the newest stamp is always kept, however old it is: a host
# whose backups stopped must not prune away its last one.
set -euo pipefail

[ "$#" -eq 2 ] || { echo "usage: $0 BACKUP_ROOT KEEP_DAYS" >&2; exit 2; }
root=$1
days=$2
[[ $days =~ ^[1-9][0-9]*$ ]] \
    || { echo "prune-backups: KEEP_DAYS must be a positive integer, got '$days'" >&2; exit 2; }
[ -d "$root" ] || { echo "prune-backups: no such folder: $root" >&2; exit 1; }

stamp='[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z'
newest=$(find "$root" -mindepth 1 -maxdepth 1 -type d -name "$stamp" | sort | tail -n 1)

find "$root" -mindepth 1 -maxdepth 1 -type d -name "$stamp" -mmin +$((days * 1440)) -print0 \
    | while IFS= read -r -d '' dir; do
          [ "$dir" = "$newest" ] && continue
          rm -rf -- "$dir"
          echo "prune-backups: deleted $dir"
      done
