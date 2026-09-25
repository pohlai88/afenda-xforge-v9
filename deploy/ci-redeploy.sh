#!/usr/bin/env bash
# The one command the CI deploy key may run: redeploy the commit CI tested.
#
# Installed as the key's forced command in the deploy user's
# ~/.ssh/authorized_keys (deploy/README.md, "Automatic deploys"):
#
#   command="/srv/afenda/deploy/ci-redeploy.sh",restrict ssh-ed25519 AAAA... afenda-ci-deploy
#
# sshd then runs this script whatever the client asked for, and hands the
# client's command over as SSH_ORIGINAL_COMMAND. The only thing accepted
# there is a full 40-character commit id, which goes to redeploy.sh as its
# REF; anything else is refused before redeploy.sh is touched. So a leaked
# key can redeploy a commit that exists on GitHub, and nothing more.
#
# One deploy at a time (flock, exit 75 if another holds the lock), and a
# commit that is already checked out is not rebuilt, so two CI runs that
# both finish green for one commit deploy it once.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
sha=${SSH_ORIGINAL_COMMAND:-}

if ! [[ $sha =~ ^[0-9a-f]{40}$ ]]; then
    echo "ci-redeploy: expected a full commit id, got: ${sha:0:80}" >&2
    exit 64
fi

exec 9>"${AFENDA_DEPLOY_LOCK:-/tmp/afenda-redeploy.lock}"
if ! flock -n 9; then
    echo "ci-redeploy: another deploy is running; not starting a second one" >&2
    exit 75
fi

current=$(git -C "$here" rev-parse HEAD)
if [ "$current" = "$sha" ]; then
    echo "ci-redeploy: already at $sha; nothing to do"
    exit 0
fi

exec "$here/redeploy.sh" "$sha"
