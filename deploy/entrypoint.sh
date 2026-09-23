#!/bin/sh
# Render /etc/afenda/odoo.conf from the environment, then run the command.
#
# Database credentials reach Odoo only through PGHOST / PGUSER / PGPASSWORD
# (PGPORT optional), which Odoo reads as db_host / db_user / db_password.
# PGDATABASE is refused: Odoo reads it as db_name and environment values
# override the config file, so it would silently replace `db_name = afenda`.
#
# Environment:
#   PGHOST, PGUSER                  required
#   PGPASSWORD or PGPASSWORD_FILE   required (the _FILE form reads a secret)
#   ADMIN_PASSWD_HASH_FILE          pbkdf2_sha512 hash of the master password
#                                   (default /run/secrets/master_password_hash)
#   WORKERS, MAX_CRON_THREADS, LIMIT_MEMORY_SOFT, LIMIT_MEMORY_HARD,
#   LIMIT_TIME_CPU, LIMIT_TIME_REAL optional sizing overrides
set -eu

RC=/etc/afenda/odoo.conf
export RC

die() { echo "afenda-entrypoint: $*" >&2; exit 1; }

if [ -n "${PGDATABASE:-}" ]; then
    die "PGDATABASE must not be set: it overrides db_name in $RC"
fi

if [ -n "${PGPASSWORD_FILE:-}" ]; then
    [ -r "$PGPASSWORD_FILE" ] || die "cannot read PGPASSWORD_FILE $PGPASSWORD_FILE"
    PGPASSWORD=$(cat "$PGPASSWORD_FILE")
    export PGPASSWORD
fi
[ -n "${PGHOST:-}" ] || die "PGHOST is not set"
[ -n "${PGUSER:-}" ] || die "PGUSER is not set"
[ -n "${PGPASSWORD:-}" ] || die "PGPASSWORD (or PGPASSWORD_FILE) is not set"

hash_file=${ADMIN_PASSWD_HASH_FILE:-/run/secrets/master_password_hash}
[ -r "$hash_file" ] || die "cannot read master password hash $hash_file"
admin_passwd=$(cat "$hash_file")
case "$admin_passwd" in
    '$pbkdf2-sha512$'*) ;;
    *) die "$hash_file is not a pbkdf2_sha512 hash; run deploy/make-secrets.sh" ;;
esac

WORKERS=${WORKERS:-4}
MAX_CRON_THREADS=${MAX_CRON_THREADS:-1}
# These cap each worker's ADDRESS SPACE (virtual memory), not its RSS: the
# soft limit is checked against memory_info().vms (odoo/tools/osutil.py) and
# the hard limit is set as RLIMIT_AS on the worker (odoo/service/server.py,
# set_limit_memory_hard). wkhtmltopdf inherits RLIMIT_AS, so a low cap breaks
# PDF printing. Keep the upstream defaults (odoo/tools/config.py); size RAM
# through WORKERS instead.
LIMIT_MEMORY_SOFT=${LIMIT_MEMORY_SOFT:-2147483648}  # 2048 MiB of address space
LIMIT_MEMORY_HARD=${LIMIT_MEMORY_HARD:-2684354560}  # 2560 MiB of address space
# Below nginx's proxy_read_timeout (720s), so the worker gives up first.
LIMIT_TIME_CPU=${LIMIT_TIME_CPU:-300}
LIMIT_TIME_REAL=${LIMIT_TIME_REAL:-600}

umask 077
cat > "$RC" <<EOF
[options]
db_name = afenda
data_dir = /var/lib/afenda
addons_path = /opt/afenda/addons,/opt/afenda/afenda/addons,/opt/afenda/afenda/oca/server-brand,/opt/afenda/afenda/oca/web
admin_passwd = $admin_passwd
list_db = False
proxy_mode = True
http_interface = 0.0.0.0
http_port = 8069
gevent_port = 8072
workers = $WORKERS
max_cron_threads = $MAX_CRON_THREADS
limit_memory_soft = $LIMIT_MEMORY_SOFT
limit_memory_hard = $LIMIT_MEMORY_HARD
limit_time_cpu = $LIMIT_TIME_CPU
limit_time_real = $LIMIT_TIME_REAL
publisher_warranty_url = http://127.0.0.1:9/
log_level = info
EOF
chmod 600 "$RC"

# `python odoo-bin [options]` is the server: append the config. Anything else
# (a subcommand, afenda-init, a shell) runs unchanged and passes -c "$RC"
# itself, because subcommands take -c at different argument positions.
if [ "$#" -ge 2 ] && [ "${2##*/}" = "odoo-bin" ]; then
    case "${3:-}" in
        ''|-*) exec "$@" -c "$RC" ;;
    esac
fi
exec "$@"
