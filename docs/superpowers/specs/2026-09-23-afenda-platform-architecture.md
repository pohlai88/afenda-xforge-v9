# AFENDA xForge — platform architecture and constraint-breaking strategy

Date: 2026-09-23. Status: **design, not yet approved for implementation.**
Scope: how AFENDA xForge deploys, and how it stops being "an Odoo installation".

## Doctrine

> **AFENDA owns truth. Odoo provides mechanisms.**

| AFENDA owns | Currently Odoo |
|---|---|
| Tenant identity · release identity · deployment truth | ORM implementation |
| Backup truth · audit truth | UI implementation |
| API contracts · job identity | Accounting / inventory engines |
| Storage abstraction | Module loader |

The word *currently* is the strategic content of that table. The goal is not to escape
Odoo — it is to make Odoo **replaceable at AFENDA boundaries where replacement might
someday matter**. Odoo becomes the ERP kernel, not the whole platform.

As one engineering law:

> AFENDA may depend on an Odoo mechanism. AFENDA **business semantics** must not depend
> directly on that mechanism when a stable AFENDA boundary is practical.

```
business modules → AFENDA Storage Interface → ir.attachment
business workflow → AFENDA Job Kernel       → ir.cron
clients → AFENDA API Contract → AFENDA Application Service → Odoo ORM
```

never the reverse direction, where a business module reaches into `ir.attachment` internals.

## The two constraints

1. **Deployment** — stateful filesystem, PostgreSQL, persistent HTTP/gevent workers and
   cron processes make xForge unsuitable for serverless hosting.
2. **Fork** — 23,291 modified files make AFENDA expensive to merge, audit and release.

**The second is strategically more important**, and it is the one to attack after G0
production is boring.

## What is genuinely immovable (verified in this tree)

1. **PostgreSQL specifically.** The ORM emits PG-specific SQL throughout and
   `_create_empty_database` needs `CREATE DATABASE … TEMPLATE template0` with
   `LC_COLLATE 'C'`. You can change *where* PG runs, not *that* it is PG.
2. **A long-lived process with an in-memory registry.** Odoo builds and caches a
   per-process `Registry` — seconds of work. *This*, not the filestore, is what makes
   serverless-function hosting impossible.
3. **One writable primary.** A read-replica pool exists (`db_replica_host`); writes go to
   one place.
4. **`workers` must never be 1.** `odoo/addons/base/models/ir_actions_report.py:119-122` —
   `if config['workers'] == 1: state = 'workers'`, which **disables PDF printing
   entirely**. Use `0` or `>= 2`. A landmine for any autoscaler that can scale to 1.

Everything else below is a default with a seam.

## The seams, each verified

| Constraint | Seam | Verified at |
|---|---|---|
| Local filestore | `_storage()` is a config-param read; `_file_read` / `_file_write` / `_file_delete` are overridable; `db_datas` column supports DB storage natively | `ir_attachment.py:88,147,158,173,325,473` |
| Filesystem sessions | `FilesystemSessionStore` class; all use via the `root.session_store` singleton | `http.py:995,1815,2176` |
| `wkhtmltopdf` binary | `_run_wkhtmltopdf` and `_render_qweb_pdf` are ordinary overridable methods | `ir_actions_report.py:515,1036` |
| Odoo internals as the API | `/json/2/<model>/<method>`, bearer auth, `readonly` per method | `addons/rpc/controllers/json2.py:38,49` |
| Per-process connection pool | `db_maxconn` is **per process**, not per server | `sql_db.py:823` |

Setting `ir_attachment.location = 'db'` makes Odoo stateless on disk **today, with zero
code** — at the cost of carrying every attachment in the database. Useful as a
measurement, not as the destination.

## Do NOT break the monolith

A tempting and wrong move: "Odoo is monolithic, therefore microservices." Accounting
transactions, inventory reservations, invoices, payments and payroll benefit from being in
one database and one ORM transaction. Splitting them prematurely buys distributed
transactions, eventual consistency, retries, duplicate processing and schema-ownership
fights, for no benefit at this scale.

> **Break infrastructure coupling first. Keep transactional business coupling intact.**

## Six generations

| Gen | Architecture | Unlocks |
|---|---|---|
| **G0 — now** | One VM, Compose, PostgreSQL, local filestore | Production, safely |
| **G1** | Immutable CI-built runtime, external backup, restore rehearsal | Reproducibility |
| **G2** | Object-store attachments **and** an external session store; cron split out | **Truly** stateless app tier |
| **G3** | N xForge replicas, external PostgreSQL, role-specific connection budgets | Horizontal scale |
| **G4** | Tenant control plane and tenant registry | Real SaaS operations |
| **G5** | Upstream + semantic patch ledger + generated distribution | Breaks fork maintenance |
| **G6** | Stable AFENDA APIs and events, selective extraction | Odoo becomes interchangeable |

**Do not jump G0 → G6.** Make each generation operationally boring before proceeding.

### G2 detail — state externalization, then one role split

**Attachments alone do not make the tier stateless.** Sessions are the second filesystem
dependency (`FilesystemSessionStore`, `http.py:995`), and a container holding local session
files is still stateful. G2 is not done until both have left the disk:

```
Attachments   local filestore  → AFENDA Storage Interface → S3-compatible
Sessions      FilesystemStore  → AFENDA Session Interface → Redis (one implementation)
Cron          inside web       → its own service
```

The acceptance test for G2, and it should be automated:

> **Destroying an xForge container destroys zero durable business state.**

Note the *interface* is what belongs to G2; Redis is merely the first implementation, so
G3 is defined by replicas and connection budgets rather than by a cache product.

Only two roles at G2, not three:

```
AFENDA-WEB    workers = N, max_cron_threads = 0
              (the gevent/websocket worker is spawned automatically — see below)
AFENDA-CRON   http_enable = False, workers = 0, max_cron_threads >= 1
```

**Do not split the websocket worker out at G2.** `PreforkServer` spawns the gevent child
itself and respawns it if it dies, so a separate role would either duplicate it or fight it
for the port. Splitting it is a G3/G4 move, justified by measured websocket load — not by
the fact that an internal `gevent` command exists. Break one coupling at a time.

Two traps that must be designed around, both verified:

- **Cron runs on *every available database*** when no `--database` is given
  (`odoo/service/server.py:99-100`, `cron_database_list`). A dedicated cron role without
  `db_name` set will fan out across every tenant. Worse, `list_dbs` only returns databases
  **owned by the connecting role** (`odoo/service/db.py:454`), so with databases owned
  elsewhere the list is empty and **cron silently runs nowhere**.
- **Correction to an earlier claim in this document:** I previously wrote that exactly one
  cron role may exist because N instances would mean N× every job. **That is wrong.** Odoo
  coordinates concurrent cron workers through PostgreSQL row locking —
  `ir_cron._acquire_one_job` selects `FOR NO KEY UPDATE SKIP LOCKED`
  (`odoo/addons/base/models/ir_cron.py:365`), and the comment at `:330-332` is explicit:
  "each worker just acquire one available job at a time and lock it so the other workers
  don't select it too." So redundant cron workers are *supported*.
  The doctrine is therefore operational, not correctness-driven: **run one cron service
  initially for simplicity, and add redundancy when HA justifies it.** Cron is closer to
  horizontally scalable than this document first claimed.

### G3 detail — connection math before you choose a managed PG

`db_maxconn` is a per-process pool (`sql_db.py:823`), and the gevent process has **its own**
(`db_maxconn_gevent`, `tools/config.py:395`; `sql_db.py:823` selects it when `odoo.evented`).
So the ceiling is 10 processes, not 9: 8 HTTP + 1 cron + 1 gevent at the default 64 is
**640 potential connections** against a typical `max_connections = 100`. Plan against the
ceiling, not observed utilisation, and budget per role rather than globally —
web ~8, cron ~4, gevent ~4, then measure. At four web replicas that is roughly
`4 × 8 + 4 + 4 × 4 ≈ 52` planned, which makes PostgreSQL sizing intentional instead of
accidental. And
**PgBouncer transaction mode will break Odoo** — it relies on session-scoped state (`SET`,
advisory locks, server-side cursors). Session mode only, which removes much of the benefit
people expect from serverless PG.

## AFENDA Jobs — abstract, don't rip out

Do not remove `ir.cron`. Introduce an AFENDA job kernel with first-class concepts — Job,
Trigger, Attempt, Lease, Execution, Retry, Dead Letter, Idempotency Key, Tenant,
Correlation ID — and back it with `ir.cron` initially:

```
AFENDA Job Kernel → ir.cron        (today)
AFENDA Job Kernel → PG queue       (later)
AFENDA Job Kernel → Temporal/MQ    (only if genuinely needed)
```

Business modules call `job.enqueue(...)`, never `self.env["ir.cron"]`. That removes the
architectural dependency without a big-bang migration.

## Tenant control plane — and a correction to earlier advice

Odoo's `dbfilter = ^%d$` maps a subdomain to a database, and `db_filter` derives the label
from `host.partition('.')[0]` (`odoo/http.py:402-418`). Useful. **Not sufficient to build a
SaaS on.**

⚠️ **This supersedes my earlier recommendation.** I previously advised "database name ==
subdomain label". That is wrong as a long-term rule — it welds routing to naming. The
hostname should resolve to a **tenant identity**, which then resolves to routing metadata:

```
acme.afenda.com → tenant=acme → db=afenda_t_01948, cluster=pg-sg-01,
                                storage=tenants/01948/, release=19.0.1.4
```

A separate control-plane application (not ERP — it *controls* ERP instances) owns a tenant
registry: `id, slug, domain, database_name, database_cluster, storage_namespace, region,
release_channel, xforge_version, status, backup_policy, encryption_key_ref`, plus tenant
lifecycle, database provisioning/backup/restore/clone, runtime version and rollback,
hostname and TLS, release compatibility, and an immutable audit history.

Provisioning becomes `CREATE TENANT` rather than someone SSH-ing into a server.

## Breaking the fork constraint — three layers

The measurement that makes this tractable: the core delta is **100% generator output and
converged** (`python -m afenda.tools.rebrand` reports `0 total (would apply)`), and it is
almost entirely text. `odoo/orm/models.py` is **5 docstring lines**;
`odoo/service/server.py` is **1 comment**; `odoo/http.py` is 26 lines of which **2 are
behavioural** (`/odoo/` → `/app/`, from `url_prefix` at `afenda/tools/rules.py:53-61`).
119 files are hand-authored; 23,172 are generated; 90% of the delta is `.po`/`.pot`.

So the fork is a **derived artifact stored as if it were source**. Separate the layers:

```
Layer 1  ODOO UPSTREAM            pristine
Layer 2  AFENDA SEMANTIC PATCHES  small, deliberate, each with an identity
Layer 3  AFENDA IDENTITY TRANSFORM deterministic generation
```

and build:

```
upstream SHA → semantic patches → identity compiler → corpus verify
             → identity scan → AFENDA runtime tree → OCI image digest
```

**Two metrics, never combined.** Reporting one number hides the whole insight:

```
AUTHORED DELTA   what humans deliberately changed        ~119 files, 2 behavioural
DERIVED DELTA    what the AFENDA compiler generated      ~23,172 files
```

23,291 is not AFENDA's source complexity. It is AFENDA's **distribution footprint**.

The 23,000-file tree becomes a **build artifact**, not the source of truth. Branch topology:

```
upstream-19.0    pristine snapshot, real ancestry. Never edited.
     |
afenda-src       + the 119 hand-authored files. ALL human work happens here.
     |
19.0-src         + the 119 hand-authored files. APPEND ONLY.
     |
19.0-dist        + generated release snapshots, one commit per release. APPEND ONLY.
                 Tagged xforge-v19.0.1.0.4, .5, .6 …
```

⚠️ **Revised: do not force-push the generated branch.** My first draft had `19.0` reset and
force-pushed each release, with tags as the durable artifact. That works technically and
contradicts the thing this platform is being built around — *the system never forgets*. A
source-control design that deliberately rewrites published history is the wrong foundation
for a product whose selling point is kept truth. Both branches are append-only instead.

Better still, the generated tree need not live in git at all. CI can emit a release bundle
and bind its parts cryptographically:

```yaml
release:              xforge-v19.0.1.0.5
upstream_sha:         2d1b7a131…
afenda_source_sha:    84fd3…
transform_rules_sha:  ce17a…
generated_tree_sha256: …
oci_digest:           sha256:…
test_evidence_sha256: …
```

That is a traceable product derivation rather than a branch trick, and it is what makes the
provenance seam below answerable.

**Upstream merges then touch 119 files instead of 23,291**, because nothing generated is
ever merged — it is re-derived. The `.po` conflict profile that makes the current cadence
unsurvivable (20,965 translation files, entries reordering, `#:` comments shifting) never
arises. `afenda/tools/corpus.py` plus its golden file already reviews a rule change as a
diff of distinct rewrites rather than 19,000 modified files — the right primitive, already
built.

### Patch ledger

Every intentional deviation from upstream gets an identity:

```yaml
AFD-PATCH-HTTP-001:
  upstream: { file: odoo/http.py, sha: ... }
  reason: "AFENDA URL prefix /odoo/ -> /app/"
  owner: platform-runtime
  tests: [HTTP-017]
  introduced: 19.0.1
  status: active
```

### Upstream delta budget — a release KPI

```
Upstream commit:                 abc123
Changed semantic core files:     17
Patched framework LOC:           +821 / -314
Generated identity files:        23,102
AFENDA-only addons:              3
Unresolved upstream conflicts:   0
Forbidden identity occurrences:  10,838 baseline, delta 0
Patch test coverage:             100%
```

Far more meaningful than "our fork changes 23,291 files."

### ⚠️ Blocker: the documented upstream step cannot run today

Verified first-hand:

```
.git/shallow contains              2d1b7a131…
root commit == upstream-19.0 ==    19ebd007c
git merge-base upstream/19.0 HEAD  → NONE, histories unrelated
upstream-19.0 ancestor of upstream/19.0? → NO
```

`git merge --ff-only upstream/19.0` (`afenda/README.md:120`) **refuses**, and
`--allow-unrelated-histories` does not apply to `--ff-only`. This repo is a shallow clone
whose `upstream-19.0` is an orphan root commit. The saving grace: its tree is byte-identical
to upstream `2d1b7a131`, so `git fetch --unshallow` then
`git branch -f upstream-19.0 2d1b7a131` restores ancestry without moving content — and makes
`git log upstream-19.0..upstream/19.0` a real changelog, which *is* the review.

## A stable AFENDA API boundary

Consumers should call `/api/afenda/v1/sales/orders`, not `/web/dataset/call_kw`:

```
Consumers → AFENDA Contract → AFENDA Application Service → Odoo ORM
```

This is what makes a capability movable later without the consumer caring. Note the
existing `/json/2/<model>/<method>` endpoints are `readonly` per method, so they are exactly
the traffic a read replica can serve.

**Keep** `models.Model`, the PostgreSQL transactional model, fields, recordsets, manifests,
ACLs and record rules, the view framework, and the accounting and inventory engines. The
goal is a boundary, not a rewrite.

## Vercel

xForge cannot run on Vercel — persistent HTTP workers, a separate gevent websocket port,
multiprocessing and dedicated cron processes are not a function runtime, and the registry
cold start alone rules it out. Forcing it would be **breaking the wrong constraint**.

Vercel's correct role:

```
Vercel: AFENDA website · customer portal · modern frontend · Control Plane UI
   ↓ API
xForge runtime on container infrastructure
```

## What to add now, before anything ambitious

Six cheap pieces that prevent xForge being trapped later:

1. **AFENDA Runtime Identity** — the release/version/image digest the runtime reports.
2. **AFENDA Tenant Context** — one place that answers "which tenant is this request".
3. **AFENDA Storage Interface** — `put/get/delete/exists/stream/checksum`, with
   `LocalFilestoreAdapter` first and an S3-compatible adapter second.
4. **AFENDA Job Interface** — `job.enqueue(...)`, backed by `ir.cron` initially.
5. **AFENDA Upstream Delta Manifest** — the authored/derived separation above. **Start this
   at G0, not G5.** It is a YAML file a build step writes; by the time the distribution
   compiler exists you already hold years of trustworthy delta history instead of starting
   the record then.
6. **AFENDA Provenance** — a read-only endpoint every instance exposes, which application
   code must never be able to edit:

   ```json
   {"product":"AFENDA xForge","release":"19.0.1.0.5","upstream":"odoo/19.0@2d1b7a131",
    "source":"84fd3…","identity_rules":"ce17a…","image":"sha256:…",
    "database_schema":"19.0.1.0.5","built_at":"…","environment":"production"}
   ```

   So that a bug report resolves to an exact runtime, source, upstream, rule set, image and
   migration level. *Humans may forget how production came to exist; AFENDA must not.*

The **Delta Manifest / Distribution Compiler is the most strategically important**. The
23,291-file measurement is already enough evidence to distinguish generated identity
changes from real framework changes. Formalising that separation is what turns xForge from
a large white-label fork into a **reproducible AFENDA distribution built on Odoo**.

## Defects found while verifying (fix before a release)

> **Status 2026-09-25**, checked against the tree:
> - **Fixed:**
>   - Root `README.md` and `SECURITY.md` rewritten, with no `odoo.com` link.
>   - Branch `19.0` retired to the tag `archive/19.0`.
>   - `afenda_api_docs` guides reachable: in the manifest, served by the catch-all, versioned and `.html` links resolved, `test_guides_in_sync` present.
>   - `fonts.odoocdn.com` removed (`BASELINE` 10826).
>   - `data_dir` set by `deploy/entrypoint.sh`.
>   - Production cron set in `deploy/entrypoint.sh`. `afenda/odoo.conf` stays at 0 as a dev-only config.
>   - `.dockerignore` tracked.
>   - The Pillow conflict: the tools follow the root's tiers. 126 generated images are byte-identical between 3.11 + 9.4.0 and 3.12 + 10.2.0.
>   - Python 3.12 in CI for the tools suite, with 3.11 kept.
> - **Still open:**
>   - The scan scope. No `odoo.com` link remains at the root, but widening to `doc/`, `setup/` and `debian/` (1,177 hits, mostly CLA records and packaging) needs an allowlist design.
>   - The Odoo image on 3.12 / `ubuntu:noble`.
>   - The Windows-side determinism hash.

- **`scan_identity`'s blast radius is `SCAN_DIRS = ("addons", "odoo")`**
  (`afenda/tools/rebrand.py:18`). Nothing at the repo root, in `debian/`, `setup/` or
  `doc/` is in scope — which is *why* the root `README.md` is still verbatim upstream Odoo
  (21 `odoo.com` links). A hole in the gate's definition, not an oversight. `SECURITY.md`
  is the sharp one: it routes vulnerability reports to Odoo.
- **Branch `19.0` is not the product.** `git show 19.0:odoo/release.py` →
  `product_name = 'Odoo'`; HEAD → `'AFENDA xForge'`. `19.0` touches zero files under
  `odoo/` or `addons/`, while `afenda/README.md` calls it "This deploys."
- **`afenda_api_docs` guides are unreachable, three ways.** `views/guides.xml` is absent
  from the manifest's `data` (`__manifest__.py:14`); *independently*,
  `controllers/landing.py:11-16` routes `/docs/<subpath>` to always render the landing
  template; and `build_docs.py:5` claims a `test_guides_in_sync` test **that does not
  exist**.
- **`fonts.odoocdn.com`** is still fetched at runtime by
  `addons/web/static/fonts/fonts.scss:10-12,20-22,30-32,40-42` (12 URLs). Installing
  `fonts-noto-*` in the image does not fix it — the browser does the fetching. These lines
  are inside the 10,838 baseline, so the fix lowers the count and the same commit must
  lower `BASELINE`.
- **`data_dir` unset** derives the filestore from `release.product_name`
  (`odoo/tools/config.py:509-515`) → `~/.local/share/AFENDA xForge/filestore/<db>`:
  depends on the service user's `HOME` and contains a space.
- **`max_cron_threads = 0`** in `afenda/odoo.conf` — cron entirely disabled.
- **Pillow conflict**: `afenda/tools/requirements.txt` pins `pillow==9.4.0`, root pins
  `Pillow==10.2.0` for ≥3.12. They cannot share a venv, and icon renders are documented as
  Pillow-version-sensitive.
- **`.dockerignore` will be silently gitignored** — `.gitignore:5` is `.*` and the
  whitelist covers only `.gitignore`, `.gitkeep`, `.github`, `.mailmap`, `.weblate.json`.
  Needs `git add -f` or it works locally and vanishes in CI.
- **Python 3.12 / `ubuntu:noble`** is the target: Odoo's own 19.0 image is `FROM
  ubuntu:noble`, and the `< 3.12` pin tier carries `cryptography==3.4.8` (a 2021 release)
  versus `42.0.8` on `>= 3.12`. Dev runs 3.11, so CI must run 3.12 — but **keep 3.11 in CI
  during the transition**: 3.11 as the existing-compatibility proof, 3.12 as the mandatory
  release gate. Drop 3.11 from release qualification only once 3.12 has stayed green and the
  image/icon determinism question above is settled. Flipping the whole environment in one
  release is the riskier path.
- **Image generation may not be cross-platform deterministic.** PNG output is version- and
  platform-sensitive; dev is Windows/3.11, target is Linux/3.12. Formalise the split rather
  than leaving it to judgement:

  | Class | Transforms | Treatment |
  |---|---|---|
  | Deterministic | text, XML, `.po`/`.pot`, Python, JS, SCSS | generated in CI |
  | Binary | PNG, JPEG, possibly fonts | committed golden until proven |

  The graduation gate is a determinism test: hash the generator's output on Windows and on
  Linux; equal promotes that artifact to generated, unequal keeps it source-controlled.

## Corrections recorded

- **`ir.cron` coordinates concurrent workers.** My claim that exactly one cron role may
  exist was wrong: `_acquire_one_job` uses `FOR NO KEY UPDATE SKIP LOCKED`
  (`ir_cron.py:365`, comment at `:330-332`). Redundant cron workers are supported; one
  service is an operational choice, not a correctness requirement. The *real* cron hazard
  stands and is stronger: never let cron discover databases — assign them explicitly, per
  runtime, because `cron_database_list()` falls back to `list_dbs(True)` which is scoped by
  PostgreSQL ownership.
- **The connection ceiling undercounted.** The gevent process has its own pool
  (`db_maxconn_gevent`), so it is 10 processes and ~640 potential connections at defaults,
  not 9 and 576. Budget per role.
- **G2 was not actually stateless as I defined it.** I listed the session seam and then
  omitted it from G2. Attachments *and* sessions must both leave the disk before the tier
  is stateless.
- **Splitting the websocket role at G2 was too ambitious.** `PreforkServer` spawns and
  respawns the gevent child itself; a separate role at that stage duplicates or fights it.
  G3/G4, on measured load.
- **Force-pushing the generated branch was the wrong foundation.** Append-only, plus a
  cryptographically bound release manifest, for a platform whose premise is kept truth.

- My earlier "database name == subdomain label" is **superseded** by the tenant registry
  above. Routing should not be welded to naming.
- My earlier lean toward Debian 12 (on the grounds that `wkhtmltopdf` 0.12.6 has no Noble
  build) was **wrong**: Odoo's own image installs the *jammy* `.deb` on Noble with pinned
  per-arch SHA1s.
- A design agent reported that `log_handler = odoo.tests:INFO` does not restore the test
  count. **Rejected on evidence** — an observed passing run printed both
  `odoo.tests.stats: afenda_brand: 46 tests` and `odoo.tests.result: 0 failed, 0 error(s)
  of 40 tests`. `odoo.tests.result` is under `odoo.tests`, so the handler reaches it. CI
  should still assert on both lines: a missing per-module `stats` line is how a module's
  tests go silently missing.

## Verified references

`ir_attachment.py:88,147,158,173,325,473` · `http.py:995,1815,2176,402-418` ·
`ir_actions_report.py:42,119,515,1036` · `sql_db.py:823` · `service/server.py:99-100` ·
`service/db.py:454` · `tools/config.py:509-515` · `addons/rpc/controllers/json2.py:38,49` ·
`afenda/tools/rebrand.py:18` · `afenda/tools/rules.py:53-61` · `.git/shallow` and
`git merge-base` for the upstream blocker.
