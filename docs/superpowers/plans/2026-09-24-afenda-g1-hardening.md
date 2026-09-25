# AFENDA xForge G1 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the live ERP as a least-privilege database role, pin every base image by digest, and run the AFENDA Odoo module suites in CI, without an unrecoverable step on the live host.

**Architecture:** A new PostgreSQL role `afenda_app` (no superuser) owns the `afenda` database and every object in it; the app and `init` connect as it, while the bootstrap superuser `xforge` stays for the db container, `backup.sh` and `restore.sh`. Existing hosts move over with `deploy/migrate-db-role.sh` (backup first, idempotent, `--rollback`), rehearsed on a local stack that holds a restored copy of production before the live run. Images are pinned to the multi-arch index digests running today; CI runs the module suites inside the built image against a `postgres:16` service container.

**Tech Stack:** Docker Compose v2 (Compose v5.x on the VPS), PostgreSQL 16, Odoo 19 (`odoo-bin`), GitHub Actions, bash/sh, Python 3.11 unittest.

**Spec:** `docs/superpowers/plans/2026-09-23-afenda-g0-deploy.md` (decision R6's deferrals, go-live record, independence audit). Facts established 2026-09-24 on the live host:
- `pg_roles`: `xforge | rolsuper t | rolcreatedb t`; `afenda` is owned by `xforge`; extensions in `afenda`: `plpgsql, pg_trgm`.
- Every service reads `PGUSER: xforge` / `PGPASSWORD_FILE: /run/secrets/db_password` from the `x-xforge-env` anchor (`deploy/compose.yaml:27-31`); `restore.sh:36-37` creates the database with `-O xforge` and restores with `--role=xforge`.
- `odoo-bin db init` refuses an existing database (`odoo/cli/db.py:257-263`) and creates it with `CREATE DATABASE` (`odoo/service/db.py:128-147`), so the app role needs `CREATEDB` for a fresh host.
- Running digests: `postgres@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6`, `nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`; the python base is not cached on the host and is resolved in Task 1.
- AFENDA tests use `HttpCase` but no `start_tour`/`browser_js`, so CI needs no browser. Odoo prints `"{failed} failed, {errors} error(s) of {testsRun} tests"` (`odoo/tests/result.py:198`).

Proven 2026-09-24 against a throwaway `postgres:16` at the pinned digest, with the SQL extracted verbatim from this plan (`g1proof` harness, scratchpad):
- the db-init script creates `afenda_app` with `rolsuper = f`, `rolcreatedb = t`; the migrate role block creates it when absent, is idempotent, and `afenda_app` logs in over TCP with the secret's password;
- as `afenda_app`: `CREATE DATABASE … ENCODING 'unicode' LC_COLLATE 'C' TEMPLATE template0` and `CREATE EXTENSION pg_trgm` (the fresh-host path);
- on an Odoo-like schema (serial table, trigram GIN index, standalone sequence, view, function, `pg_trgm`) owned by `xforge`: forward, rollback, forward and a repeat run each end with `every object in afenda is owned by <target>` in one transaction; afterwards `afenda_app` ran ALTER TABLE, ALTER SEQUENCE, CREATE SEQUENCE, an insert through the serial, a trigram index and CREATE OR REPLACE VIEW;
- `pg_dump -U xforge` then `pg_restore --no-owner --role=afenda_app` into a database owned by `afenda_app`: 0 objects owned by anyone else;
- with another session holding an ACCESS EXCLUSIVE lock, the migration failed after 5 s (`canceling statement due to lock timeout`, exit 3) and rolled back entirely, `ALTER DATABASE` included.

Reviewed 2026-09-24 by an independent read-only agent: 2 blockers (live rollback target and order; CI run on the wrong ref and before its commit), 3 major (migration against a live app without a lock timeout; fresh-host path untested; a check that left a junk record in production), 5 minor; all folded into Tasks 2–5 below.

## Global Constraints

- CLAUDE.md "Execution discipline" binds every task: name the cause before a change, narrowest test per edit, full gates once before each commit, never rerun a passing gate, stop after the same fix fails twice.
- Commit with `git commit --only -F msgfile -- <paths>` in one shell call; a NEW executable script is committed from the index after `git add --chmod=+x`, with a guard that the staged set equals the task's file list (memory: git-only-drops-exec-bit).
- `.github/` and `deploy/` are this session's scope; do not touch `afenda/addons/afenda_brand/views`, `afenda_brand/static/src/scss`, `afenda_brand/tests/test_branding.py` or icon tooling (owned by the UI session).
- Live deploys go only through `deploy/redeploy.sh` after a push the user approved. Never `docker compose down -v`. Never touch the older compose project named `afenda` on the workstation.
- Every live step starts with a verified backup and has a written rollback; stop and report if a verification does not print its expected value.
- Secrets are generated on the host and never printed; tests and scripts check them only as booleans.
- Out of scope here (still deferred): the arm64 image and bold non-Latin report fonts; backup pruning already shipped in G0 (`deploy/prune-backups.sh`); monitoring is
  DigitalOcean's agent, configured outside this repo.
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

### Task 2: Odoo module suites in CI, as a least-privilege role

**Files:**
- Modify: `.github/workflows/afenda-image.yml`
- Test: `afenda/tools/tests/test_deploy_static.py`

**Interfaces:**
- Consumes: the image built in the same job (`afenda/xforge:ci`); the pinned postgres reference from Task 1.
- Produces: a CI step that fails on any failed/errored Odoo test, on a missing result line, and on a count below `ODOO_TESTS_MIN`. It runs as a `NOSUPERUSER CREATEDB` role, so it also proves the fresh-host path: `odoo-bin -d ci -i …` creates the database itself (`odoo/cli/server.py:104`) and runs `CREATE EXTENSION IF NOT EXISTS pg_trgm` (`odoo/service/db.py:152`).

- [ ] **Step 1: Failing test — the workflow's postgres pin must equal compose's** (add to `DeployStaticTests`)

```python
    def test_ci_postgres_matches_the_pinned_compose_image(self):
        compose = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
        pinned = re.search(r"^\s+image:\s*(postgres:\S+)\s*$", compose, re.MULTILINE).group(1)
        workflow = (REPO / ".github" / "workflows" / "afenda-image.yml").read_text(encoding="utf-8")
        used = re.findall(r"^\s+image:\s*(postgres:\S+)\s*$", workflow, re.MULTILINE)
        self.assertEqual(used, [pinned])
```

Run: `.venv/Scripts/python -m unittest afenda.tools.tests.test_deploy_static.DeployStaticTests.test_ci_postgres_matches_the_pinned_compose_image` → expect FAIL (`[] != [...]`).

- [ ] **Step 2: Add the service, the role and the suite step** (job `build`, after "The image is AFENDA xForge")

```yaml
    services:
      postgres:
        image: postgres:16@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6
        env:
          POSTGRES_USER: ci_admin
          POSTGRES_PASSWORD: ci_admin
          POSTGRES_DB: postgres
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U ci_admin -d postgres"
          --health-interval 5s --health-timeout 5s --health-retries 20
    env:
      ODOO_TESTS_MIN: "1"
```

```yaml
      - name: A least-privilege role, as on the VPS
        run: |
          docker run --rm --network host -e PGPASSWORD=ci_admin \
            postgres:16@sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6 \
            psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U ci_admin -d postgres \
            -c "CREATE ROLE afenda_app LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD 'ci'"
      - name: Odoo module suites (afenda_*), as afenda_app
        run: |
          set -o pipefail
          mods=afenda_brand,afenda_runtime,afenda_api_docs,afenda_brand_digest
          docker run --rm --network host --entrypoint /opt/venv/bin/python afenda/xforge:ci \
            /opt/afenda/odoo-bin \
            --db_host 127.0.0.1 --db_port 5432 --db_user afenda_app --db_password ci -d ci \
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

The result line comes from the `odoo.tests.result` logger (`odoo/service/server.py:717-725`), which `--log-handler odoo.tests:INFO` shows; a run with failures also exits non-zero.

- [ ] **Step 3: Gate and commit.** Full tools suite once: `.venv/Scripts/python -m unittest discover afenda/tools/tests` → `OK`, count printed. Commit `[ADD] ci: run the afenda Odoo module suites as a least-privilege role` (workflow + test).

- [ ] **Step 4: First run on the branch** (only after the owner approves the push): push; the `push` trigger runs `afenda-image` because the workflow file is in its `paths`. If a run must be started by hand, pass the branch: `env -u GITHUB_TOKEN -u GH_TOKEN gh workflow run afenda-image.yml --ref afenda/deidentify-phase1`. Watch it with `gh run watch <id> --exit-status`.
Expected: `result: 0 failed, 0 error(s) of N tests`. Failures are triaged one by one with their traceback (superpowers:systematic-debugging) before any change; a fix inside `afenda_brand` tests goes to the UI session that owns them.

- [ ] **Step 5: Set the floor** to the N the green run printed: `ODOO_TESTS_MIN: "<N from Step 4>"`; commit `[IMP] ci: floor the Odoo suite count at the first green run`.

---

### Task 3: The least-privilege role in the repository

**Files:**
- Create: `deploy/db-init/10-afenda-app-role.sh`
- Create: `deploy/migrate-db-role.sh`
- Modify: `deploy/compose.yaml`, `deploy/make-secrets.sh`, `deploy/restore.sh`, `deploy/README.md`
- Test: `afenda/tools/tests/test_deploy_static.py`, `afenda/tools/tests/test_deploy_scripts.py`

**Interfaces:**
- Produces: role `afenda_app` (LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS); secret `db_app_password`; `deploy/migrate-db-role.sh [--rollback] --yes` (exit 0 when every object is owned by the target; non-zero on any failure, psql's 3 for a SQL error such as the lock timeout; 2 usage). Tasks 4 and 5 run it.

- [ ] **Step 1: Failing tests** (add to `DeployStaticTests`)

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
        for args in ([], ["--rollback"], ["--yes", "extra"]):
            proc = subprocess.run([BASH, str(DEPLOY / "migrate-db-role.sh"), *args],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 2, (args, proc.stderr))
```

- [ ] **Step 2: Run the two files; expect 3 FAIL** (`.venv/Scripts/python -m unittest afenda.tools.tests.test_deploy_static afenda.tools.tests.test_deploy_scripts`).

- [ ] **Step 3: `deploy/db-init/10-afenda-app-role.sh`** (runs once, on an empty volume, as the bootstrap superuser; the image skips init scripts when `PG_VERSION` exists)

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
# or back to xforge with --rollback. Backup first; idempotent; the app is
# stopped while ownership moves, so no request or cron creates an object
# under the old owner mid-way.
#
#   deploy/migrate-db-role.sh --yes
#   deploy/migrate-db-role.sh --rollback --yes
#
# Tables go before sequences: ALTER TABLE carries the sequences and indexes
# its columns own, and ALTER SEQUENCE on such a sequence is refused.
# Extension members (pg_trgm) stay with the superuser. REASSIGN OWNED is not
# used: it would also hand over the postgres and template databases. The
# ownership change is one transaction with a 5 s lock timeout, and it raises
# unless every object ends up owned by the target.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"
usage() { echo "usage: $0 [--rollback] --yes" >&2; exit 2; }
target=afenda_app
if [ "${1:-}" = "--rollback" ]; then target=xforge; shift; fi
[ "$#" -eq 1 ] && [ "$1" = "--yes" ] || usage

docker compose exec -T db test -s /run/secrets/db_app_password \
    || { echo "migrate-db-role: the db container has no db_app_password secret; run make-secrets.sh and 'docker compose up -d db' first" >&2; exit 1; }

./backup.sh "${BACKUP_ROOT:-/var/backups/afenda}"

restart_xforge() {
    docker compose start xforge >/dev/null
    docker compose exec -T nginx nginx -s reload || true
}
docker compose stop xforge
trap restart_xforge EXIT

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
docker compose exec -T db psql -1 -v ON_ERROR_STOP=1 -U xforge -d afenda -v target="$target" <<'SQL'
SET LOCAL lock_timeout = '5s';
SELECT set_config('afenda.target', :'target', true);
ALTER DATABASE afenda OWNER TO :"target";
DO $$
DECLARE r record; t text := current_setting('afenda.target'); left_over int;
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
  SELECT count(*) INTO left_over FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
     AND pg_get_userbyid(c.relowner) <> t
     AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e');
  IF left_over > 0 THEN
    RAISE EXCEPTION 'migrate-db-role: % objects are not owned by %', left_over, t;
  END IF;
  RAISE NOTICE 'migrate-db-role: every object in afenda is owned by %', t;
END $$;
SQL
echo "migrate-db-role: afenda now owned by $target"
```

- [ ] **Step 5: Wire compose** — `x-xforge-env`: `PGUSER: afenda_app`, `PGPASSWORD_FILE: /run/secrets/db_app_password`; `init` and `xforge` `secrets:` list `db_app_password` instead of `db_password`; `db`: add `db_app_password` to `secrets:` and `- ./db-init:/docker-entrypoint-initdb.d:ro` to `volumes:`; top-level `secrets:` gains:

```yaml
  db_app_password:
    file: ./secrets/db_app_password
```

- [ ] **Step 6: `make-secrets.sh`** — after `write_new db_password "$(random)" || true` add `write_new db_app_password "$(random)" || true`, and list `db_app_password` in the header comment ("PostgreSQL password of the afenda_app role the app connects as").

- [ ] **Step 7: `restore.sh:36-37`** — `createdb -U xforge -O afenda_app afenda` and `pg_restore -U xforge -d afenda --no-owner --role=afenda_app`.

- [ ] **Step 8: README** — a "Database roles" paragraph (`xforge`: the db container's bootstrap superuser, used by `backup.sh`, `restore.sh` and `migrate-db-role.sh`; `afenda_app`: what `init` and the server connect as, owner of `afenda` and every object in it; `CREATEDB` stays because a fresh host's first `init` creates the database) and a "Moving an existing host" runbook: record `prev=$(git -C /srv/afenda rev-parse HEAD)`; check out the new commit; `./make-secrets.sh` (adds only `db_app_password`); `docker compose up -d db`; `./migrate-db-role.sh --yes` (ends `every object in afenda is owned by afenda_app`); `./redeploy.sh`. Rollback: `./redeploy.sh "$prev"` only — the app goes back to connecting as the superuser `xforge`, which can use every object whatever its owner, so ownership stays with `afenda_app`.

- [ ] **Step 9: Gate and commit.** Full tools suite once: `.venv/Scripts/python -m unittest discover afenda/tools/tests` → `OK` with the count (includes `test_every_deploy_script_parses` over the two new scripts). Commit from the index, guarded: `git add --chmod=+x -- deploy/db-init/10-afenda-app-role.sh deploy/migrate-db-role.sh`, `git add` the other paths, compare `git diff --cached --name-only` with the file list, then `git commit -F msg` — `[IMP] deploy: run the ERP as the least-privilege role afenda_app`.

---

### Task 4: Rehearse on the local stack that holds a restored production copy

**Files:** record only: `docs/superpowers/plans/2026-09-23-afenda-g0-deploy.md`

All commands run in Git Bash from `deploy/` with the local stack's own files:

```bash
export MSYS_NO_PATHCONV=1 COMPOSE_FILE="compose.yaml;compose.proof.yaml" COMPOSE_PATH_SEPARATOR=";"
export BACKUP_ROOT="$TEMP/afenda-g1-rehearsal"   # holds production data: delete it at the end
```

- [ ] **Step 1: Baseline.** Save the compose file from before Task 3 for the rollback rehearsal: `t3=$(git log --format=%H -1 --grep='run the ERP as the least-privilege role afenda_app'); mkdir -p "$BACKUP_ROOT"; git show "$t3^:deploy/compose.yaml" > "$BACKUP_ROOT.compose.prev.yaml"`. Then `docker compose build` (the image now carries Tasks 1–3), `./make-secrets.sh` (expect `wrote db_app_password`, the rest `keeping existing`), `docker compose up -d db`.
- [ ] **Step 2: Migrate.** `./migrate-db-role.sh --yes` → backup printed, then `NOTICE: migrate-db-role: every object in afenda is owned by afenda_app`, exit 0.
- [ ] **Step 3: Start as the app role.** `docker compose up -d` → `init` exited 0, `xforge` healthy.
- [ ] **Step 4: Verify, each printed once:**

```bash
q() { docker compose exec -T db psql -X -tA -U xforge -d "$1" -c "$2"; }
q postgres "select rolname||' super='||rolsuper from pg_roles where rolname='afenda_app'"            # afenda_app super=f
q afenda   "select string_agg(distinct usename, ',') from pg_stat_activity where datname='afenda' and usename <> 'xforge'"   # afenda_app
q afenda   "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p','v','m','S') and pg_get_userbyid(c.relowner)<>'afenda_app' and not exists (select 1 from pg_depend d where d.objid=c.oid and d.deptype='e')"   # 0
curl -s http://localhost:8080/web/health                                                          # {"status": "pass"}
curl -s http://localhost:8080/web/login | grep -c "AFENDA xForge"                                 # >= 1
docker compose run --rm -T init sh -c '/opt/venv/bin/python /opt/afenda/odoo-bin shell -c "$RC" --no-http' <<'PY'
env["ir.sequence"].create({"name": "g1-check", "implementation": "standard"})
env.cr.execute("SELECT current_user")
print("SEQ OK as", env.cr.fetchone()[0])
env.cr.rollback()
PY
# SEQ OK as afenda_app   (DDL rolled back: nothing is left behind)
docker compose run --rm -T init sh -c '/opt/venv/bin/python /opt/afenda/odoo-bin module upgrade -c "$RC" afenda_brand afenda_runtime'   # exit 0
```

- [ ] **Step 5: Restore as the app role.** `./backup.sh "$BACKUP_ROOT"`; `./restore.sh "$BACKUP_ROOT/$(ls -1 "$BACKUP_ROOT" | tail -n 1)" --yes`; repeat the ownership query (0) and `/web/health` (pass).
- [ ] **Step 6: Rehearse the live rollback.** Bring the stack up with the previous compose file (app connects as `xforge` again, ownership unchanged): `docker compose -f "$BACKUP_ROOT.compose.prev.yaml" -f compose.proof.yaml up -d` → `init` exited 0, `/web/health` pass, and `pg_stat_activity` shows `xforge`. Then forward again with `docker compose up -d` (the new files) → `afenda_app` in `pg_stat_activity`, health pass.
- [ ] **Step 7:** Record every printed value in the G0 record; `rm -rf "$BACKUP_ROOT" "$BACKUP_ROOT.compose.prev.yaml"`; commit `[IMP] docs: record the G1 role rehearsal`.

---

### Task 5: Live host

**Precondition:** Tasks 1–4 committed; CI green on the pushed head; the owner approved the push and this run.

Run every command below from `/srv/afenda/deploy` (`ssh root@68.183.233.155`, `cd /srv/afenda/deploy`).

- [ ] **Step 1: Record the rollback target and the pinned commit.** `prev=$(git -C /srv/afenda rev-parse HEAD); echo "$prev"` — write it into the ledger before anything else. Also record `new=<the SHA the green CI run tested>`: Step 4 deploys exactly this commit, not the branch head, so a push by another session between this step and Step 4 cannot ship an untested commit. (`redeploy.sh`'s own `fail()` message names `$before`, which by the time Step 4 can print it is already `$new` — ignore it and use `$prev` from this step for any rollback.)
- [ ] **Step 2: Hold the backup cron, fetch the pinned commit, build now.** Confirm the wall clock is clear of 02:40 UTC (the daily backup cron runs `backup.sh`, which stops/starts `xforge` with its own trap and has no lock against this run), then hold that line for the window: `crontab -l | sed 's|^\(40 2 .*backup.sh.*\)$|# \1|' | crontab -`. Then pin and fetch the recorded commit — not the branch head — and build immediately, before migrating: `git -C /srv/afenda fetch --depth 1 origin "$new" && git -C /srv/afenda checkout --detach FETCH_HEAD && git -C /srv/afenda submodule update --init --depth 1`, then `./make-secrets.sh` → `wrote db_app_password`, the rest `keeping existing`, then `docker compose build`. Building here means Step 4's own `docker compose build` hits the cache, which shrinks Step 3's superuser window to minutes instead of a full build.
- [ ] **Step 3: Migrate.** `docker compose up -d db` (recreates only `db` with the new secret and init mount; the named volume stays, and init scripts are skipped on an existing volume), then `./migrate-db-role.sh --yes` → backup printed, `every object in afenda is owned by afenda_app`, exit 0. The app is stopped during the SQL; `migrate-db-role.sh`'s own trap restarts it immediately afterwards, still connecting as `xforge`, and it keeps running — as the superuser — through Step 4's backup and (now cached) image build. Anything it creates in that window, for example an `ir.sequence` for a new journal or date range, is owned by `xforge`; Step 5's ownership query catches this.
- [ ] **Step 4: Redeploy the pinned commit.** `./redeploy.sh "$new"` → `…/web/health passes; now at <new head>`. Passing `"$new"` (never bare) redeploys exactly the commit Step 1 recorded even if the branch head moved since.
- [ ] **Step 5: Verify once** (the same commands as Task 4 Step 4, against the live stack): `afenda_app super=f`; `pg_stat_activity` shows `afenda_app`; the ownership query (`select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p','v','m','S') and pg_get_userbyid(c.relowner)<>'afenda_app' and not exists (select 1 from pg_depend d where d.objid=c.oid and d.deptype='e')`) prints `0` — a non-zero count here is the Step 3 window catching up, not a failure: run `./migrate-db-role.sh --yes` once more (idempotent) and re-check before treating it as anything else; `/web/health` pass; `SEQ OK as afenda_app` with the rollback; then the 17-check proof prints `17/17 checks passed`, and the `ir_mail_server` row still reads `Resend | t | 2587 | starttls_strict`.
- [ ] **Step 6: Restore the backup cron line.** `crontab -l | sed 's|^# \(40 2 .*backup.sh.*\)$|\1|' | crontab -`, then confirm it took: `crontab -l | grep backup.sh`. Do this regardless of Step 5's outcome.
- [ ] **Step 7: If any check in Step 5 fails for a reason other than the ownership count** (Step 5 already retries that one): `./redeploy.sh "$prev"` only — the app reconnects as the superuser `xforge`, which can use every object whatever its owner, so ownership stays with `afenda_app` and nothing further needs to move. Note that this rebuilds the image from `$prev` (older than what Step 2 just built and cached, so its layers are not the ones sitting in the build cache — expect the build alone to take ~10+ minutes) while the app keeps running as it was; the database stays at `afenda_runtime` 19.0.1.2.0 throughout, which is fine for the old code because `module upgrade --outdated` only upgrades a module when the disk version is newer than the one the database recorded. Report with the failing output; do not retry a variation (CLAUDE.md: stop after the same fix fails twice).
- [ ] **Step 8:** Record the run in the G0 record and memory; commit `[IMP] docs: record the G1 role migration on the live host`.
