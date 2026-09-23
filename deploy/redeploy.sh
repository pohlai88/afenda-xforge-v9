#!/usr/bin/env bash
# Upgrade the running stack to a pushed commit, in one command.
#
#   deploy/redeploy.sh [REF]      (default afenda/deidentify-phase1)
#
# In order, stopping at the first failure:
#   1. refuse if the checkout has tracked changes: a hand edit on the host
#      would be replaced without a trace;
#   2. back up with backup.sh into BACKUP_ROOT (default /var/backups/afenda);
#   3. fetch REF from origin (shallow, as the host's clone is) and check it
#      out detached, with its submodules;
#   4. build the image; if the build fails, put the previous commit back;
#   5. docker compose up -d: init reruns and upgrades outdated modules;
#   6. check that init exited 0 and that PUBLIC_URL/web/health passes.
# From step 5 on the database may already be upgraded, so a failure there
# prints the commit and the backup to go back to instead of rolling back.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash: keep container paths as written

cd "$(dirname "$0")"
ref=${1:-afenda/deidentify-phase1}
backup_root=${BACKUP_ROOT:-/var/backups/afenda}
tries=${HEALTH_TRIES:-60}
wait_s=${HEALTH_WAIT:-5}
public_url=$(sed -n 's/^PUBLIC_URL=//p' .env 2>/dev/null | tail -n 1)
public_url=${public_url:-http://localhost:8080}
public_url=${public_url%/}

repo=$(git rev-parse --show-toplevel)
if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]; then
    echo "redeploy: the checkout has tracked changes; commit or discard them first:" >&2
    git -C "$repo" status --short --untracked-files=no >&2
    exit 1
fi
before=$(git -C "$repo" rev-parse HEAD)

echo "redeploy: backing up into $backup_root"
./backup.sh "$backup_root"
backup=$(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*T*Z' | sort | tail -n 1)

echo "redeploy: fetching $ref"
git -C "$repo" fetch --depth 1 origin "$ref"
git -C "$repo" checkout --detach FETCH_HEAD
git -C "$repo" submodule update --init --depth 1
after=$(git -C "$repo" rev-parse HEAD)
echo "redeploy: $before -> $after"

if ! docker compose build; then
    echo "redeploy: the build failed; putting $before back" >&2
    git -C "$repo" checkout --detach "$before"
    git -C "$repo" submodule update --init --depth 1
    exit 1
fi

fail() {
    echo "redeploy: $1" >&2
    echo "redeploy: the database may already be upgraded. To go back to $before:" >&2
    echo "  git -C $repo checkout --detach $before && git -C $repo submodule update --init --depth 1 \\" >&2
    echo "    && docker compose build && docker compose up -d && ./restore.sh $backup --yes" >&2
    exit 1
}

docker compose up -d || fail "docker compose up failed"
state=$(docker compose ps -a init --format '{{.State}} {{.ExitCode}}')
[ "$state" = "exited 0" ] || fail "init did not finish cleanly ($state); see: docker compose logs init"

for _ in $(seq 1 "$tries"); do
    if curl -fsS --max-time 10 "$public_url/web/health" | grep -q '"status": *"pass"'; then
        echo "redeploy: $public_url/web/health passes; now at $after"
        exit 0
    fi
    sleep "$wait_s"
done
fail "$public_url/web/health did not pass after $tries tries"
