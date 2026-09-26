# Handoff: "AFENDA-owned API assets" phase 1 → the next session

Read this before starting work. It records what this run of the plan
`docs/superpowers/plans/2026-09-25-afenda-owned-api-assets.md` shipped, the corrections
filed against its design spec, what is waiting on the owner, and what is still open. Where
it disagrees with the tree, the tree wins. Correct this file rather than work around it.

## Start here

1. `git log --oneline -20` on this branch (`claude/superpowerskill-agent-setup-x5fcyv`,
   HEAD after this session's commit) to see Tasks 1-7's commits. This branch has **not**
   been merged to `main` and no PR was opened for it (see "Owner decisions" below) — check
   before assuming any of this is live.
2. `CLAUDE.md` → "Superpowers skills" says which skills to use and where `CLAUDE.md`
   overrides them. Its "Commands" section now also has the OpenAPI asset exporter and
   `api_diff` invocations (added by this session).
3. `afenda/README.md` → "Documentation at /docs" is the fullest prose description of what
   phase 1 built; read it before the spec or the per-task reports.

## What landed (phase 1 of the "AFENDA-owned API assets" plan, all 7 tasks)

| Task | What |
|---|---|
| 1 | RFC 9457 Problem Details on every `/json/2` error (`afenda_runtime`'s `ir.http._handle_error`, `problems.py`); the `/docs/api/errors` page. |
| 2 | The OpenAPI exporter's shared `Problem`/error-response plumbing and the live document's size reduction (per-operation responses collapsed to shared `4XX`/`5XX` refs). |
| 3 | `x-afenda-dynamic-enum` for environment-derived selections (installed languages, `ENVIRONMENT_DERIVED_SELECTIONS = {("res.partner", "tz")}`). |
| 4 | 33 committed OpenAPI 3.1 documents under `afenda/addons/afenda_api_docs/openapi/<area>.json`, generated as `base.user_admin` on a fresh all-apps install; per-area attribution rule (AFD-ARCH-CORR-0007); `info.description` per asset. |
| 5 | `afenda/tools/api_diff.py` (`check`, `changelog`), `openapi/CHANGELOG.md`, `api_version.py` (`API_VERSION = "1.0.0"`). |
| 6 | CI: `afenda-image.yml`'s module-suite and asset-freshness steps, `afenda-ci.yml`'s `api_contract` job; `test_deploy_static`'s CI-shape coverage. |
| 7 (this session) | Documentation, the CI floor correction, two stale-comment corrections, this handoff. No code changes — docs, `CLAUDE.md`, `afenda/README.md`, and two workflow files only. |

Every task went through `plan → dispatch → implement → review → fix round → re-review →
complete`, recorded turn by turn in
`.superpowers/sdd/2026-09-25-afenda-owned-api-assets/progress.md`; the per-task briefs and
reports are alongside it (`task-<N>-brief.md`, `task-<N>-report.md`).

## Corrections filed against the design spec

Recorded in `docs/superpowers/specs/2026-09-25-afenda-owned-api-and-doc-assets-design.md`,
"Corrections recorded" (format: `.claude/odoo-agent-rules.md`, "Correction ledger"). One line
each; read that section for the full evidence and replacement text.

- **AFD-ARCH-CORR-0001** (AMENDED): `type` is the relative reference `/docs/api/errors#<code>`,
  not an absolute `nexuscanon.com` URI — the landing site serves no errors page.
- **AFD-ARCH-CORR-0002** (AMENDED): the actual code table, keyed by exception class then by
  HTTP status, replacing the spec's illustrative list.
- **AFD-ARCH-CORR-0003** (AMENDED, twice): every `/json/2` error raised *after* dispatch gets
  Problem Details. **Three** pre-dispatch exclusions keep upstream's plain HTML instead: a
  wrong `Content-Type` (415), an unknown database (nodb 404), and — added by the Task 1
  review — a failure while a read-only request re-acquires its cursor
  (`odoo/http.py:2317-2324` → `2889`; pool exhaustion or a lost connection). The third would
  need a server-wide patch of `Json2Dispatcher.handle_error` to cover, so it is documented,
  not patched.
- **AFD-ARCH-CORR-0004** (RETRACTED): no per-commit `x-afenda-build` header — it would make
  every committed document differ on every commit, defeating the golden-file gate.
  `info.version` (`API_VERSION`) is the only version marker.
- **AFD-ARCH-CORR-0005** (AMENDED): the asset lives at
  `afenda/addons/afenda_api_docs/openapi/<area>.json` plus `CHANGELOG.md` alongside, not
  under `docs/` — `.dockerignore` excludes `/docs` from the production image.
- **AFD-ARCH-CORR-0006** (AMENDED, **for the owner's attention**): generated as
  `base.user_admin` (`su=False`, `lang=en_US`) on default settings, not a dedicated
  API-reference role. The documented surface is the administrator's on a fresh install;
  fields behind an optional feature group the admin doesn't hold by default (e.g.
  multi-currency) are absent.
- **AFD-ARCH-CORR-0007** (AMENDED): area attribution is checked in order — a model defined
  by an application module belongs to that application; otherwise `ir.*` models form a
  `technical` document; otherwise the original smallest-closure rule. Measured: `core`
  927 KiB, `technical` 745 KiB, `mail` 557 KiB.
- **AFD-ARCH-CORR-0008** (AMENDED, **for the owner's attention**): the per-committed-document
  size budget is 1.5 MiB, not 1 MiB — `account` alone measures over 1 MiB of genuine
  accounting API surface (55 models, 1012 operations). The live per-request document keeps
  the tighter 1 MiB budget, achieved by collapsing per-operation response entries to shared
  `4XX`/`5XX` references.
- **AFD-ARCH-CORR-0009** (AMENDED): document validation is a standard-library structural
  check (required top-level keys, every `$ref` resolves, every operation has `operationId`
  / `requestBody` / `responses`), not full OpenAPI 3.1 meta-schema validation — no JSON
  Schema validator is in `.venv` and phase 1 adds no dependencies. Accepted gap.
- **AFD-ARCH-CORR-0010** (AMENDED): an additive change is never reported as breaking, but
  needs at least a MINOR bump (not just "caught by oasdiff"); a descriptive-only change
  needs none. Done by `afenda/tools/api_diff.py`.
- **AFD-ARCH-CORR-0011** (AMENDED, amended again during Task 3): committed documents mark an
  environment-derived selection `x-afenda-dynamic-enum: true` and omit `enum`, rather than
  baking in one server's installed languages or `pytz.all_timezones`. A selection counts as
  environment-derived when its `selection` is a callable/method name, **or** the field
  (resolved through its related chain) is in `ENVIRONMENT_DERIVED_SELECTIONS` — found to be
  needed because `res.partner.tz` is a *static* list built from `pytz` at import time, which
  the callable-only test alone missed; the constant starts as `{("res.partner", "tz")}`.

## Measured counts (read the printed line, never the exit code)

All measured on this session's tree at commit `e5b3b81a5` (HEAD before this session's own
commit; Tasks 1-6 already on it) unless noted.

| What | Command | Printed result |
|---|---|---|
| Tools suite | `.venv/Scripts/python -m unittest discover afenda/tools/tests` | `Ran 304 tests in 48.731s` … `OK (skipped=1)` |
| `test_deploy_static` alone (inside the tools suite) | `.venv/Scripts/python -m unittest afenda.tools.tests.test_deploy_static -v` | `Ran 35 tests in 0.016s` … `OK` |
| Four AFENDA modules together (CI shape), fresh db `afenda_t7`, port 8179 | `-i afenda_brand,afenda_brand_digest,afenda_runtime,afenda_api_docs --test-enable --test-tags "/afenda_brand,/afenda_brand_digest,/afenda_runtime,/afenda_api_docs" --without-demo=all` | `odoo.tests.result: 0 failed, 0 error(s) of 183 tests when loading database 'afenda_t7'` |
| Asset export, fresh all-apps db `afenda_assets` (reused; already had all Community apps installed from Task 4, so not reinstalled) | `OUT_DIR=<tmp> ADDONS_ROOT=addons odoo-bin shell … < afenda/tools/export_openapi_shell.py` | `afenda-openapi: wrote 33 documents`; `diff -rq` against the committed `openapi/` shows only the (never-exported) `CHANGELOG.md` as a difference — all 33 `.json` files byte-identical |
| `api_diff check` against `origin/main` | `python -m afenda.tools.api_diff check --base-ref origin/main` | `breaking: 0, additive: 8452, descriptive: 0` / `no base contract` (exit 0) — `origin/main` predates this feature, confirming the no-base-contract counts path (AFD-ARCH-CORR-0010, the Task 5/172c12518 fix) |

**A finding worth recording, not a discrepancy in the required number:** the per-module
breakdown `odoo.tests.stats` prints alongside the result line (e.g. `afenda_api_docs: 146
tests`) is **not** the module's real test count. `OdooSuite._handleClassSetUp` /
`_tearDownPreviousClass` (`odoo/tests/suite.py:196-225`) record a `setUpClass`/`tearDownClass`
stat entry per test class via `result.collectStats`, and `_TEST_ID`'s regex
(`odoo/tests/result.py:45-54`) happily parses `TestClass.setUpClass` as if `setUpClass` were a
test method, so `log_stats()`'s per-module counter (`odoo/tests/result.py:244-273`) counts
2 phantom entries per test class on top of the real tests. Confirmed by class count: 21 + 3 +
1 + 4 = 29 classes across `afenda_api_docs`/`afenda_brand`/`afenda_brand_digest`/
`afenda_runtime` × 2 = 58; `146+61+4+30 − 58 = 183` — exactly the real, authoritative
`testsRun` total, and the corrected per-module split (`104`/`55`/`2`/`22`) matches numbers
already known from standalone runs (`afenda_api_docs` alone `104`, `afenda_runtime` alone
`22`). **Only the single `odoo.tests.result` line is the real count** — never sum the
per-module `odoo.tests.stats` lines.

The measured `183` matches what Task 4's fix round predicted
(`progress.md`: "CI ODOO_TESTS_MIN target is now 183"), so `.github/workflows/afenda-image.yml`'s
`ODOO_TESTS_MIN` is now set to `"183"` with a comment citing this measurement and the SHA it
ran on (`e5b3b81a5`).

## What this session changed (Task 7, docs/CI only — no application code)

- `afenda/README.md` → "Documentation at /docs": added the error contract, the errors page,
  the three pre-dispatch exclusions (AFD-ARCH-CORR-0003), the asset's `base.user_admin`
  generation identity and its consequence for optional-feature-group fields
  (AFD-ARCH-CORR-0006), the asset's location/regeneration/size-budget/area-attribution
  rules (AFD-ARCH-CORR-0005/0007/0008), the environment-derived-selection marker
  (AFD-ARCH-CORR-0011), the version rule, and the `api_diff` commands.
- `CLAUDE.md` → "Commands": added the exporter invocation and both `api_diff` subcommands,
  plus a note that a `[REBRAND]` apply or an upstream merge changes generated help text (and
  therefore the asset's descriptions) and must be followed by regenerating and committing the
  asset — a descriptive-only change, no version bump. Also repointed "Handoffs between
  sessions" at this file as the newest, keeping the `2026-09-25-cloud-session.md` note about
  the two owner rulings (no hand-written guides, no G2) intact.
- `.github/workflows/afenda-image.yml`: `ODOO_TESTS_MIN` `"177"` → `"183"`, comment rewritten
  to cite this session's measurement and SHA instead of the stale `146 + 8 + 23` arithmetic.
- `.github/workflows/afenda-ci.yml`: corrected the `api_contract` step's comment, which said
  `api_diff` "always prints the three change lists" — since `172c12518` (Task 5's fix round
  2), a run with no base contract prints the three change-class *counts* instead, and only a
  real version-to-version diff prints the full lists.
- This handoff file.

No PR was opened for this branch (see "Owner decisions").

## Owner decisions carried over (binding, from 2026-09-25)

- **No hand-written guide pages.** Still true; nothing in phase 1 adds one. See
  `afenda/README.md`'s guides bullet, which now says so explicitly.
- **G2 waits.** Untouched by this plan.

## Waiting on the owner

1. **AFD-ARCH-CORR-0008** — the 1.5 MiB per-committed-document size budget (up from the
   original 1 MiB), because `account` alone is over 1 MiB of genuine accounting surface.
   Needs the owner's sign-off on the number; `account.json` currently measures
   1,031,048 bytes (~1007 KiB), comfortably under 1.5 MiB.
2. **AFD-ARCH-CORR-0007** — the area-attribution rule (application-owned model → its area;
   otherwise `ir.*` → `technical`; otherwise smallest closure). This changed the shape of
   the 33 files from the plan's original "closure in every app or none ⇒ `core`" rule.
3. **AFD-ARCH-CORR-0006** — the asset documents the administrator's default-settings surface,
   not a dedicated API-reference role with every feature group. Fields behind an optional
   feature group (multi-currency, etc.) are simply absent from the committed contract.
4. **Whether to open a PR for this branch at all**, and against what target — Task 7's brief
   said to open one; the controller deferred that to
   `superpowers:finishing-a-development-branch` (whole-branch review first), per the ruling
   in `progress.md`. The draft PR body is in this session's `task-7-report.md`, naming
   AFD-ARCH-CORR-0008, 0007 and 0006 for the owner as requested.

## Open, repo-only (phase 2 and deferred items — pick up with the normal plan → review loop)

- **Phase 2, the functional reference** (generated end-user documentation: apps, screens,
  fields, statuses, access) is outlined in the design spec but not specified or started.
  Specify it separately, per the spec's own note, before any implementation — and remember
  the owner's binding ruling: **no hand-written guide pages**, ever, for this or anything
  else.
- **SDKs** (a generated client from the committed OpenAPI documents) were deferred; nothing
  in phase 1 builds one.
- **Minor, deferred findings from task reviews** (see `progress.md` for the fuller list):
  - Task 2: `afenda_api_docs` now hard-imports `afenda_runtime.problems` at module level
    (declared dependency; cannot load in isolation) — deferred.
  - Task 2: the manifest version-bump convention (which component to bump on a module
    change) is unstated — deferred.
  - Task 3: `write_assets` and `_app_closures` each search installed applications
    independently (two round-trips) — deferred.
  - Task 5: `x-enum-labels` relabelling is not diffed by `api_diff` (a descriptive change
    would go unreported) — deferred.
  - Task 5: `_version_bump` raises on a malformed/pre-release version string rather than
    reporting a clean error (`API_VERSION` is always `MAJOR.MINOR.PATCH` today, so latent)
    — deferred.
  - Task 1: 4xx `detail` sometimes echoes upstream's message text verbatim (e.g. `AccessError`
    names the model/group, a 422 carries the constraint's own signature text) — the spec
    allows this; the plan flagged it for revisiting with the owner, still open.
- **Industry packs and CI numbers from the 2026-09-25 handoff** are unaffected by this plan
  and still apply; see that file for their own open items (Windows Pillow determinism hash,
  automatic-deploy setup, `catchall@nexuscanon.com`, etc.) — this file does not repeat them.

## Where things are

- **Plan, specs, gate change list:**
  `docs/superpowers/plans/2026-09-25-afenda-owned-api-assets.md`,
  `docs/superpowers/specs/2026-09-25-afenda-owned-api-and-doc-assets-design.md`
  (`gc-error-contract.md`, `gc-asset.md`, `gc-change-gate.md` alongside it under
  `.superpowers/sdd/2026-09-25-afenda-owned-api-assets/`).
- **Per-task briefs, reports and the turn-by-turn progress ledger:**
  `.superpowers/sdd/2026-09-25-afenda-owned-api-assets/` (`task-<N>-brief.md`,
  `task-<N>-report.md`, `progress.md`, the `review-<sha>..<sha>.diff` files).
- **The committed asset:** `afenda/addons/afenda_api_docs/openapi/` (33 `.json` files +
  `CHANGELOG.md`); the exporter is `afenda/tools/export_openapi_shell.py`; the checker is
  `afenda/tools/api_diff.py`; the version constant is
  `afenda/addons/afenda_api_docs/api_version.py`.
- **Previous handoff:** `docs/superpowers/handoffs/2026-09-25-cloud-session.md` (industry
  packs, the live `/docs/api` and `/docs/openapi.json` routes this plan builds on, CI shape
  before this plan, and its own owner decisions and open items).
