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
| 1 | RFC 9457 Problem Details on every `/json/2` error (`afenda_runtime`'s `ir.http._handle_error`, `problems.py`). |
| 2 | The `/docs/api/errors` page; the OpenAPI exporter's shared `Problem`/error-response plumbing and the live document's size reduction (per-operation responses collapsed to shared `4XX`/`5XX` refs). |
| 3 | `x-afenda-dynamic-enum` for environment-derived selections (installed languages, `ENVIRONMENT_DERIVED_SELECTIONS = {("res.partner", "tz")}`). |
| 4 | 33 committed OpenAPI 3.1 documents under `afenda/addons/afenda_api_docs/openapi/<area>.json`, generated as `base.user_admin` on a fresh all-apps install; per-area attribution rule (AFD-ARCH-CORR-0007); `info.description` per asset. |
| 5 | `afenda/tools/api_diff.py` (`check`, `changelog`), `openapi/CHANGELOG.md`, `api_version.py` (`API_VERSION = "1.0.0"`). |
| 6 | CI: `afenda-image.yml`'s module-suite and asset-freshness steps, `afenda-ci.yml`'s `api_contract` job; `test_deploy_static`'s CI-shape coverage. |
| 7 (this session) | Documentation, the CI floor correction, two stale-comment corrections, this handoff. No code changes — docs, `CLAUDE.md`, `afenda/README.md`, and two workflow files only. |

Every task went through `plan → dispatch → implement → review → fix round → re-review →
complete`. The turn-by-turn ledger this ran from lived at
`.superpowers/sdd/2026-09-25-afenda-owned-api-assets/progress.md` — gitignored, so it does
not survive past the container it was written in (`CLAUDE.md`: a handoff must not rely on a
scratch ledger). What it decided is committed instead: the plan's own "Global Constraints"
section (`docs/superpowers/plans/2026-09-25-afenda-owned-api-assets.md`), the spec's
"Corrections recorded" section (next), and, for every deviation the ledger ruled on that
neither of those already covers, "Rulings made during execution" below.

## Corrections filed against the design spec

Recorded in `docs/superpowers/specs/2026-09-25-afenda-owned-api-and-doc-assets-design.md`,
"Corrections recorded" (format: `.claude/odoo-agent-rules.md`, "Correction ledger"). One line
each; read that section for the full evidence and replacement text.

- **AFD-ARCH-CORR-0001** (AMENDED): `type` is the relative reference `/docs/api/errors#<code>`,
  not an absolute `nexuscanon.com` URI — the landing site serves no errors page.
- **AFD-ARCH-CORR-0002** (AMENDED): the actual code table, keyed by exception class then by
  HTTP status, replacing the spec's illustrative list.
- **AFD-ARCH-CORR-0003** (AMENDED, twice): every `/json/2` error raised *after* dispatch gets
  Problem Details. **Three** pre-dispatch exclusions never reach that path: a wrong
  `Content-Type` (415) and an unknown database (nodb 404) keep upstream's plain HTML, but a
  failure while a read-only request re-acquires its cursor (`odoo/http.py:2317-2324`; pool
  exhaustion or a lost connection) — added by the Task 1 review — escapes to
  `request.dispatcher.handle_error` (`odoo/http.py:2889`), which by then is
  `Json2Dispatcher.handle_error` (`odoo/http.py:2666-2690`): it answers with upstream's
  JSON-RPC-style `serialize_exception` body (`name`, `message`, `arguments`, `context`,
  `debug` = the full traceback), status 500. Covering it would need a server-wide patch of
  `Json2Dispatcher.handle_error`, so it is documented, not patched.
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

## Rulings made during execution

Every `Ruling:` line from the turn-by-turn ledger (`.superpowers/sdd/2026-09-25-afenda-owned-api-assets/progress.md`,
gone with the container that wrote it — see "Where things are"), compressed to one line each,
in ledger order, none skipped. A ruling already stated in full above ("Corrections filed",
AFD-ARCH-CORR-000*) is not repeated here.

1. Per-operation responses collapse to a shared `4XX`/`5XX` `Problem` reference (plus `200`),
   sizes re-measured before the size budget is fixed — cost if wrong: a client wanting
   per-status detail only reads the generic Problem description.
2. CI's asset-staleness check is `git status --porcelain` on the asset directory (catches new
   untracked files; `git diff` alone would miss them) — cost if wrong: none.
3. Dynamic (callable/method-name) selections omit `enum` in the committed asset, flagged
   `x-afenda-dynamic-enum: true`; the live document is unchanged; determinism is proven by a
   double export under different `PYTHONHASHSEED` values; CI uploads the regenerated set as
   an artifact — cost if wrong: the asset loses timezone/language enum values.
4. An absent base contract reads as "no base contract": the check passes as long as
   `CHANGELOG.md` has a section for the head version — cost if wrong: none (this plan's own
   first PR hits exactly this path).
5. `load_set` resolves each document's own `requestBodies` `$ref`s before the union — cost if
   wrong: none.
6. Every deviation from the spec is filed as a one-line ruling; the area/budget/role rulings
   are named in the PR text for the owner — cost if wrong: none.
7. OpenAPI 3.1 meta-schema validation is a standard-library structural check, not full
   `jsonschema` validation (no such dependency in `.venv`, phase 1 adds none); the gap is
   accepted — cost if wrong: an exotic schema error slips through uncaught.
8. `manifest_applications` moves to the pure, odoo-free `asset_rules.py`; CI's fetch is
   `git fetch --no-tags --depth=1 origin main:refs/remotes/origin/main`; `ODOO_TESTS_MIN` is
   raised to the measured count in Task 6; the asset-generation step gets a 20-minute
   timeout — cost if wrong: none.
9. Determinism is proven by a double export under different hash seeds; the "exactly one
   area" test compares against an independently computed model list — cost if wrong: none.
10. Minors 10-15 accepted as specified: exact test counts, a `problem_code` unit test (8 Task 1
    tests), "delete, don't replace" wording, `dev_mode` patched in tests, `actionlint` kept
    optional, spec section 1.3, and `write_bytes` plus a `.gitattributes` `linguist-generated`
    entry for the committed asset — cost if wrong: none.
11. The 415 (wrong `Content-Type`) and nodb 404 exclusions are documented, not handled — cost
    if wrong: a client sending the wrong `Content-Type` sees upstream's plain HTML.
12. The error-code table is keyed by exception class then HTTP status (`AccessDenied`/
    `AccessError` → `access_denied`; `MissingError` → `not_found`; `LockError` → `conflict`;
    `ValidationError` → `validation_error`; `UserError` → `user_error`; else by status: 401
    unauthenticated, 403/404/409 as named, else <500 `invalid_request`, ≥500
    `internal_error`; `ConcurrencyError` dropped from the table) — cost if wrong: a client
    keys its own handling off the wrong code.
13. The 500-path test uses `patch.object(..., autospec=True)` and `mute_logger('odoo.http')`;
    the 403 test uses an internal user's key against `ir.cron`/`search`, revoked via
    `_remove()`; the portal key's expiry is 0.5 day; requests go through `json=` — cost if
    wrong: none (test-shape decisions only).
14. CI runs the exporter with `docker run -i`; the exporter prints "wrote N documents" and CI
    asserts N equals the expected file count and is greater than zero — cost if wrong: a
    silent no-op export (empty stdin) would pass unnoticed.
15. The asset reflects `base.user_admin` on default settings — stated in both the doc and the
    spec correction — cost if wrong: none (recorded for the owner as AFD-ARCH-CORR-0006).
16. `afenda_api_docs`'s manifest gains explicit dependencies on `afenda_runtime` and `rpc` —
    cost if wrong: none.
17. Path-traversal route vectors must resolve to 404 or a 303 redirect to `/docs`, never raw
    file bytes — cost if wrong: a crafted URL reads an arbitrary file.
18. The errors page passes `no_footer`, matching `landing.py`'s own convention — cost if
    wrong: none.
19. AFENDA's own 5xx log line carries the opaque `instance` id and the exception type only;
    upstream's own traceback log line stays adjacent and unchanged — cost if wrong: none.
20. Spec deviations are filed as `AFD-ARCH-CORR-0001` onward in the design spec's own
    "Corrections recorded" section; `CHANGELOG.md`'s `1.0.0` section is written by
    `api_diff changelog`, never by hand — cost if wrong: none.
21. Tasks 5 and 6 run in parallel with Task 1 (the skill's default is serial) since T5 touches
    only `afenda/tools/api_diff.py` plus its test (no database) and T6 only
    `.github/workflows/*` plus `test_deploy_static.py` (no database); T2-T4 stay serial (they
    share `openapi.py`/`controllers/api.py`) — cost if wrong: interleaved commits, or a T6
    step whose names drift from T3/T5 (caught by T7's own CI simulation).
22. Task 5's Step 5 (generate `CHANGELOG.md`) is deferred until after Task 4, since it needs
    `api_version.py` (Task 2) and the asset directory (Task 4) — cost if wrong: one extra
    small dispatch.
23. Tools-suite counts reported by T5 and T6 may double-count the other's new test depending
    on ordering (297 or 298 either way); 278 + 19 (T5) + 1 (T6) = 298 is accepted as the
    combined target — cost if wrong: none.
24. The cursor-reacquisition failure is documented as a third known exclusion (pool
    exhaustion / cursor re-acquire after `ReadOnlySqlTransaction`,
    `odoo/http.py:2317-2324` → `2889`) in CORR-0003 and the README, flagged for the final
    review, rather than covered by a server-wide monkeypatch of
    `Json2Dispatcher.handle_error` — cost if wrong: a traceback reaches a caller when the
    database pool is exhausted.
25. `res.partner.tz` is a *static* selection built from `pytz` at import time, which the
    original "callable or method-name ⇒ dynamic" rule missed; the rule becomes "environment-
    derived if `selection` is callable/a string, **or** the field (through its related chain)
    is in `ENVIRONMENT_DERIVED_SELECTIONS = {("res.partner", "tz")}`" — cost if wrong: another
    import-time list appears later and makes repeated exports differ (caught by CI's double
    export / staleness check).
26. Counts shift by +1 after Task 3's reserved-guard test: `afenda_api_docs` after Task 4 is
    99 (92 + 7); CI's `ODOO_TESTS_MIN` becomes 178, not 177 — cost if wrong: none (the floor
    is re-measured anyway).
27. For the initial contract (no base), the changelog section is the heading plus one summary
    line (document/operation/schema counts); `check` prints the three change-class counts
    instead of the full lists; a real version-to-version diff keeps the full lists — cost if
    wrong: the `1.0.0` entry doesn't enumerate the initial surface (the committed documents
    do, so nothing is actually lost).
28. Portal users may fetch the committed asset (`auth="user"` kept) — it is the repository's
    public contract, no server data — cost if wrong: a portal user learns the full app
    catalogue's API shape.
29. Asset documents get their own `info.description`, generated as `base.user_admin` on a
    fresh install; all 33 regenerated together — cost if wrong: one regeneration.
30. CI's `ODOO_TESTS_MIN` target becomes 183 (146 + 8 runtime + 29 `api_docs`), set from
    Task 7's own simulation — cost if wrong: none.
31. Task 7's brief numbers were already stale by the time it ran: the tools suite is 304 (not
    298), there are three exclusions (not two), `afenda_api_docs` is 104, and the CI module
    floor is 183 — the dispatch carries these corrected figures over the brief — cost if
    wrong: the docs cite a stale count (caught by final review; and again by this fix wave,
    which found `183`/`304`/`104` themselves stale in turn).
32. Task 7's own Step 3, "open the PR", is deferred to `superpowers:finishing-a-development-branch`
    — the owner said no PR unless asked, and the whole-branch review comes first — cost if
    wrong: none (the PR text is drafted into the report, and now into this handoff's "Draft PR
    body").
33. The Task 7 task review and the final whole-branch review run in parallel, since Task 7 is
    docs/CI-only and both reviews are read-only, and the owner asked for non-conflicting
    parallel work — cost if wrong: a docs finding gets reported twice (deduplicated at
    adjudication).
34. Exclusion 3 (cursor re-acquisition) is fixed in docs only, not code — CORR-0003 (the spec,
    binding) accepts it, and covering it would mean monkeypatching `odoo.http`'s
    `Json2Dispatcher` — cost if wrong: a database-connection failure during cursor
    re-acquisition still returns a traceback to a JSON-2 client (documented, not silent).
35. `api_contract` also runs on push to `main`, with `base = github.event.before` (skipped
    with a notice when that is all zeros) — the owner's own path into `main` may be a direct
    push, and a failure there blocks `afenda-deploy`, which waits on `afenda-ci` — cost if
    wrong: a force-push to `main` fails the job until re-run.
36. The area-rule order stays exactly as coded (`ir.*` → `technical`, checked before
    application ownership) — the handoff records it as a deliberate deviation from
    CORR-0007's own listing order; no model is affected today, since every `ir.*`-named model
    in an application module extends a model first defined in `base` — cost if wrong: a
    future application defining a new `ir.*` model would land in `technical`, not its own
    application area.
37. The handoff inlines the draft PR body and a one-line-per-ruling summary, citing only
    committed files, since `CLAUDE.md` forbids relying on a scratch ledger — cost if wrong:
    none (this is that ruling, executed as this section and "Draft PR body" below).
38. Minors 5-8 and the 1.5 MiB size-budget assertion are folded into one fix wave rather than
    dispatched separately, since each is local and cheap — cost if wrong: none.

## Measured counts (read the printed line, never the exit code)

Task 7 measured these at commit `e5b3b81a5` (304 / 183 / 104 tools-suite / four-module /
`afenda_api_docs` real counts). A later fix wave (the whole-branch review's corrections,
`174c6ac5e` → the commits after it) added three tests — `afenda/tools/tests/test_api_diff.py`
gained `BaseRefTests` (a nonexistent `--base-ref` must exit 2, not read as "no base contract")
and a downgrade-is-an-error case, and `TestCommittedAsset` gained the 1.5 MiB size-budget
check (AFD-ARCH-CORR-0008) — raising every count below by the same amount. What follows is
the fix wave's own measurement, atop `174c6ac5e` (HEAD before that wave's own commits); Task
7's original counts are superseded, not repeated.

| What | Command | Printed result |
|---|---|---|
| Tools suite | `.venv/Scripts/python -m unittest discover afenda/tools/tests` | `Ran 307 tests` … `OK (skipped=1)` |
| `test_api_diff` alone (inside the tools suite) | `.venv/Scripts/python -m unittest afenda.tools.tests.test_api_diff -v` | `Ran 27 tests` … `OK` |
| `test_deploy_static` alone (inside the tools suite) | `.venv/Scripts/python -m unittest afenda.tools.tests.test_deploy_static -v` | `Ran 35 tests in 0.016s` … `OK` |
| Four AFENDA modules together (CI shape), reused db `afenda_t7`, port 8179 | `-u afenda_brand,afenda_brand_digest,afenda_runtime,afenda_api_docs --test-enable --test-tags "/afenda_brand,/afenda_brand_digest,/afenda_runtime,/afenda_api_docs"` | `odoo.tests.result: 0 failed, 0 error(s) of 184 tests when loading database 'afenda_t7'` |
| `TestCommittedAsset` + `TestSpecRouteGuard` alone, same db | `--test-tags "/afenda_api_docs:TestCommittedAsset,/afenda_api_docs:TestSpecRouteGuard"` | `odoo.tests.result: 0 failed, 0 error(s) of 6 tests when loading database 'afenda_t7'` |
| Asset export, fresh all-apps db `afenda_assets` (reused; already had all Community apps installed from Task 4, so not reinstalled) | `OUT_DIR=<tmp> ADDONS_ROOT=addons odoo-bin shell … < afenda/tools/export_openapi_shell.py` | `afenda-openapi: wrote 33 documents`; `diff -rq` against the committed `openapi/` shows only the (never-exported) `CHANGELOG.md` as a difference — all 33 `.json` files byte-identical |
| `api_diff check` against `origin/main` | `python -m afenda.tools.api_diff check --base-ref origin/main` | `breaking: 0, additive: 8452, descriptive: 0` / `no base contract` (exit 0) — `origin/main` predates this feature, confirming the no-base-contract counts path (AFD-ARCH-CORR-0010, the Task 5/172c12518 fix); unaffected by the fix wave, no code change on that path |

**A finding worth recording, not a discrepancy in the required number:** the per-module
breakdown `odoo.tests.stats` prints alongside the result line (e.g. `afenda_api_docs: 147
tests`) is **not** the module's real test count. `OdooSuite._handleClassSetUp` /
`_tearDownPreviousClass` (`odoo/tests/suite.py:196-225`) record a `setUpClass`/`tearDownClass`
stat entry per test class via `result.collectStats`, and `_TEST_ID`'s regex
(`odoo/tests/result.py:45-54`) happily parses `TestClass.setUpClass` as if `setUpClass` were a
test method, so `log_stats()`'s per-module counter (`odoo/tests/result.py:244-273`) counts
2 phantom entries per test class on top of the real tests. Confirmed by class count: 21 + 3 +
1 + 4 = 29 classes across `afenda_api_docs`/`afenda_brand`/`afenda_brand_digest`/
`afenda_runtime` (the fix wave adds a test method to an existing class, `TestCommittedAsset`,
and a `@tagged` decorator to another existing class, `TestSpecRouteGuard` — no new class, so
the class count is unchanged from Task 7) × 2 = 58; `147+61+4+30 − 58 = 184` — exactly the
real, authoritative `testsRun` total, and the corrected per-module split (`105`/`55`/`2`/`22`)
matches the narrower run above (`TestCommittedAsset`+`TestSpecRouteGuard` alone: 6 real tests,
10 stats = 6 + 2×2 classes). **Only the single `odoo.tests.result` line is the real count** —
never sum the per-module `odoo.tests.stats` lines.

The measured `184` is why `.github/workflows/afenda-image.yml`'s `ODOO_TESTS_MIN` is now set
to `"184"`, with a comment citing this measurement and the SHA it ran atop (`174c6ac5e`).

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

## What this fix wave changed (whole-branch review fixes, atop `174c6ac5e`)

Ten ruled items, none of them a design change (every ruling is recorded in "Rulings made
during execution" below). No application code beyond `afenda/tools/api_diff.py` itself and
test files.

1. **Docs only.** Reworded the third pre-dispatch exclusion in `afenda/README.md` and this
   handoff's "Corrections filed" section: the cursor-reacquisition failure does not keep
   upstream's plain HTML like the other two — it escapes to `Json2Dispatcher.handle_error`
   and answers with upstream's JSON-RPC-style `serialize_exception` body (full traceback),
   status 500.
2. **`afenda/tools/api_diff.py`.** `check`/`changelog` now refuse a `--base-ref` that does
   not exist (`base_ref_exists`, `git rev-parse --verify --quiet <ref>^{commit}`) instead of
   `list_base` silently reading it as "no base contract"; exit 2, naming the ref. One new
   test (`BaseRefTests`).
3. **`.github/workflows/afenda-ci.yml`.** `api_contract` now also runs on `push` to `main`,
   not only on pull requests: the base is `github.event.before`, fetched by SHA; an all-zero
   `before` (a brand-new branch) prints a `::notice::` and exits 0 instead of fetching a SHA
   that never existed.
4. **This handoff.** Removed every reference that sent the reader to `.superpowers/...`
   (gitignored, gone with the container that wrote it) and pointed at committed files
   instead; added "Rulings made during execution" and "Draft PR body" below; fixed two
   slips — the `/docs/api/errors` page is Task 2's, not Task 1's, and the gate-change files
   (`gc-*.md`) never lived "alongside the spec", they lived under the now-gone
   `.superpowers/sdd/...` ledger directory.
5. **`.github/workflows/afenda-image.yml`.** The asset-generation step ("API asset is
   current") now has `id: asset`; the upload step's `if:` gained
   `&& steps.asset.outcome != 'skipped'`, so a job that fails before that step runs no
   longer uploads the unregenerated, committed files under a name that promises they were
   regenerated.
6. **`afenda/README.md` and this handoff.** Reworded the area-attribution rule in the order
   the code actually checks it, stated completely (abstract/transient excluded; `ir.*` →
   `technical`; application ownership; every closure or none → `core`; smallest closure,
   alphabetical tie, otherwise); noted the `ir.*`-before-application-ownership order as a
   deliberate, currently-inert deviation from AFD-ARCH-CORR-0007's own listing order; removed
   this handoff's incorrect claim that the "every closure or none ⇒ `core`" step had been
   dropped (`asset_rules.py:59-61` still applies it).
7. **`afenda/addons/afenda_api_docs/tests/test_api_routes.py`.** `TestSpecRouteGuard` gained
   `@tagged("post_install", "-at_install")`, matching every other class in the file.
8. **`afenda/tools/api_diff.py`.** `_version_bump` now reports a head version lower than
   base as `"downgrade"`; `check` reports that as its own error rather than silently reading
   it as `"patch"`. One new test.
9. **`afenda/addons/afenda_api_docs/tests/test_assets.py`.** `TestCommittedAsset` gained a
   test that every committed `openapi/*.json` stays at or under the 1.5 MiB budget
   (AFD-ARCH-CORR-0008), naming the offending file and size on failure; `afenda/README.md`'s
   budget line now cites the test that enforces it.
10. **Counts.** `ODOO_TESTS_MIN` `"183"` → `"184"` (see "Measured counts" above); the stale
    `183`/`304`/`104` corrected wherever this file and `afenda/README.md` still carried them.
11. **`.github/workflows/afenda-image.yml` and `afenda/tools/tests/test_deploy_static.py`.**
    The first real `afenda-image.yml` run (36216051763, at `5c71e380d`) failed at the "API
    asset is current" step: its `odoo-bin shell` call passed no `--addons-path`, so the fresh
    `assets` database it opened had `afenda_api_docs` "not installable, skipped", and
    `afenda/tools/export_openapi_shell.py` raised `ModuleNotFoundError` importing it. The
    other three `odoo-bin` calls in that file already carried
    `--addons-path /opt/afenda/addons,/opt/afenda/afenda/addons,/opt/afenda/afenda/oca/server-brand,/opt/afenda/afenda/oca/web`;
    that run's earlier steps — the module suites (floor 184) and the industry pack suites —
    passed there, since they use those correct calls. Fixed by adding the same
    `--addons-path` to the exporter's call, guarded by a new static test,
    `test_ci_odoo_bin_calls_all_pass_the_afenda_addons_path`, that parses every `odoo-bin`
    invocation out of the workflow file and asserts each one carries it.

No PR was opened for this branch either (see "Owner decisions").

## Owner decisions carried over (binding, from 2026-09-25)

- **No hand-written guide pages.** Still true; nothing in phase 1 adds one. See
  `afenda/README.md`'s guides bullet, which now says so explicitly.
- **G2 waits.** Untouched by this plan.

## Waiting on the owner

1. **AFD-ARCH-CORR-0008** — the 1.5 MiB per-committed-document size budget (up from the
   original 1 MiB), because `account` alone is over 1 MiB of genuine accounting surface.
   Needs the owner's sign-off on the number; `account.json` currently measures
   1,031,048 bytes (~1007 KiB), comfortably under 1.5 MiB.
2. **AFD-ARCH-CORR-0007** — the area-attribution rule, in the order the code actually checks
   it (`assets.py`'s `asset_areas`, then `asset_rules.py`'s `assign_area`): abstract and
   transient models are excluded; an `ir.*`-named model goes to `technical`; otherwise a
   model defined by an application module belongs to that application; otherwise a model
   whose module is in every installed application's dependency closure, or in none of them,
   goes to `core` (unchanged from the plan's original rule — `asset_rules.py:59-61` still
   applies it); otherwise the application with the smallest closure containing the module,
   an equal tie going to the alphabetically first application name. The `ir.*` → `technical`
   check running before application ownership is a deliberate deviation from CORR-0007's own
   listing order (which puts application ownership first); it has no effect today, since
   every `ir.*`-named model in an application module extends a model first defined in `base`.
3. **AFD-ARCH-CORR-0006** — the asset documents the administrator's default-settings surface,
   not a dedicated API-reference role with every feature group. Fields behind an optional
   feature group (multi-currency, etc.) are simply absent from the committed contract.
4. **PR #5 is open** (https://github.com/pohlai88/afenda-xforge-v9/pull/5), opened on the owner's
   instruction of 2026-09-26 and driven to merge by `.claude/skills/steward/SKILL.md`. Its
   description supersedes the draft below, which is kept as written.
5. **Required status checks on `main`** (repository settings → branches, or a ruleset):
   require `tools suite`, `tools suite (Python 3.12)`, `api contract`, `nginx -t`,
   `docker build` and `pr evidence` before merging. Only the owner can set this; until then the
   checks bind agents (through the steward skill) but not a manual merge.

## Draft PR body (not submitted — for the controller/owner)

> **Title:** `[FIX] api docs: whole-branch review fix wave (tools, CI, docs, tests)`
>
> Ten ruled fixes closing out the whole-branch review of phase 1 of the "AFENDA-owned API
> assets" plan (Task 7's own commit, `174c6ac5e`, plus this fix wave atop it). No design
> change; every item was already ruled before implementation (see "Rulings made during
> execution").
>
> **For the owner's attention — three corrections recorded against the design spec, carried
> over from Task 7 and unchanged by this fix wave (restated here since this is the PR that
> would actually merge phase 1):**
> - **AFD-ARCH-CORR-0008**: the committed OpenAPI documents' per-file size budget is
>   1.5 MiB, not the original 1 MiB — `account.json` alone is genuine accounting API surface
>   at just over 1 MiB (1,031,048 bytes measured). The live per-request document keeps the
>   tighter 1 MiB budget via shared `4XX`/`5XX` response references. This fix wave adds a
>   test enforcing the 1.5 MiB budget on every committed document
>   (`TestCommittedAsset.test_committed_asset_stays_under_the_size_budget`).
> - **AFD-ARCH-CORR-0007**: which models land in which of the 33 area files is decided by an
>   application-owns-its-models-first rule (then `ir.*` → `technical` — checked first in the
>   code, ahead of application ownership, a deliberate and currently inert deviation from this
>   correction's own listing order — then the smallest-closure rule), not the original
>   "closure in every app or none ⇒ `core`" rule alone.
> - **AFD-ARCH-CORR-0006**: the asset is generated as `base.user_admin` on a fresh
>   installation's default settings, not a dedicated API-reference role holding every app's
>   manager group — so fields gated behind an optional feature group the admin doesn't hold
>   by default (e.g. multi-currency) are simply absent from the published contract.
>
> **What this fix wave changed** (see this handoff's "What this fix wave changed" section for
> the full ten-item list): `afenda/tools/api_diff.py` now refuses a nonexistent `--base-ref`
> (exit 2) instead of reading it as "no base contract", and reports a version downgrade as its
> own error instead of silently reading it as a patch bump; `afenda-ci.yml`'s `api_contract`
> job now also runs on push to `main`, not only on pull requests; `afenda-image.yml`'s asset
> upload no longer offers unregenerated files when the regeneration step itself was skipped;
> `afenda/README.md` and this handoff correct the third pre-dispatch error exclusion's actual
> behaviour (a JSON error body with a traceback, not HTML) and the area-attribution rule's
> prose (stated in code order, complete); `TestSpecRouteGuard` is tagged
> `post_install`/`-at_install` like its neighbours; `TestCommittedAsset` gained the size-budget
> test above; and every stale `183`/`304`/`104` count left by Task 7 is corrected to
> `184`/`306`/`105`; the first real `afenda-image.yml` run (36216051763, at `5c71e380d`)
> then found one more: the asset exporter's `odoo-bin shell` call had no `--addons-path`,
> fixed with a static guard, raising the tools suite to `307`.
>
> **Gates:** `test_api_diff` 27 tests (25 + 2 new) OK; the tools suite 307 tests OK
> (skipped=1); the four AFENDA modules together, reused database `afenda_t7`, 184 tests,
> 0 failed/0 error; `TestCommittedAsset` + `TestSpecRouteGuard` alone, same database, 6 tests,
> 0 failed/0 error. No generator or asset-content code changed, so no re-export was needed.

## Open, repo-only (phase 2 and deferred items — pick up with the normal plan → review loop)

- **Phase 2, the functional reference** (generated end-user documentation: apps, screens,
  fields, statuses, access) is outlined in the design spec but not specified or started.
  Specify it separately, per the spec's own note, before any implementation — and remember
  the owner's binding ruling: **no hand-written guide pages**, ever, for this or anything
  else.
- **SDKs** (a generated client from the committed OpenAPI documents) were deferred; nothing
  in phase 1 builds one.
- **Minor, deferred findings from task reviews:**
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

- **Plan and spec (committed, the durable record):**
  `docs/superpowers/plans/2026-09-25-afenda-owned-api-assets.md` (its own "Global
  Constraints" section is what a plan-level ruling should be checked against),
  `docs/superpowers/specs/2026-09-25-afenda-owned-api-and-doc-assets-design.md` (its own
  "Corrections recorded" section, restated in this file's "Corrections filed" above).
- **The turn-by-turn ledger and per-task briefs/reports** (`progress.md`, `task-<N>-brief.md`,
  `task-<N>-report.md`, the gate-change files `gc-error-contract.md`/`gc-asset.md`/
  `gc-change-gate.md`, the `review-<sha>..<sha>.diff` files) lived under
  `.superpowers/sdd/2026-09-25-afenda-owned-api-assets/` — gitignored, so they are gone with
  the container that wrote them; do not point a future session at that path expecting it to
  still be there. What they decided is captured above: the spec's corrections, and every
  ledger `Ruling:` line, compressed, in "Rulings made during execution" above.
- **The committed asset:** `afenda/addons/afenda_api_docs/openapi/` (33 `.json` files +
  `CHANGELOG.md`); the exporter is `afenda/tools/export_openapi_shell.py`; the checker is
  `afenda/tools/api_diff.py`; the version constant is
  `afenda/addons/afenda_api_docs/api_version.py`.
- **Previous handoff:** `docs/superpowers/handoffs/2026-09-25-cloud-session.md` (industry
  packs, the live `/docs/api` and `/docs/openapi.json` routes this plan builds on, CI shape
  before this plan, and its own owner decisions and open items).
