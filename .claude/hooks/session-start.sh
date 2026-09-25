#!/bin/bash
# SessionStart hook for Claude Code on the web: make the tools suite, ruff and
# the Odoo module suites runnable in a fresh Linux container.
#
# Mirrors the local setup in afenda/README.md, with two Linux adjustments:
# - the venv's interpreter is .venv/bin/python; a .venv/Scripts -> bin link
#   keeps the Windows-style commands in CLAUDE.md working verbatim;
# - PostgreSQL runs as a dedicated cluster on 127.0.0.1:5444 with a
#   passwordless `odoo` superuser, which is what afenda/odoo.conf expects.
#
# Idempotent: every step checks before it acts, so a resumed or cached
# container only pays for what is missing. The database itself is not
# created here; the "first run" command in CLAUDE.md does that once.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

# 1. Headers psycopg2 and python-ldap compile against (no wheels for 3.11 pins).
need=()
for pkg in libpq-dev libldap2-dev libsasl2-dev; do
  dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg")
done
if [ ${#need[@]} -gt 0 ]; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}" >/dev/null
fi

# 2. OCA addons on the addons_path.
git submodule update --init --depth 1

# 3. Python 3.11 venv with the server, tools and linter requirements.
if [ ! -x .venv/bin/python ]; then
  python3.11 -m venv .venv
fi
[ -e .venv/Scripts ] || ln -s bin .venv/Scripts
.venv/bin/python -m pip install -q --disable-pip-version-check \
  -r requirements.txt \
  -r afenda/tools/requirements.txt \
  -r afenda/tools/requirements-icons.txt \
  "ruff>=0.16.1"

# 4. PostgreSQL cluster on 5444 with the passwordless `odoo` superuser.
pg_ver=$(ls /usr/lib/postgresql | sort -n | tail -1)
if ! pg_lsclusters -h | awk '{print $2}' | grep -qx afenda; then
  pg_createcluster "$pg_ver" afenda -p 5444 >/dev/null
  hba="/etc/postgresql/$pg_ver/afenda/pg_hba.conf"
  # Local dev container only: trust loopback, as afenda/odoo.conf has no password.
  sed -i -E 's/^(host\s+all\s+all\s+(127\.0\.0\.1\/32|::1\/128)\s+)\S+/\1trust/' "$hba"
fi
if ! pg_lsclusters -h | awk '$2 == "afenda" {print $4}' | grep -qx online; then
  pg_ctlcluster "$pg_ver" afenda start
fi
if ! su postgres -c "psql -p 5444 -tAc \"SELECT 1 FROM pg_roles WHERE rolname='odoo'\"" | grep -qx 1; then
  su postgres -c "createuser -p 5444 -s odoo"
fi
