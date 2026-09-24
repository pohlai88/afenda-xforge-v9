# AFENDA xForge G1 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the live ERP as a least-privilege database role, pin every base image by digest, and run the AFENDA Odoo module suites in CI, without an unrecoverable step on the live host.

**Architecture:** A new PostgreSQL role `afenda_app` (no superuser) owns the `afenda` database and every object in it; the app and `init` connect as it, while the bootstrap superuser `xforge` stays for the db container, `backup.sh` and `restore.sh`. Existing hosts move over with `deploy/migrate-db-role.sh` (backup first, idempotent, `--rollback`), rehearsed on a local stack that holds a restored copy of production before the live run. Images are pinned to the multi-arch index digests running today; CI runs the module suites inside the built image against a `postgres:16` service container.

**Tech Stack:** Docker Compose v2 (Compose v5.x on the VPS), PostgreSQL 16, Odoo 19 (`odoo-bin`), GitHub Actions, bash/sh, Python 3.11 unittest.

**Spec:** `docs/superpowers/plans/2026-09-23-afenda-g0-deploy.md` ("Deferred to G1", go-live record, independence audit). Facts established 2026-09-24 on the live host:
- `pg_roles`: `xforge | rolsuper t | rolcreatedb t`; `afenda` is owned by `xforge`; extensions in `afenda`: `plpgsql, pg_trgm`.
- Every service reads `PGUSER: xforge` / `PGPASSWORD_FILE: /run/secrets/db_password` from the `x-xforge-env` anchor (`deploy/compose.yaml:27-31`); `restore.sh:36-37` creates the database with `-O xforge` and restores with `--role=xforge`.
- `odoo-bin db init` refuses an existing database (`odoo/cli/db.py:257-263`) and creates it with `CREATE DATABASE` (`odoo/service/db.py:128-147`), so the app role needs `CREATEDB` for a fresh host.
- Running digests: `postgres@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6`, `nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`; the python base is not cached on the host and is resolved in Task 1.
- AFENDA tests use `HttpCase` but no `start_tour`/`browser_js`, so CI needs no browser. Odoo prints `"{failed} failed, {errors} error(s) of {testsRun} tests"` (`odoo/tests/result.py:198`).

## Global Constraints

- CLAUDE.md "Execution discipline" binds every task: name the cause before a change, narrowest test per edit, full gates once before each commit, never rerun a passing gate, stop after the same fix fails twice.
- Commit with `git commit --only -F msgfile -- <paths>` in one shell call; a NEW executable script is committed from the index after `git add --chmod=+x`, with a guard that the staged set equals the task's file list (memory: git-only-drops-exec-bit).
- `.github/` and `deploy/` are this session's scope; do not touch `afenda/addons/afenda_brand/views`, `afenda_brand/static/src/scss`, `afenda_brand/tests/test_branding.py` or icon tooling (owned by the UI session).
- Live deploys go only through `deploy/redeploy.sh` after a push the user approved. Never `docker compose down -v`. Never touch the older compose project named `afenda` on the workstation.
- Every live step starts with a verified backup and has a written rollback; stop and report if a verification does not print its expected value.
- Secrets are generated on the host and never printed; tests and scripts check them only as booleans.
- Out of scope here (still deferred): the arm64 image and bold non-Latin report fonts; backup pruning and monitoring alerts already shipped in G0.
- The local rehearsal stack holds a restored copy of production data: never publish its volumes, and delete rehearsal backup folders afterwards.
- The new role is named exactly `afenda_app`; its password file is `deploy/secrets/db_app_password`; the Docker secret is `db_app_password`.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `deploy/compose.yaml` | image digests; app role wiring; db init mount | 1, 3 |
| `deploy/Dockerfile` | python base digest | 1 |
| `deploy/README.md` | image update path; role layout; migration and rollback runbook | 1, 3 |
| `.github/workflows/afenda-image.yml` | module suites against a postgres service | 2 |
| `deploy/make-secrets.sh` | also writes `db_app_password` | 3 |
| `deploy/db-init/10-afenda-app-role.sh` (new) | creates `afenda_app` on a fresh db volume | 3 |
| `deploy/migrate-db-role.sh` (new) | moves an existing database to `afenda_app`, or back | 3 |
| `deploy/restore.sh` | creates and restores as `afenda_app` | 3 |
| `afenda/tools/tests/test_deploy_static.py` | pins, role wiring | 1, 3 |
| `afenda/tools/tests/test_deploy_scripts.py` | migrate script argument handling | 3 |
| `docs/superpowers/plans/2026-09-23-afenda-g0-deploy.md` | records the rehearsal and the live run | 4, 5 |

---

### Task 1: Pin every base image by digest

**Files:**
- Modify: `deploy/compose.yaml` (`image: postgres:16`, `image: nginx:1.27-alpine`)
- Modify: `deploy/Dockerfile:13` (`ARG PYTHON_IMAGE=`)
- Modify: `deploy/README.md` (new section "Updating the base images")
- Test: `afenda/tools/tests/test_deploy_static.py`

**Interfaces:**
- Produces: image references of the form `<repo>:<tag>@sha256:<64 hex>`; Task 2 reuses the postgres reference verbatim for its service container.

- [ ] **Step 1: Write the failing test** (add to `DeployStaticTests`)

```python
    def test_every_base_image_is_pinned_by_digest(self):
        # A tag can move under us; a digest cannot. The tag stays for humans.
        pinned = re.compile(r"^[a-z0-9./-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")
        compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
        refs = re.findall(r"^\s+image:\s*(\S+)\s*$", compose, re.MULTILINE)
        refs = [r for r in refs if not r.startswith("${XFORGE_IMAGE")]
        self.assertEqual(len(refs), 2, refs)  # postgres and nginx
        arg = re.search(r"^ARG PYTHON_IMAGE=(\S+)$", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
        self.assertIsNotNone(arg)
        for ref in refs + [arg.group(1)]:
            self.assertRegex(ref, pinned)
```

- [ ] **Step 2: Run it; expect FAIL**

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_deploy_static.DeployStaticTests.test_every_base_image_is_pinned_by_digest`
Expected: `FAIL` on `postgres:16` not matching the pattern.

- [ ] **Step 3: Resolve the python index digest** (multi-arch index, so an arm64 build later still works)

Run: `docker buildx imagetools inspect python:3.11-slim-bookworm --format '{{json .Manifest.Digest}}'`
Expected: `"sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b"` (resolved 2026-09-24; the registry digests of postgres:16 and nginx:1.27-alpine also matched the ones running on the host). If it differs at execution time, use the new value and say so in the commit message.

- [ ] **Step 4: Pin**

```yaml
    image: postgres:16@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6
```
```yaml
    image: nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
```
```dockerfile
ARG PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b
```

- [ ] **Step 5: README section "Updating the base images"**

```markdown
## Updating the base images

Every base image is pinned as `<tag>@sha256:<digest>` (`compose.yaml`,
`Dockerfile` `ARG PYTHON_IMAGE`), so a rebuild never picks up a moved tag.
To take an update, resolve the tag's current index digest, replace it, and
ship it like any change:

    docker buildx imagetools inspect postgres:16 --format '{{json .Manifest.Digest}}'
    docker buildx imagetools inspect nginx:1.27-alpine --format '{{json .Manifest.Digest}}'
    docker buildx imagetools inspect python:3.11-slim-bookworm --format '{{json .Manifest.Digest}}'

Stay on the same postgres major version: a new major needs a dump and restore
(`backup.sh`, then `restore.sh` into a new volume), not a digest bump.
```

- [ ] **Step 6: Run the test file; expect PASS**, then the local build proves the pinned python digest resolves.

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_deploy_static` → `OK`, count printed.
Run: `cd deploy && docker compose build` → ends with `Image afenda/xforge:local Built`.

- [ ] **Step 7: Commit** `[IMP] deploy: pin every base image by digest` with the four paths.

---

### Task 2: Odoo module suites in CI

**Files:**
- Modify: `.github/workflows/afenda-image.yml`

**Interfaces:**
- Consumes: the image built in the same job (`afenda/xforge:ci`); the pinned postgres reference from Task 1.
- Produces: a CI step that fails on any failed/errored Odoo test and on a test count below `ODOO_TESTS_MIN`.

- [ ] **Step 1: Add the postgres service and the suite step** (job `build`)

```yaml
    services:
      postgres:
        image: postgres:16@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6
        env:
          POSTGRES_USER: odoo
          POSTGRES_PASSWORD: odoo
          POSTGRES_DB: postgres
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U odoo -d postgres"
          --health-interval 5s --health-timeout 5s --health-retries 20
    env:
      ODOO_TESTS_MIN: "1"
```

```yaml
      - name: Odoo module suites (afenda_*)
        run: |
          set -o pipefail
          mods=afenda_brand,afenda_runtime,afenda_api_docs,afenda_brand_digest
          docker run --rm --network host --entrypoint /opt/venv/bin/python afenda/xforge:ci \
            /opt/afenda/odoo-bin \
            --db_host 127.0.0.1 --db_port 5432 --db_user odoo --db_password odoo -d ci \
            --addons-path /opt/afenda/addons,/opt/afenda/afenda/addons,/opt/afenda/afenda/oca/server-brand,/opt/afenda/afenda/oca/web \
            --data-dir /tmp/afenda-data -i "$mods" \
            --test-enable --test-tags "/afenda_brand,/afenda_runtime,/afenda_api_docs,/afenda_brand_digest" \
            --stop-after-init --http-port 8069 --workers 0 \
            --log-level warn --log-handler odoo.tests:INFO 2>&1 | tee odoo-tests.log
          line=$(grep -oE '[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests' odoo-tests.log | tail -n 1)
          echo "result: ${line:-none}"
          set -- $(printf '%s' "$line" | grep -oE '[0-9]+')
          [ "$#" -eq 3 ] || { echo "::error::no Odoo test result line"; exit 1; }
          [ "$1" -eq 0 ] && [ "$2" -eq 0 ] || { echo "::error::$line"; exit 1; }
          [ "$3" -ge "$ODOO_TESTS_MIN" ] || { echo "::error::only $3 tests ran (min $ODOO_TESTS_MIN)"; exit 1; }
```

- [ ] **Step 2: Run it once on GitHub** (after the user approves the push): `gh workflow run afenda-image.yml` (keyring login: `env -u GITHUB_TOKEN -u GH_TOKEN`), then `gh run watch <id> --exit-status`.
Expected: `result: 0 failed, 0 error(s) of N tests`. If failures appear, triage each with its traceback (systematic-debugging) before any change; fixes to `afenda_brand` tests go to the UI session that owns them.

- [ ] **Step 3: Set the floor** to the N printed by the green run: `ODOO_TESTS_MIN: "<N>"`; commit `[IMP] ci: run the afenda Odoo module suites in the built image`.

---

### Task 3: The least-privilege role in the repository

**Files:**
- Create: `deploy/db-init/10-afenda-app-role.sh`
- Create: `deploy/migrate-db-role.sh`
- Modify: `deploy/compose.yaml`, `deploy/make-secrets.sh`, `deploy/restore.sh`, `deploy/README.md`
- Test: `afenda/tools/tests/test_deploy_static.py`, `afenda/tools/tests/test_deploy_scripts.py`

**Interfaces:**
- Produces: role `afenda_app` (LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS); secret `db_app_password`; `deploy/migrate-db-role.sh [--rollback] --yes` (exit 0 done, 2 usage); Task 4 and 5 run it.

- [ ] **Step 1: Failing static tests** (add to `DeployStaticTests`)

```python
    def test_app_connects_as_the_least_privilege_role(self):
        compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
        env = re.search(r"^x-xforge-env: &xforge-env\n((?:  .*\n)+)", compose, re.MULTILINE).group(1)
        self.assertIn("PGUSER: afenda_app", env)
        self.assertIn("PGPASSWORD_FILE: /run/secrets/db_app_password", env)
        self.assertIn("./db-init:/docker-entrypoint-initdb.d:ro", compose)
        self.assertRegex(compose, r"db_app_password:\n\s+file: \./secrets/db_app_password")
        # The superuser stays the db container's bootstrap role only.
        self.assertIn("POSTGRES_USER: xforge", compose)

    def test_restore_recreates_objects_as_the_app_role(self):
        text = (DEPLOY / "restore.sh").read_text(encoding="utf-8")
        self.assertIn("createdb -U xforge -O afenda_app afenda", text)
        self.assertIn("--role=afenda_app", text)
```

and in `test_deploy_scripts.py`:

```python
@unittest.skipUnless(BASH, "needs bash")
class MigrateDbRoleTests(unittest.TestCase):
    def test_refuses_without_yes(self):
        for args in ([], ["--rollback"]):
            proc = subprocess.run([BASH, str(DEPLOY / "migrate-db-role.sh"), *args],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 2, (args, proc.stderr))
```

- [ ] **Step 2: Run; expect 3 FAIL** (`-m unittest afenda.tools.tests.test_deploy_static afenda.tools.tests.test_deploy_scripts`).

- [ ] **Step 3: `deploy/db-init/10-afenda-app-role.sh`** (runs once, on an empty volume, as the bootstrap superuser)

```sh
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
```

- [ ] **Step 4: `deploy/migrate-db-role.sh`**

```bash
#!/usr/bin/env bash
# Move the existing afenda database to the least-privilege role afenda_app,
# or back to xforge with --rollback. Backup first; idempotent.
#
#   deploy/migrate-db-role.sh --yes
#   deploy/migrate-db-role.sh --rollback --yes
#
# Tables go before sequences: ALTER TABLE carries the sequences its columns
# own, and ALTER SEQUENCE on such a sequence is refused. Extension members
# (pg_trgm) stay with the superuser. REASSIGN OWNED is not used: it would
# also hand over the postgres and template databases.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"
usage() { echo "usage: $0 [--rollback] --yes" >&2; exit 2; }
target=afenda_app
case "${1:-}" in
    --rollback) target=xforge; shift ;;
esac
[ "${1:-}" = "--yes" ] && [ "$#" -eq 1 ] || usage

./backup.sh "${BACKUP_ROOT:-/var/backups/afenda}"
if [ "$target" = afenda_app ]; then
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U xforge -d postgres <<'SQL'
\set pw `cat /run/secrets/db_app_password`
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'afenda_app') AS create_role \gset
\if :create_role
CREATE ROLE afenda_app LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\endif
ALTER ROLE afenda_app PASSWORD :'pw';
SQL
fi
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U xforge -d afenda -v target="$target" <<'SQL'
SELECT set_config('afenda.target', :'target', false);
ALTER DATABASE afenda OWNER TO :"target";
DO $$
DECLARE r record; t text := current_setting('afenda.target');
BEGIN
  FOR r IN SELECT format('ALTER %s %I.%I OWNER TO %I',
                         CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END,
                         n.nspname, c.relname, t) AS q
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
              AND pg_get_userbyid(c.relowner) <> t
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
  LOOP EXECUTE r.q; END LOOP;
  FOR r IN SELECT format('ALTER SEQUENCE %I.%I OWNER TO %I', n.nspname, c.relname, t) AS q
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'S' AND pg_get_userbyid(c.relowner) <> t
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('e', 'a'))
  LOOP EXECUTE r.q; END LOOP;
  FOR r IN SELECT format('ALTER FUNCTION %s OWNER TO %I', p.oid::regprocedure, t) AS q
             FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND pg_get_userbyid(p.proowner) <> t
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
  LOOP EXECUTE r.q; END LOOP;
END $$;
SELECT count(*) AS not_owned_by_target FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','S')
   AND pg_get_userbyid(c.relowner) <> current_setting('afenda.target')
   AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e');
SQL
echo "migrate-db-role: afenda now owned by $target; redeploy with the matching compose.yaml"
```

- [ ] **Step 5: Wire compose** — `x-xforge-env`: `PGUSER: afenda_app`, `PGPASSWORD_FILE: /run/secrets/db_app_password`; `init` and `xforge` `secrets:` list `db_app_password` instead of `db_password`; `db`: add `db_app_password` to `secrets:` and `- ./db-init:/docker-entrypoint-initdb.d:ro` to `volumes:`; top-level `secrets:` gains `db_app_password: {file: ./secrets/db_app_password}`.

- [ ] **Step 6: `make-secrets.sh`** — after `write_new db_password …` add `write_new db_app_password "$(random)" || true`, and list it in the header comment.

- [ ] **Step 7: `restore.sh:36-37`** — `createdb -U xforge -O afenda_app afenda` and `pg_restore -U xforge -d afenda --no-owner --role=afenda_app`.

- [ ] **Step 8: README** — a "Database roles" paragraph (who uses `xforge`, who uses `afenda_app`, why `CREATEDB` stays: `db init` on a fresh host) and a "Moving an existing host" runbook: `./make-secrets.sh` (adds only `db_app_password`), `./migrate-db-role.sh --yes` (expect `not_owned_by_target = 0`), `./redeploy.sh`; rollback: `./migrate-db-role.sh --rollback --yes`, then `./redeploy.sh <previous commit>`.

- [ ] **Step 9: Run both test files; expect OK** (and `test_every_deploy_script_parses` covers the two new scripts). Commit from the index with `git add --chmod=+x -- deploy/db-init/10-afenda-app-role.sh deploy/migrate-db-role.sh` plus the other paths, guarded: `[IMP] deploy: run the ERP as the least-privilege role afenda_app`.

---

### Task 4: Rehearse on the local stack that holds a restored production copy

**Files:** record only: `docs/superpowers/plans/2026-09-23-afenda-g0-deploy.md`

- [ ] **Step 1:** `cd deploy && ./make-secrets.sh` (expect `wrote db_app_password`, others `keeping existing`); `docker compose -p afenda-deploy -f compose.yaml -f compose.proof.yaml up -d db` (db needs the new secret mounted).
- [ ] **Step 2:** `COMPOSE_FILE="compose.yaml;compose.proof.yaml" COMPOSE_PATH_SEPARATOR=";" BACKUP_ROOT=$TEMP/afenda-g1-rehearsal ./migrate-db-role.sh --yes` (a throwaway folder; delete it after the rehearsal, it holds production data) → expect `not_owned_by_target` `0`.
- [ ] **Step 3:** same files, `docker compose … up -d` → `init` exits 0, `xforge` healthy.
- [ ] **Step 4: Verify, each printed once:**
  - `select rolname, rolsuper from pg_roles where rolname='afenda_app'` → `afenda_app | f`
  - `select distinct usename from pg_stat_activity where datname='afenda' and usename <> 'xforge'` → `afenda_app`
  - `curl localhost:8080/web/health` → `{"status": "pass"}`; `/web/login` 200 with `AFENDA xForge`
  - runtime DDL as the app: `docker compose … run --rm -T init sh -c '/opt/venv/bin/python /opt/afenda/odoo-bin shell -c "$RC" --no-http'` with `env["ir.sequence"].create({"name": "g1-rehearsal", "implementation": "standard"}); env.cr.commit(); print("SEQ OK")` → `SEQ OK`
  - forced upgrade as the app: `… module upgrade -c "$RC" afenda_brand afenda_runtime` → exit 0
  - backup then `restore.sh` into this stack with the same `COMPOSE_FILE` → health passes, objects owned by `afenda_app`
- [ ] **Step 5: Rollback drill:** `./migrate-db-role.sh --rollback --yes` → `not_owned_by_target 0` (now xforge); then forward again → `0`. Record every printed value in the G0 record.

---

### Task 5: Live host

**Precondition:** Tasks 1–4 committed; CI green on the pushed head; the user approved push and this run.

- [ ] **Step 1:** `ssh root@68.183.233.155`; `cd /srv/afenda/deploy && git -C /srv/afenda fetch --depth 1 origin afenda/deidentify-phase1 && git -C /srv/afenda checkout --detach FETCH_HEAD` (so the new scripts exist), then `./make-secrets.sh` → `wrote db_app_password`.
- [ ] **Step 2:** `docker compose up -d db` (mounts the new secret; db restarts in seconds), then `./migrate-db-role.sh --yes` → backup printed, `not_owned_by_target` `0`.
- [ ] **Step 3:** `./redeploy.sh` → `…/web/health passes; now at <head>`.
- [ ] **Step 4: Verify once:** the four checks of Task 4 Step 4 (without the restore), the 17-check proof (`17/17 checks passed`), and a mail test through the Resend server (`mail.mail` state `sent`).
- [ ] **Step 5: Rollback if any check fails:** `./migrate-db-role.sh --rollback --yes`, then `./redeploy.sh <previous head>`; report with the failing output.
- [ ] **Step 6:** record the run in the G0 record and memory; commit `[IMP] docs: record the G1 role migration on the live host`.
