#!/bin/sh
# One-shot initialisation, run by the `init` compose service through the
# entrypoint (which renders $RC). Safe to rerun on every `compose up`:
#
#   1. `db init` only when the database does not exist yet. `db init` sets the
#      admin login's password from a secret (--password); `-i` would leave it
#      at admin/admin. An existing, initialised database is left untouched.
#      An existing database that is NOT initialised stops the run: dropping it
#      is a decision for an operator, never for a restart.
#   2. `module install` for the product modules. For a module that is already
#      installed this changes nothing: button_install only moves modules in
#      state 'uninstalled' (odoo/addons/base/models/ir_module.py _state_update),
#      so the reload that follows has nothing to install.
#   3. On a database that was already initialised, `module upgrade --outdated`
#      for the same modules, so a new module version (a bumped manifest
#      `version`) applies on redeploy. --outdated upgrades only a module whose
#      version on disk is newer than the one recorded in the database
#      (odoo/cli/module.py _upgrade); an unchanged version is left alone, so a
#      plain restart does not reload module data.
#   4. The system parameters, from init_params.py through `odoo-bin shell`.
set -eu

PY=/opt/venv/bin/python
BIN=/opt/afenda/odoo-bin
DB=afenda
MODULES="afenda_brand afenda_runtime afenda_api_docs"
: "${RC:?RC is exported by afenda-entrypoint}"
PUBLIC_URL=${PUBLIC_URL:-http://localhost:8080}
export PUBLIC_URL

# absent | initialised | uninitialised. psycopg2 takes the connection from
# PGHOST/PGUSER/PGPASSWORD, exactly as the server does.
state=$("$PY" - "$DB" <<'PYEOF'
import sys
import psycopg2

name = sys.argv[1]
conn = psycopg2.connect(dbname="postgres")
try:
    with conn.cursor() as cr:
        cr.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        exists = cr.fetchone() is not None
finally:
    conn.close()
if not exists:
    print("absent")
    sys.exit(0)
conn = psycopg2.connect(dbname=name)
try:
    with conn.cursor() as cr:
        cr.execute("SELECT to_regclass('public.ir_module_module') IS NOT NULL")
        has_table = cr.fetchone()[0]
        installed = False
        if has_table:
            cr.execute("SELECT state FROM ir_module_module WHERE name = 'base'")
            row = cr.fetchone()
            installed = bool(row) and row[0] == "installed"
finally:
    conn.close()
print("initialised" if installed else "uninitialised")
PYEOF
)

case "$state" in
    absent)
        admin_password_file=${ADMIN_PASSWORD_FILE:-/run/secrets/admin_password}
        [ -r "$admin_password_file" ] || { echo "afenda-init: cannot read $admin_password_file" >&2; exit 1; }
        # Empty is not a password: `db init --password ''` stores a hash of the
        # empty string, and _check_credentials rejects an empty submitted
        # password outright (odoo/addons/base/models/res_users.py:350), so the
        # admin account would be unusable until someone reset it. The file is
        # also deliberately emptied once spent (deploy/secrets/README.md), so an
        # empty one here means a first init without a fresh secret.
        [ -s "$admin_password_file" ] || { echo "afenda-init: $admin_password_file is empty; run deploy/make-secrets.sh before a first init" >&2; exit 1; }
        echo "afenda-init: creating database $DB"
        "$PY" "$BIN" db -c "$RC" init "$DB" --password "$(cat "$admin_password_file")"
        ;;
    initialised)
        echo "afenda-init: database $DB already initialised, skipping db init"
        ;;
    uninitialised)
        echo "afenda-init: database $DB exists but is not initialised (no installed 'base')." >&2
        echo "afenda-init: drop it or restore a backup (deploy/restore.sh); refusing to guess." >&2
        exit 1
        ;;
    *)
        echo "afenda-init: could not determine the state of database $DB: '$state'" >&2
        exit 1
        ;;
esac

echo "afenda-init: installing $MODULES"
# shellcheck disable=SC2086
"$PY" "$BIN" module install -c "$RC" $MODULES

if [ "$state" = initialised ]; then
    echo "afenda-init: upgrading any of $MODULES whose version is newer on disk"
    # shellcheck disable=SC2086
    "$PY" "$BIN" module upgrade --outdated -c "$RC" $MODULES
fi

echo "afenda-init: setting system parameters (web.base.url=$PUBLIC_URL)"
AFENDA_REQUIRED_MODULES="$MODULES" "$PY" "$BIN" shell -c "$RC" --no-http \
    < /usr/local/lib/afenda/init_params.py

echo "afenda-init: done"
