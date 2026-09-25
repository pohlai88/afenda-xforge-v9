# AFENDA-Owned API Contract and OpenAPI Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the JSON-2 API AFENDA's own asset: an AFENDA error contract (RFC 9457 Problem
Details, no Odoo internals), and a versioned, deterministic OpenAPI description of every
installable Community application. It is committed in the repository, served to signed-in
users, regenerated and checked in CI, and gated for breaking changes on every pull request.

**Architecture:**
- **Error contract:** an `ir.http._handle_error` override in `afenda_runtime` rewrites JSON-2
  error bodies.
- **Asset documents:** `afenda_api_docs` gains a pure area-assignment rule and an exporter
  that writes one sorted-key JSON document per area into the addon (so it ships in the image),
  and a route that serves those files.
- **Change gate:** a database-free tool in `afenda/tools/` diffs two committed sets and
  enforces the version rule.
- **CI:** it regenerates the set on a fresh all-apps database and fails on drift.

**Tech Stack:** Odoo 19.0 (`ir.http`, `HttpCase`, `TransactionCase`), Python 3.11 standard
library only (no new dependency), GitHub Actions, the existing `afenda-image` job's Docker
image and Postgres service.

**Spec:** `docs/superpowers/specs/2026-09-25-afenda-owned-api-and-doc-assets-design.md`,
phase 1, including "Owner decisions (2026-09-25)" items 1–4, which override the body where
they differ.

## Global Constraints

- **Hands off upstream:** never edit root `odoo/` or `addons/`. All code goes under
  `afenda/addons/afenda_runtime`, `afenda/addons/afenda_api_docs` and `afenda/tools`.
- **No new Python dependency, and no third-party tool in any gate.** oasdiff is not used
  (spec decision 4).
- **Error codes and status mapping** (checked in order; subclasses before parents):

  | Exception | Code |
  |---|---|
  | `AccessDenied` | `unauthenticated` |
  | `AccessError` | `access_denied` |
  | `MissingError` | `not_found` |
  | `ConcurrencyError` | `conflict` |
  | `ValidationError` | `validation_error` |
  | `UserError` | `user_error` |

  Otherwise by status: 401 `unauthenticated`, 403 `access_denied`, 404 `not_found`,
  409 `conflict`, anything else below 500 `invalid_request`. Status 500 or above is always
  `internal_error`.
- **Problem body keys, exactly:**
  - `type` = `"/docs/api/errors#<code>"`;
  - `title` = the HTTP reason phrase;
  - `status`, `code`, `detail`;
  - `message` = `detail`, kept for upstream's `/doc` explorer;
  - `instance` = `"urn:afenda:error:<uuid4 hex>"`, on 5xx only.

  Content type `application/problem+json; charset=utf-8`. A 5xx `detail` is always
  `"Internal server error"`.
- **Scope of the rewrite:** only when `request.dispatcher.routing_type == "json2"` and
  `config["dev_mode"]` is empty. Every other route keeps upstream's body.
- **API version:** `API_VERSION = "1.0.0"` in `afenda/addons/afenda_api_docs/api_version.py`,
  used as `info.version`. No commit id or timestamp in any committed document.
- **Asset location:** `afenda/addons/afenda_api_docs/openapi/<area>.json` and
  `afenda/addons/afenda_api_docs/openapi/CHANGELOG.md`. Never `docs/api/`: `.dockerignore`
  line 8 excludes `/docs` from the image.
- **Asset serialisation:** `json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + "\n"`,
  UTF-8. Built as `base.user_admin` with `su=False` and `context={"lang": "en_US"}`.
- **Area rule** (spec decision 2, refined by measurement on 2026-09-25):
  1. Abstract and transient models are excluded.
  2. A model whose `_original_module` is itself an installed application belongs to that app.
  3. Else a model whose name starts with `ir.` goes to `technical`.
  4. Else a module in the dependency closure of every installed application, or of none,
     goes to `core`.
  5. Else the app with the smallest dependency closure containing the module; a tie goes to
     the alphabetically first.

  Areas with no models get no file. `core` and `technical` must never be application names.
- **Supported applications:** every `addons/*/__manifest__.py` with `application: True` and
  `installable` not false. There are 34 at `1243e57a9`. The exporter refuses a database whose
  installed applications differ from that list.
- **Asset size budget:** 1.5 MiB (1,572,864 bytes) per committed document. Measured on
  2026-09-25: `account` 1166 KiB, the largest; `core` 927 KiB; `technical` 745 KiB; 33 files,
  9.4 MiB in total. The live `/docs/openapi.json` 1 MiB test stays as it is.
- **Change classes and the version rule:**
  - *Breaking:* a removed operation; a removed schema property; a changed property type; a
    removed enum value; a parameter or property newly required. Needs a MAJOR bump.
  - *Additive:* any added operation, schema, property or enum value. Needs at least a MINOR
    bump.
  - *Descriptive:* text only. No bump needed.
  - The diff is over the union of all documents, so a model moving between areas is not a
    removal.
- **CHANGELOG:** a new `API_VERSION` requires a `## <version>` section in `CHANGELOG.md`.
  The first section is `## 1.0.0`.
- **Commits:** `git commit --only -F msgfile -- <paths>`, with Odoo tags (`[ADD]` / `[FIX]` /
  `[IMP]`), and read the printed test counts, never the exit code (CLAUDE.md).

## Review Focus

1. **A non-JSON-2 error keeps upstream's shape.** The web client's `/web/dataset/call_kw`
   JSON-RPC errors are what the UI parses (Task 1 pins it).
2. **A model that moves between area files** when a new Community app appears must not read
   as a breaking removal (Task 5 pins it).
3. **A stale or partial local database** (an app missing or extra) must make the exporter
   refuse, not write a silently different asset set (Task 3 pins it).
4. **`/docs/api/spec/<area>.json` path tricks** (`..`, `%2e%2e`, absolute paths, unknown
   names) must 404 and never read outside the asset directory (Task 4 pins it).
5. **Bearer authentication failures** (missing, malformed or revoked API key) must come back
   as Problem Details 401, not upstream's body (Task 1 pins it).

---

### Task 1: Problem Details for JSON-2 errors

**Files:**
- Create: `afenda/addons/afenda_runtime/models/ir_http.py`
- Create: `afenda/addons/afenda_runtime/problems.py`
- Modify: `afenda/addons/afenda_runtime/models/__init__.py`,
  `afenda/addons/afenda_runtime/__manifest__.py` (bump `version`)
- Test: `afenda/addons/afenda_runtime/tests/test_problem_details.py`, registered in
  `tests/__init__.py`

**Interfaces:**
- Produces:
  - `afenda_runtime.problems.PROBLEM_CODES: tuple[tuple[str, int | None, str], ...]`, as
    `(code, typical_status, one-line description)` in the table order. Task 2 renders it.
  - `afenda_runtime.problems.problem_code(exception: BaseException, status: int) -> str`.
- Prior art: `git show 0eccdfa11:afenda/addons/afenda_brand/models/ir_http.py`
  (tag `archive/cloud-api-hardening`).
  - Port its approach: `super()._handle_error`, then rewrite the JSON body.
  - Re-verify each hook against this tree: `odoo/addons/base/models/ir_http.py:367`,
    `odoo/http.py:2350`, `:2666-2688`.
  - Do not copy its `type="about:blank"`; use the Global Constraints values.

- [ ] **Step 1: Write the failing tests** (`HttpCase`, `@tagged("post_install", "-at_install")`).
  Call `/json/2/<model>/<method>` with an API key from
  `env["res.users.apikeys"].with_user(u)._generate(None, "t", <future datetime>)`. See
  `odoo/addons/test_http/tests/test_webjson2.py` for the request shape.
  - `test_missing_or_bad_key_is_problem_401`: no header, `Bearer nonsense`, and a revoked
    key. Each gives status 401, content type starting `application/problem+json`,
    `body["code"] == "unauthenticated"`, and
    `body["type"] == "/docs/api/errors#unauthenticated"`.
  - `test_access_error_is_problem_403`: a portal user's key calls
    `res.users/search_read`. Expect 403 and `code == "access_denied"`.
  - `test_missing_record_is_problem_404`: `res.partner/write` on `ids=[<max id + 1000>]`.
    Expect 404 and `code == "not_found"`.
  - `test_bad_arguments_are_problem_422`: an unknown parameter name. Expect 422 and
    `code == "invalid_request"`.
  - `test_unexpected_error_is_opaque_500`:
    - patch `type(env["res.partner"]).name_search` to raise
      `RuntimeError("secret-internal-detail")`;
    - expect 500, `code == "internal_error"`, and `detail == "Internal server error"`;
    - the body text contains none of `secret-internal-detail`, `Traceback`, `odoo.`,
      `debug`, `arguments`, `context`;
    - `body["instance"]` matches `^urn:afenda:error:[0-9a-f]{32}$`;
    - `assertLogs("odoo.addons.afenda_runtime")` captures a record containing that same
      `instance`.
  - `test_every_problem_has_exactly_the_contract_keys`: across the cases above, the keys are
    `{"type","title","status","code","detail","message"}`, plus `instance` on 5xx only.
  - `test_json_rpc_errors_keep_upstream_shape`: an authenticated
    `/web/dataset/call_kw/res.partner/name_search` whose patched method raises `UserError`
    still returns the upstream JSON-RPC `error.data.name` shape.
- [ ] **Step 2: Run them and confirm they fail for the right reason.** Expect upstream bodies
  (`name`, `debug`), not import errors.
  ```
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -u afenda_runtime --test-enable --test-tags "/afenda_runtime:TestProblemDetails" --stop-after-init --http-port 8179
  ```
- [ ] **Step 3: Implement.**
  - `problems.py` holds the table and `problem_code`.
  - `models/ir_http.py` overrides `_handle_error(cls, exception)` as a classmethod on
    `ir.http`.
  - On 5xx, log `_logger.error("JSON-2 internal error %s", instance, exc_info=exception)`
    before replacing the body.
- [ ] **Step 4: Run the class again.** Expect `0 failed, 0 error(s) of 7 tests`. Then run the
  full `afenda_runtime` suite once and record the printed count.
- [ ] **Step 5: Commit** `[IMP] afenda_runtime: JSON-2 errors as RFC 9457 Problem Details`.

### Task 2: The OpenAPI document describes the AFENDA contract

**Files:**
- Create: `afenda/addons/afenda_api_docs/api_version.py`
- Create: `afenda/addons/afenda_api_docs/views/errors.xml` (template `afenda_api_docs.api_errors`)
- Modify:
  - `afenda/addons/afenda_api_docs/openapi.py`: the `Error` schema, the responses, and
    `info.version` at `:423`;
  - `controllers/api.py`: a new route `/docs/api/errors`, `auth="public"`;
  - `__manifest__.py`: add `afenda_runtime` to `depends`, add `views/errors.xml`, bump
    `version`.
- Test: `tests/test_openapi.py`, `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `afenda_runtime.problems.PROBLEM_CODES` (Task 1).
- Produces: `afenda_api_docs.api_version.API_VERSION: str = "1.0.0"`.

- [ ] **Step 1: Failing tests.**
  - `test_info_version_is_the_api_version`: `doc["info"]["version"] == API_VERSION`.
  - `test_error_schema_is_problem_details`: `components.schemas.Error.required` is
    `["type","title","status","code","detail"]`, and `code.enum` lists every code in
    `PROBLEM_CODES`.
  - `test_every_operation_documents_problem_responses`: statuses 401, 403, 404, 409, 422 and
    500 are all present, each `$ref` into `components/responses` with the
    `application/problem+json` media type.
  - `test_errors_page_lists_every_code`: `GET /docs/api/errors` is 200 anonymously and has an
    element `id="<code>"` for each code.
  - Replace `test_error_responses_use_the_dispatcher_error_shape`: it pins the old contract.
- [ ] **Step 2: Run them; they fail** on the old schema.
- [ ] **Step 3: Implement.** The errors page renders `PROBLEM_CODES` into a table, one anchor
  per code.
- [ ] **Step 4: Run the whole `afenda_api_docs` suite once.** Expect
  `0 failed, 0 error(s) of <75 − 1 + 4 = 78> tests`, and state it if it differs.
- [ ] **Step 5: Commit** `[IMP] afenda_api_docs: document the Problem Details contract and version the API`.

### Task 3: Asset areas and the exporter

**Files:**
- Create: `afenda/addons/afenda_api_docs/asset_rules.py`. Pure Python, no `odoo` import.
- Create: `afenda/addons/afenda_api_docs/assets.py`
- Create: `afenda/tools/export_openapi_shell.py`, a script fed to `odoo-bin shell` on stdin
- Test: `afenda/addons/afenda_api_docs/tests/test_assets.py`

**Interfaces:**
- Produces:
  - `asset_rules.assign_area(module: str, app_closures: dict[str, frozenset[str]]) -> str`,
    which implements the Global Constraints area rule for non-`ir.` models. The caller handles
    `ir.`.
  - `asset_rules.RESERVED_AREAS = ("core", "technical")`.
  - `assets.manifest_applications(addons_root: pathlib.Path) -> list[str]`: sorted and
    installable. It reads manifests with `ast.literal_eval`.
  - `assets.asset_areas(env) -> dict[str, list[str]]`: sorted model names per area, empty
    areas dropped.
  - `assets.render_asset(env, area: str, names: list[str]) -> bytes`: builds through
    `openapi.build_document`. Refactor `build_document(env, app=None, names=None)` so an
    explicit `names` list bypasses `models_for_app`. The existing callers are unchanged.
  - `assets.write_assets(env, out_dir: pathlib.Path, addons_root: pathlib.Path) -> list[pathlib.Path]`:
    - raises `ValueError` naming the missing and extra apps if the installed applications
      differ from `manifest_applications`;
    - writes every area;
    - deletes `*.json` files in `out_dir` for areas that no longer exist;
    - leaves `CHANGELOG.md` alone.
- `export_openapi_shell.py` reads `OUT_DIR` and `ADDONS_ROOT` from the environment and calls
  `write_assets(env(user=admin, su=False, context={"lang": "en_US"}), ...)`. Usage, added to
  the module README section in Task 7:
  ```
  OUT_DIR=afenda/addons/afenda_api_docs/openapi ADDONS_ROOT=addons .venv/Scripts/python odoo-bin shell -c afenda/odoo.conf -d <all-apps db> --no-http < afenda/tools/export_openapi_shell.py
  ```

- [ ] **Step 1: Failing tests** (`TransactionCase`, `post_install`).
  - `assign_area` on hand-built closures:
    - an app's own module goes to that app;
    - a module in every closure goes to `core`;
    - a module in no closure goes to `core`;
    - of two apps containing a module, the smaller closure wins;
    - an equal-size tie goes to the alphabetical first.
  - `test_ir_models_are_technical`, and `test_transient_and_abstract_models_are_excluded`
    (using `asset_areas` on the test database).
  - `test_every_concrete_model_is_in_exactly_one_area`.
  - `test_render_is_deterministic`: two `render_asset` calls give equal bytes, and the output
    has no `x-afenda-build` or timestamp key.
  - `test_render_is_openapi_31_and_under_budget`: every area is `openapi == "3.1.0"` and
    `len(bytes) <= 1_572_864`.
  - `test_write_refuses_a_database_with_different_apps` (Review Focus 3): pass an
    `addons_root` fixture directory whose manifests name one app that isn't installed. Expect
    `ValueError` naming it, and nothing written to `out_dir` (a tmp dir).
  - `test_write_removes_stale_area_files_but_keeps_the_changelog`.
- [ ] **Step 2: Run them; they fail** (import errors are acceptable only for the new modules).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `test_assets` again, then the full module suite once.** Record both counts.
- [ ] **Step 5: Commit** `[ADD] afenda_api_docs: OpenAPI asset areas and exporter`.

### Task 4: Generate, commit and serve the asset

**Files:**
- Create: `afenda/addons/afenda_api_docs/openapi/*.json` (generated) and
  `openapi/CHANGELOG.md`
- Modify: `afenda/addons/afenda_api_docs/controllers/api.py` (route
  `/docs/api/spec/<string:area>.json`, `auth="user"`), and the `/docs/api` page
- Test: `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `write_assets` (Task 3).
- Produces: the committed asset set. The route returns the file bytes with
  `Content-Type: application/json` and `Cache-Control: private, no-store`.

- [ ] **Step 1: Failing route tests.**
  - An anonymous request gets 303 to `/web/login`.
  - An internal user gets 200 for `core`, and the body equals the committed file's bytes.
  - An unknown area gets 404.
  - Review Focus 4: `..%2fmanifest`, `%2e%2e`, `core.json%00`, `/etc/passwd` and `CHANGELOG`
    all get 404, with nothing read outside `openapi/`. Accept only names matching
    `^[a-z0-9_]+$` that exist as files.
  - The `/docs/api` page links each committed area.
  - `test_committed_asset_carries_no_odoo_identity_in_prose` (spec, phase 1 acceptance):
    - apply `tests/test_identity.py`'s prose check to every `description`, `summary` and
      `title` value in every committed file;
    - wire values (keys, `operationId`, enum values, `$ref`) are exempt, as in the live
      document.
- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement the route, then generate.**
  - Build a fresh database with all supported apps, once:
    `-i afenda_brand,afenda_runtime,afenda_api_docs,<the 34 apps> --without-demo=all`.
    Measured at 215 s locally.
  - Run the exporter.
  - Write `CHANGELOG.md` with `## 1.0.0` and one line: "First published contract: Problem
    Details errors; one document per Community application area."
- [ ] **Step 4: Run the route tests, then the module suite once.** Also check the generated
  set: 33 files, each ≤ 1.5 MiB. Total ≈ 9.4 MiB, and state the measured figure.
- [ ] **Step 5: Commit** `[ADD] afenda_api_docs: the committed OpenAPI asset, served at /docs/api/spec`.
  Stage `openapi/` explicitly.

### Task 5: The change checker

**Files:**
- Create: `afenda/tools/api_diff.py`
- Test: `afenda/tools/tests/test_api_diff.py`, with fixtures built in code, no files

**Interfaces:**
- Produces:
  - `load_set(get_text: Callable[[str], str | None], names: list[str]) -> dict`: merges every
    document in a set into one union of `paths` and `components.schemas`.
  - `diff(base: dict, head: dict) -> Changes`, where `Changes` is a dataclass with
    `breaking`, `additive` and `descriptive`, each a sorted `list[str]` of human-readable
    lines.
  - `required_bump(changes) -> Literal["major", "minor", "none"]`.
  - `check(base_version: str, head_version: str, changes, changelog_text: str) -> list[str]`:
    the errors; empty means pass.
  - CLI `python -m afenda.tools.api_diff check --base-ref origin/main` reads the base set and
    `api_version.py` through `git show <ref>:<path>`, and the head from the working tree.
    Exit 1 on errors, printing the change lists either way.
  - CLI `python -m afenda.tools.api_diff changelog --base-ref origin/main` prints the
    Markdown section for the current `API_VERSION`.

- [ ] **Step 1: Failing tests.** One per Global Constraints change class:
  - removed operation, removed property, changed type, removed enum value and newly required
    each give `breaking`;
  - an added operation or property gives `additive`;
  - a changed `description` gives `descriptive`.
  - Review Focus 2: a model whose path and schema move from `sale_management.json` to
    `website_sale.json` gives no change at all.
  - `required_bump` gives `major`, `minor` or `none`.
  - `check`:
    - breaking without a MAJOR bump is an error;
    - additive without at least a MINOR bump is an error;
    - descriptive with no bump passes;
    - a version change without `## <version>` in the changelog is an error.
- [ ] **Step 2: Run them; they fail.**
  `.venv/Scripts/python -m unittest afenda.tools.tests.test_api_diff`
- [ ] **Step 3: Implement.** Standard library only.
- [ ] **Step 4: Run the file, then the tools suite once.** Expect `Ran 278 + N tests … OK`.
- [ ] **Step 5: Commit** `[ADD] tools: api_diff, the OpenAPI change checker and version gate`.

### Task 6: CI gates

**Files:**
- Modify: `.github/workflows/afenda-image.yml`: add the step "API asset is current" after
  the pack suites.
- Modify: `.github/workflows/afenda-ci.yml`: add the job `api contract`, on `pull_request`
  only.
- Test: `afenda/tools/tests/test_deploy_static.py`, with a static assertion that both steps
  exist.

**Interfaces:**
- Consumes:
  - the Task 3 exporter;
  - the Task 5 CLI;
  - the image job's existing tools mount (`/opt/afenda/afenda/tools`) and its shared data
    directory.

- [ ] **Step 1: Failing static test**, `test_ci_regenerates_the_api_asset_and_gates_changes`.
  It asserts:
  - `afenda-image.yml` runs `export_openapi_shell.py` and then
    `git diff --exit-code -- afenda/addons/afenda_api_docs/openapi`;
  - `afenda-ci.yml` runs `python -m afenda.tools.api_diff check --base-ref`.
- [ ] **Step 2: Implement.**
  - **Image job:**
    - a fresh database `assets`;
    - install `afenda_brand,afenda_runtime,afenda_api_docs` plus the application list printed
      by a one-liner over `manifest_applications`;
    - then the exporter, with the repo's `openapi/` directory mounted as `OUT_DIR`. The
      container runs as the image's `afenda` user (`deploy/Dockerfile:86`), so first
      `chmod -R a+w` that directory on the runner;
    - then `git diff --exit-code` with the message "the API asset is stale: run the exporter
      (afenda/README.md) and commit".
  - **CI job:**
    - `actions/checkout` with `fetch-depth: 0`, or `git fetch origin main --depth=1`;
    - `python -m afenda.tools.api_diff check --base-ref origin/main`;
    - write the change lists to `$GITHUB_STEP_SUMMARY`.
- [ ] **Step 3: Run the static test and actionlint.**
- [ ] **Step 4: Commit** `[ADD] ci: regenerate the API asset and gate API changes`.

### Task 7: Documentation and handoff

**Files:**
- Modify: `afenda/README.md`, section "Documentation at /docs": the asset, how to regenerate
  it, the version rule, the errors page.
- Modify: `docs/superpowers/handoffs/2026-09-25-cloud-session.md`, or add a newer dated
  handoff: phase 1 state, and phase 2 next.
- Modify: `docs/superpowers/specs/2026-09-25-afenda-owned-api-and-doc-assets-design.md`:
  - 1.3's path is replaced by the in-addon location;
  - 1.4's supported-app list by decision 2;
  - drop `x-afenda-build` from 1.2 (it would break determinism).

- [ ] **Step 1: Write them.**
- [ ] **Step 2: Final gates, once each, citing counts and the SHA:**
  - the tools suite;
  - `afenda_runtime` and `afenda_api_docs` suites (with `afenda_brand`, as CI installs them);
  - a fresh-database CI simulation of both `afenda-image` Odoo steps plus the new asset step;
  - `test_deploy_static`.
- [ ] **Step 3: Commit, then open the PR.**
