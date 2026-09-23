#!/usr/bin/env bash
# Generate the stack's secrets into deploy/secrets/ (gitignored).
#
#   deploy/make-secrets.sh
#
# Writes, only for files that do not exist yet:
#   db_password            PostgreSQL password of the xforge role
#   admin_password         password of the `admin` login, set by `db init`
#   master_password        the database-manager master password (kept for the
#                          operator; never mounted into a container)
#   master_password_hash   its pbkdf2_sha512 hash, the value of admin_passwd
#
# Existing files are never overwritten: db_password is baked into the
# PostgreSQL volume on first start, so replacing it would lock the server out.
#
# The hash is computed by passlib inside the image, with the same scheme and
# rounds as the server's own CryptContext (odoo/tools/config.py), so build the
# image first: docker compose -f deploy/compose.yaml build
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash: keep container paths as written

here=$(cd "$(dirname "$0")" && pwd)
dir="$here/secrets"
image=${XFORGE_IMAGE:-afenda/xforge:local}

mkdir -p "$dir"
chmod 700 "$dir"
umask 077

# Subshell without pipefail: tr is ended by SIGPIPE once head has 32 bytes.
random() ( set +o pipefail; LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32 )

write_new() {  # name value
    local path="$dir/$1"
    if [ -e "$path" ]; then
        echo "make-secrets: keeping existing $1"
        return 1
    fi
    printf '%s' "$2" > "$path"
    # Compose mounts secret files as-is; the containers run as non-root
    # users (postgres, afenda) that must read them. The folder stays 700.
    chmod 644 "$path"
    echo "make-secrets: wrote $1"
}

write_new db_password "$(random)" || true
write_new admin_password "$(random)" || true

if [ ! -e "$dir/master_password_hash" ]; then
    if [ ! -e "$dir/master_password" ]; then
        write_new master_password "$(random)"
    fi
    hash=$(docker run --rm -i --entrypoint /opt/venv/bin/python "$image" -c '
import sys
from passlib.context import CryptContext
ctx = CryptContext(schemes=["pbkdf2_sha512"], pbkdf2_sha512__rounds=600_000)
print(ctx.hash(sys.stdin.read()))
' < "$dir/master_password")
    case "$hash" in
        '$pbkdf2-sha512$'*) write_new master_password_hash "$hash" ;;
        *) echo "make-secrets: unexpected hash output: $hash" >&2; exit 1 ;;
    esac
else
    echo "make-secrets: keeping existing master_password_hash"
fi
