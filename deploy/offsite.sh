#!/usr/bin/env bash
# Copy the backup folders off the host with rclone, verify the copy, and only
# then expire old copies on the remote.
#
#   deploy/offsite.sh BACKUP_ROOT REMOTE    (e.g. /var/backups/afenda spaces:afenda-backups-sgp1)
#
# REMOTE is an rclone remote:path. On the VPS the remote `spaces` is a
# DigitalOcean Spaces bucket, configured in /root/.config/rclone/rclone.conf
# with a key limited to that one bucket and `no_check_bucket = true`, because
# such a key may not create buckets (see README.md, "Off-host copies").
#
# `rclone copy` never deletes on the remote, so the remote keeps its own
# history: KEEP_REMOTE_DAYS (default 30) days, longer than the host's
# KEEP_DAYS. Expiry runs only after `rclone check --one-way` has confirmed
# that every local file is on the remote and identical.
set -euo pipefail
umask 077

[ "$#" -eq 2 ] || { echo "usage: $0 BACKUP_ROOT REMOTE" >&2; exit 2; }
root=$1
remote=$2
days=${KEEP_REMOTE_DAYS:-30}
[[ $days =~ ^[1-9][0-9]*$ ]] \
    || { echo "offsite: KEEP_REMOTE_DAYS must be a positive integer, got '$days'" >&2; exit 2; }
[ -d "$root" ] || { echo "offsite: no such folder: $root" >&2; exit 1; }
command -v rclone >/dev/null 2>&1 || { echo "offsite: rclone is not installed" >&2; exit 1; }

echo "offsite: copying $root -> $remote"
rclone copy "$root" "$remote"
echo "offsite: verifying"
rclone check "$root" "$remote" --one-way
echo "offsite: expiring remote copies older than ${days} days"
rclone delete "$remote" --min-age "${days}d"
rclone rmdirs "$remote" --leave-root
echo "offsite: done"
