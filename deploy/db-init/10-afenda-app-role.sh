#!/bin/sh
# Create the role the app connects as. Runs from /docker-entrypoint-initdb.d
# on the first start of an empty volume only; existing hosts use
# deploy/migrate-db-role.sh. The password comes from the Docker secret and
# never appears in a process argument.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\set pw `cat /run/secrets/db_app_password`
CREATE ROLE afenda_app LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'pw';
SQL
