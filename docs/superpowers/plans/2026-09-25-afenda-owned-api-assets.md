# AFENDA-Owned API Contract and OpenAPI Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the JSON-2 API AFENDA's own asset:
- an AFENDA error contract (RFC 9457 Problem Details, no Odoo internals);
- a versioned, deterministic OpenAPI description of every installable Community
  application, committed in the repository, served to signed-in users, regenerated in CI,
  and gated for breaking changes on every pull request.

**Architecture:**
- An `ir.http._handle_error` override in `afenda_runtime` rewrites JSON-2 error bodies.
- `afenda_api_docs` gains:
  - a pure area-assignment module;
  - an exporter that writes one sorted-key JSON document per area into the addon, so it ships
    in the image;
  - a route that serves those files.
- A database-free tool in `afenda/tools/` diffs two committed sets and enforces the version
  rule.
- CI regenerates the set on a fresh all-apps database, and fails on drift or a missing
  export.

**Tech Stack:** Odoo 19.0 (`ir.http`, `HttpCase`, `TransactionCase`), Python 3.11 standard
library only (no new dependency), GitHub Actions, and the `afenda-image` job's image and
Postgres service.

**Spec:** `docs/superpowers/specs/2026-09-25-afenda-owned-api-and-doc-assets-design.md`,
phase 1. Read its "Owner decisions (2026-09-25)" and "Corrections recorded"
(AFD-ARCH-CORR-0001 to 0011) first: they override the body. This plan was reviewed twice
before execution (plan quality; Odoo facts). The ledger at
`.superpowers/sdd/2026-09-25-afenda-owned-api-assets/progress.md` holds the rulings.

## Global Constraints

### Scope

- Never edit root `odoo/` or `addons/`. Code goes only under `afenda/addons/afenda_runtime`,
  `afenda/addons/afenda_api_docs` and `afenda/tools`.
- No new Python dependency, and no third-party tool in any gate.

### Error contract (AFD-ARCH-CORR-0001..0003)

- **Codes by exception class**, checked in this order:

  | Exception | Code |
  |---|---|
  | `AccessDenied`, `AccessError` | `access_denied` |
  | `MissingError` | `not_found`, with `detail` fixed to `"Record does not exist or has been deleted."` |
  | `LockError` | `conflict` |
  | `ValidationError` | `validation_error` |
  | `UserError` | `user_error` |

- **Otherwise by status:** 401 `unauthenticated`, 403 `access_denied`, 404 `not_found`,
  409 `conflict`, any other status below 500 `invalid_request`, and 500 or above always
  `internal_error`.
- **Body keys, exactly:**
  - `type` = `"/docs/api/errors#<code>"`;
  - `title` = the HTTP reason phrase;
  - `status`, `code`, `detail`;
  - `message` = `detail`;
  - `instance` = `"urn:afenda:error:<uuid4 hex>"`, on 5xx only.

  A 5xx `detail` is always `"Internal server error"`. The content type is
  `application/problem+json; charset=utf-8`. Every other upstream response header is kept
  (401's `WWW-Authenticate` included).
- **When the rewrite applies:** only when `request.dispatcher.routing_type == "json2"` and
  `config["dev_mode"]` is falsy. That covers upstream's `/doc*.json` routes too. Every other
  route keeps upstream's body.
- **Known exclusions, documented and not handled:** a wrong Content-Type (415 before
  dispatch, `odoo/http.py:2199-2213`) and an unknown database (nodb 404,
  `odoo/http.py:2851-2864`).
- **Logging:** on 5xx, one log line `_logger.error("JSON-2 internal error %s (%s)", instance,
  type(exception).__name__)`. Upstream's line (`odoo/http.py:2881`) already carries the
  traceback.

### The asset

- **API version:** `API_VERSION = "1.0.0"` in `afenda/addons/afenda_api_docs/api_version.py`,
  used as `info.version`. No commit id or timestamp appears in any committed document
  (AFD-ARCH-CORR-0004).
- **Response entries (AFD-ARCH-CORR-0008):** every operation's `responses` are exactly
  `{"200": …, "4XX": {"$ref": "#/components/responses/Problem"}, "5XX": {"$ref": "#/components/responses/Problem"}}`.
  The `Problem` response's description lists the statuses and codes.
- **Location (AFD-ARCH-CORR-0005):** `afenda/addons/afenda_api_docs/openapi/<area>.json` and
  `…/openapi/CHANGELOG.md`.
- **Serialisation:**
  - `json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + "\n"`, encoded UTF-8
    and written with `Path.write_bytes`;
  - `.gitattributes` gains
    `afenda/addons/afenda_api_docs/openapi/*.json -diff eol=lf linguist-generated`.
- **Built as** `base.user_admin`, `su=False`, `context={"lang": "en_US"}`, on default
  settings (AFD-ARCH-CORR-0006).
- **Dynamic selections (AFD-ARCH-CORR-0011):** in asset documents, a selection whose
  `selection` attribute is a callable or a method name gets no `enum`, and
  `"x-afenda-dynamic-enum": true` instead. The live document is unchanged.
- **Area rule (AFD-ARCH-CORR-0007)**, checked in order:
  1. Abstract and transient models are excluded.
  2. A model whose `_original_module` is an installed application goes to that application.
  3. A model named `ir.*` goes to `technical`.
  4. A module in the dependency closure of every installed application, or of none, goes to
     `core`.
  5. Otherwise, the application with the smallest closure containing the module. A tie goes
     to the alphabetical first.

  An area with no models gets no file.
- **Supported applications:** `manifest_applications(addons_root)`, pure: every
  `addons/*/__manifest__.py` with `application: True` and `installable` not false. There
  are 34 at `83d88f153`. The exporter refuses a database whose installed applications
  differ from that list.
- **Size:** 1.5 MiB (1,572,864 bytes) per committed document (AFD-ARCH-CORR-0008).
  Re-measure after Task 2's response change, and state the largest document. The live
  `/docs/openapi.json` 1 MiB test stays.

### The change gate

- **Change classes (AFD-ARCH-CORR-0010):**
  - *Breaking:* a removed operation; a removed schema property; a changed property type; a
    removed enum value; a parameter or property newly required. Needs a MAJOR bump.
  - *Additive:* any addition. Needs at least a MINOR bump.
  - *Descriptive:* text only. No bump needed.
- **How the diff works:** over the union of all documents; request-body `$ref`s are resolved
  within each document first; `info` is ignored. A model moving between areas is not a
  change.
- **No base contract:** when the base has no `openapi/` directory or `api_version.py`, the
  check prints `no base contract` and passes if `CHANGELOG.md` has a section for the head
  version.
- **CHANGELOG:** written by `python -m afenda.tools.api_diff changelog`, never by hand.

### Conventions

- `git commit --only -F msgfile -- <paths>`, with Odoo tags. Read printed test counts,
  never exit codes.
- Every test class is `@tagged("post_install", "-at_install")` and reaches `BaseCase`
  through a base named in the same file.

## Review Focus

1. **The same export gives different bytes on two machines or runs** (hash seed, installed
   languages, pytz). Task 4 exports twice with `PYTHONHASHSEED=1` and `=2`, and Task 6's CI
   compares against the committed set.
2. **A new area file appears and is never committed.** Task 6 checks
   `git status --porcelain`, not `git diff`.
3. **The first PR, where the base has no contract.** Task 5 has
   `test_check_passes_when_base_has_no_contract`.
4. **A breaking change hidden inside a shared request-body `$ref`.** Task 5 has
   `test_newly_required_parameter_inside_a_shared_body_is_breaking`.
5. **`/docs/api/spec/` path tricks never return file bytes.** Task 4 has the route vectors:
   each gives 404 or a 303 to `/docs`.

---

### Task 1: Problem Details for JSON-2 errors

**Files:**
- Create: `afenda/addons/afenda_runtime/problems.py`, `afenda/addons/afenda_runtime/models/ir_http.py`
- Modify: `afenda/addons/afenda_runtime/models/__init__.py`; `__manifest__.py` (add `rpc` to
  `depends`, bump `version`)
- Test: `afenda/addons/afenda_runtime/tests/test_problem_details.py`, registered in
  `tests/__init__.py`

**Interfaces:**
- Produces:
  - `problems.PROBLEM_CODES: tuple[tuple[str, int, str], ...]`: `(code, status, one-line
    description)` for `unauthenticated` 401, `access_denied` 403, `not_found` 404,
    `conflict` 409, `validation_error` 422, `user_error` 422, `invalid_request` 400,
    `internal_error` 500. Task 2 renders it.
  - `problems.problem_code(exception: BaseException, status: int) -> str`.
- Prior art: `git show 0eccdfa11:afenda/addons/afenda_brand/models/ir_http.py`. Port the
  approach: `super()._handle_error`, then rewrite the `odoo.http.Response` from
  `make_json_response` (`odoo/http.py:2074-2092`) with `set_data`, touching nothing when
  the route is not json2.

- [ ] **Step 1: Failing tests** (`HttpCase`).
  - Every test patches `config["dev_mode"]` to `[]`.
  - Requests use `json=` payloads with `Authorization: Bearer <key>`. Keys come from
    `env["res.users.apikeys"].with_user(u)._generate(None, "t", <now + 0.5 day>)`, revoked
    with `_remove()`. See `odoo/addons/test_http/tests/test_webjson2.py:28-30,172-191,240`.

  The tests:
  - `test_problem_code_follows_the_table`: a pure call of `problem_code`. Subclass order
    wins: `AccessDenied` gives `access_denied`, and `LockError` gives `conflict`, not
    `user_error`. Also 418 gives `invalid_request`, and 503 gives `internal_error`.
  - `test_missing_bad_or_revoked_key_is_problem_401`: for each of the three cases, status
    401, media type `application/problem+json`, `code == "unauthenticated"`, `type` =
    `/docs/api/errors#unauthenticated`, and the `WWW-Authenticate` header present.
  - `test_access_error_is_problem_403`: an internal user's key on `ir.cron/search` gives
    403 and `access_denied`.
  - `test_missing_record_is_problem_404_without_internals`: `res.partner/write` with
    `ids=[<max id + 1000>]` and `vals={"name": "x"}` gives 404, `code == "not_found"`, and
    the fixed `detail`. The body contains neither the uid nor `res.partner(`.
  - `test_bad_arguments_are_problem_422`: an unknown parameter name gives 422 and
    `invalid_request`.
  - `test_unexpected_error_is_opaque_500`:
    - `patch.object(type(env["res.partner"]), "name_search", autospec=True,
      side_effect=RuntimeError("secret-internal-detail"))`, inside
      `mute_logger("odoo.http")`;
    - expect 500, `internal_error`, and `detail == "Internal server error"`;
    - the body contains none of `secret-internal-detail`, `Traceback`, `odoo.`, `debug`,
      `arguments`, `context`;
    - `instance` matches `^urn:afenda:error:[0-9a-f]{32}$`;
    - `assertLogs("odoo.addons.afenda_runtime", "ERROR")` has a line containing that
      `instance`.
  - `test_every_problem_has_exactly_the_contract_keys`: over the responses above, the keys
    are `{"type","title","status","code","detail","message"}`, plus `instance` on 5xx only.
  - `test_json_rpc_errors_keep_upstream_shape`: an authenticated
    `/web/dataset/call_kw/res.partner/name_search`, patched with `autospec=True` to raise
    `UserError("x")`, still returns `error.data.name == "odoo.exceptions.UserError"`.
- [ ] **Step 2: Run them; they fail on the upstream bodies** (`name`, `debug`), not on
  imports.
  ```
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -u afenda_runtime --test-enable --test-tags "/afenda_runtime:TestProblemDetails" --stop-after-init --http-port 8179
  ```
- [ ] **Step 3: Implement** `problems.py` and the `_handle_error` classmethod override.
- [ ] **Step 4: Run the class.** Expect `0 failed, 0 error(s) of 8 tests`. Then run the full
  `afenda_runtime` suite once: 14 before, 22 expected.
- [ ] **Step 5: Commit** `[IMP] afenda_runtime: JSON-2 errors as RFC 9457 Problem Details`.

### Task 2: The OpenAPI document describes the AFENDA contract

**Files:**
- Create: `afenda/addons/afenda_api_docs/api_version.py`; `views/errors.xml` (template
  `afenda_api_docs.api_errors`)
- Modify:
  - `openapi.py`: the `Error` schema, `components.responses`, `path_item` responses at
    `:308-313`, and `info.version` at `:423`;
  - `controllers/api.py`: route `/docs/api/errors`, `auth="public"`, rendered with
    `{"no_footer": True}` as `landing.py:103-107` does;
  - `__manifest__.py`: add `afenda_runtime` and `rpc` to `depends`, add `views/errors.xml`,
    bump `version`.
- Test: `tests/test_openapi.py`, `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `afenda_runtime.problems.PROBLEM_CODES`.
- Produces: `api_version.API_VERSION = "1.0.0"`, and `components.responses.Problem`.

- [ ] **Step 1: Failing tests.**
  - `test_info_version_is_the_api_version`.
  - `test_error_schema_is_problem_details`: `Error.required ==
    ["type","title","status","code","detail"]`, and `code.enum` equals the codes in
    `PROBLEM_CODES`, in order.
  - `test_every_operation_answers_4xx_and_5xx_with_problem`: every operation's `responses`
    keys are exactly `{"200","4XX","5XX"}`, both `$ref`s point to
    `#/components/responses/Problem`, and its media type is `application/problem+json`.
  - `test_errors_page_lists_every_code`: anonymous `GET /docs/api/errors` is 200, with an
    element `id="<code>"` per code.
  - **Delete** `test_error_responses_use_the_dispatcher_error_shape`; the tests above cover
    it.
- [ ] **Step 2: Run them; they fail** on the old schema.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full `afenda_api_docs` suite once.** Expect `0 failed, 0 error(s) of
  78 tests` (75 − 1 + 4). `test_every_app_document_stays_renderable` must still pass under
  1 MiB. The response change shrinks every operation.
- [ ] **Step 5: Commit** `[IMP] afenda_api_docs: document the Problem Details contract and version the API`.

### Task 3: Asset areas and the exporter

**Files:**
- Create:
  - `afenda/addons/afenda_api_docs/asset_rules.py`, with no `odoo` import;
  - `afenda/addons/afenda_api_docs/assets.py`;
  - `afenda/tools/export_openapi_shell.py`, a script run with `odoo-bin shell` on stdin.
- Modify: `openapi.py`, giving `build_document(env, app=None, names=None, asset=False)`.
  `names` bypasses `models_for_app`; `asset=True` applies the dynamic-selection rule.
- Create `.gitattributes` or modify it, adding the line from Global Constraints.
- Test: `afenda/addons/afenda_api_docs/tests/test_assets.py`

**Interfaces:**
- Produces:
  - `asset_rules.manifest_applications(addons_root: pathlib.Path) -> list[str]`: sorted,
    reads manifests with `ast.literal_eval`.
  - `asset_rules.assign_area(module: str, app_closures: dict[str, frozenset[str]]) -> str`:
    rules 2, 4 and 5; the caller applies rules 1 and 3.
  - `asset_rules.RESERVED_AREAS = ("core", "technical")`.
  - `assets.asset_areas(env) -> dict[str, list[str]]`.
  - `assets.render_asset(env, area: str, names: list[str]) -> bytes`.
  - `assets.write_assets(env, out_dir: pathlib.Path, addons_root: pathlib.Path) -> int`:
    - on success, returns the number of documents written;
    - raises `ValueError` naming the missing and extra applications when the installed set
      differs;
    - removes stale `*.json` in `out_dir`;
    - never touches `CHANGELOG.md`.
- `export_openapi_shell.py`:
  - reads `OUT_DIR` and `ADDONS_ROOT` from the environment;
  - calls `write_assets` in `env(user=<base.user_admin id>, su=False,
    context={"lang": "en_US"})`;
  - prints exactly `afenda-openapi: wrote <N> documents`.

- [ ] **Step 1: Failing tests** (`TransactionCase`).
  - **Five `assign_area` cases on hand-built closures:**
    - the app's own module goes to that app;
    - in every closure goes to `core`;
    - in no closure goes to `core`;
    - of two candidates, the smaller closure wins;
    - an equal tie goes to the alphabetical first.
  - `test_manifest_applications_reads_only_installable_applications`, with a tmp fixture
    tree.
  - `test_ir_models_are_technical`.
  - `test_areas_cover_every_concrete_model_once`: build the expected list independently,
    by iterating `env.registry.models` and filtering on `_abstract` and `_transient`. Then
    assert the sorted union of all areas equals it, and the total count equals its length
    (no duplicates).
  - `test_asset_omits_dynamic_enums`: `res.partner.tz` has no `enum` and has
    `x-afenda-dynamic-enum: true`. A static selection keeps its `enum`. The live document
    still lists `tz` values.
  - `test_render_has_no_build_or_time_markers`: the rendered bytes contain no
    `x-afenda-build` and no date pattern `\d{4}-\d{2}-\d{2}T`.
  - `test_render_is_structurally_valid_openapi_31` (AFD-ARCH-CORR-0009): the top-level
    keys are `openapi/info/paths/components`, `openapi == "3.1.0"`, every `$ref`
    resolves, and every operation has `operationId`, `requestBody` and `responses`.
  - `test_write_refuses_a_database_with_different_apps`: a fixture manifest names an app
    that isn't installed. Expect `ValueError` naming it, and an empty `out_dir`.
  - `test_write_removes_stale_area_files_but_keeps_the_changelog`.
- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `test_assets`.** Expect `0 failed, 0 error(s) of 13 tests`. Then run the
  module suite once: 91 expected (78 + 13).
- [ ] **Step 5: Commit** `[ADD] afenda_api_docs: OpenAPI asset areas and exporter`.

### Task 4: Generate, commit and serve the asset

**Files:**
- Create: `afenda/addons/afenda_api_docs/openapi/*.json` (generated), and
  `openapi/CHANGELOG.md`, written by Task 5's tool once Task 5 lands. Until then this task
  commits the JSON only; see Step 5.
- Modify:
  - `controllers/api.py`: route `/docs/api/spec/<string:area>.json`, `auth="user"`,
    answering `Content-Type: application/json` and `Cache-Control: private, no-store`;
  - the `/docs/api` page, which links each committed area.
- Test: `tests/test_api_routes.py`, `tests/test_assets.py`

**Interfaces:**
- Consumes: `write_assets` and `export_openapi_shell.py`.
- Produces: the committed asset set. `area` is accepted only if it matches `^[a-z0-9_]+$`
  and names an existing file.

- [ ] **Step 1: Failing tests.**
  - The route:
    - anonymous gets 303 to `/web/login`;
    - an internal user gets 200 for `core`, with the bytes equal to the committed file;
    - an unknown area gets 404.
  - Path vectors `..%2fmanifest`, `%2e%2e`, `core.json%00`, `/etc/passwd` and `CHANGELOG`
    each get 404 or 303 to `/docs`, and never file bytes. Assert no response body starts
    with `{` or contains `"openapi"`.
  - `test_committed_asset_carries_no_odoo_identity_in_prose`: apply
    `tests/test_identity.py`'s prose check to every `description`, `summary` and `title`
    value in every committed file. Keys, `operationId`, enum values and `$ref` are exempt.
  - `test_committed_asset_matches_the_supported_applications`: a committed file exists for
    each non-empty area, and every file name is a supported application or reserved area.
- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement the route, then generate.**
  - Build a fresh database, once:
    `-i afenda_brand,afenda_runtime,afenda_api_docs,<the 34 applications> --without-demo=all`.
    Measured at 215 s.
  - Run the exporter twice, with `PYTHONHASHSEED=1` and then `=2`.
  - `git status --porcelain` on `openapi/` must be empty after the second run. That is
    Review Focus 1.
- [ ] **Step 4: Run the route and asset tests, then the module suite once.** State the
  count, the number of files, the largest document and its size. It must be ≤ 1.5 MiB;
  otherwise stop and report.
- [ ] **Step 5: Commit** `[ADD] afenda_api_docs: the committed OpenAPI asset, served at /docs/api/spec`.
  Stage `openapi/*.json` and `.gitattributes` explicitly.

### Task 5: The change checker, and the first CHANGELOG

**Files:**
- Create: `afenda/tools/api_diff.py`, `afenda/tools/tests/test_api_diff.py` (fixtures built
  in code)
- Create, generated: `afenda/addons/afenda_api_docs/openapi/CHANGELOG.md`

**Interfaces:**
- Constants:
  - `ASSET_DIR = "afenda/addons/afenda_api_docs/openapi"`;
  - `VERSION_FILE = "afenda/addons/afenda_api_docs/api_version.py"`, read with `ast`,
    never imported.
- Functions:
  - `list_base(ref) -> list[str]`: `git ls-tree --name-only <ref> <ASSET_DIR>/`, keeping
    `*.json`. An empty list means no base contract.
  - `load_set(get_text: Callable[[str], str | None], names: list[str]) -> dict`: resolves
    each document's `#/components/requestBodies/*` inline, then merges `paths` and
    `components.schemas`, ignoring `info`.
  - `diff(base: dict, head: dict) -> Changes`: `Changes` is a dataclass with `breaking`,
    `additive` and `descriptive`, each a sorted `list[str]`.
  - `required_bump(changes) -> Literal["major","minor","none"]`.
  - `check(base_version: str | None, head_version: str, changes, changelog: str) -> list[str]`:
    the errors.
  - `changelog_section(version: str, changes, first: bool) -> str`.
- CLI:
  - `python -m afenda.tools.api_diff check --base-ref <ref>`: exit 1 on errors; always
    print the three lists.
  - `python -m afenda.tools.api_diff changelog --base-ref <ref>`: prepends the section for
    the current `API_VERSION` to `CHANGELOG.md`. It is idempotent: a section already
    present means no change.

- [ ] **Step 1: Failing tests.**
  - One per Global Constraints change class. Removed operation, removed property, changed
    type, removed enum value and newly required each give `breaking`; an addition gives
    `additive`; a description change gives `descriptive`.
  - `test_model_moving_between_area_files_is_no_change`.
  - `test_newly_required_parameter_inside_a_shared_body_is_breaking`: a `$ref`'d body in
    both base and head, where the head requires one more property.
  - `test_info_changes_are_ignored`.
  - `required_bump`: three tests, one per result.
  - `check`:
    - breaking without MAJOR is an error;
    - additive without MINOR is an error;
    - descriptive with no bump passes;
    - a version change without its changelog section is an error;
    - `test_check_passes_when_base_has_no_contract`.
  - `test_changelog_is_idempotent`.
- [ ] **Step 2: Run them; they fail.**
  `.venv/Scripts/python -m unittest afenda.tools.tests.test_api_diff`
- [ ] **Step 3: Implement.** Standard library only.
- [ ] **Step 4: Run the file.** Expect `Ran 19 tests … OK`. Then run the tools suite once:
  `Ran 297 tests` (278 + 19).
- [ ] **Step 5: Generate the first changelog, then commit.**
  - Run `python -m afenda.tools.api_diff changelog --base-ref origin/main`. The base has no
    contract, so it writes `## 1.0.0 — initial contract`.
  - Commit `api_diff.py`, its tests and `CHANGELOG.md`:
    `[ADD] tools: api_diff, the OpenAPI change checker and version gate`.

### Task 6: CI gates

**Files:**
- Modify: `.github/workflows/afenda-image.yml` (add the step "API asset is current" after
  the pack suites, and raise `ODOO_TESTS_MIN`); `.github/workflows/afenda-ci.yml` (add the
  job `api contract`, on `pull_request` only)
- Test: `afenda/tools/tests/test_deploy_static.py`

**Interfaces:**
- Consumes:
  - `export_openapi_shell.py`, whose output line is `afenda-openapi: wrote <N> documents`;
  - `asset_rules.manifest_applications`;
  - the `api_diff check` CLI.

- [ ] **Step 1: Failing static test** `test_ci_regenerates_the_api_asset_and_gates_changes`.
  It asserts that `afenda-image.yml`:
  - uses `docker run -i` with `export_openapi_shell.py` on stdin;
  - checks the printed `N` equals the number of committed `*.json` files, and is greater
    than 0;
  - runs `git status --porcelain -- afenda/addons/afenda_api_docs/openapi`;
  - has a `timeout-minutes` on the step.

  It also asserts that `afenda-ci.yml` runs `git fetch --no-tags --depth=1 origin
  main:refs/remotes/origin/main` and `python -m afenda.tools.api_diff check --base-ref
  origin/main`.
- [ ] **Step 2: Implement.**
  - **The image job:**
    - fresh database `assets`;
    - the application list comes from
      `python3 -c "import sys; sys.path.insert(0, 'afenda/addons/afenda_api_docs'); from asset_rules import manifest_applications; …"`
      on the runner;
    - install `afenda_brand,afenda_runtime,afenda_api_docs,<apps>`;
    - `chmod -R a+w` the `openapi/` directory (the container user is `afenda`,
      `deploy/Dockerfile:86`);
    - `docker run -i … -v "$PWD/afenda/addons/afenda_api_docs/openapi:/out" -e OUT_DIR=/out
      -e ADDONS_ROOT=/opt/afenda/addons … odoo-bin shell … --no-http < afenda/tools/export_openapi_shell.py`;
    - assert the count;
    - fail with "the API asset is stale: download the `openapi-asset` artifact, or run the
      exporter (afenda/README.md), and commit" when `git status --porcelain` is non-empty;
    - upload `openapi/` as the artifact `openapi-asset`, so CI is a regeneration source;
    - step `timeout-minutes: 20`.
  - **Raise `ODOO_TESTS_MIN`** to 146 + 8 (Task 1) + (the final `afenda_api_docs` count −
    75). Confirm it with the Task 7 simulation, and cite the printed total in the comment.
  - **The CI job:** the fetch above, then the check. Write the three lists to
    `$GITHUB_STEP_SUMMARY`.
- [ ] **Step 3: Run the static test.** actionlint is optional, if installed.
- [ ] **Step 4: Commit** `[ADD] ci: regenerate the API asset and gate API changes`.

### Task 7: Documentation, handoff, final gates

**Files:**
- Modify: `afenda/README.md`, section "Documentation at /docs". It covers:
  - the error contract and the errors page;
  - the asset and how to regenerate it (the exporter command, or the CI artifact);
  - the version rule and the `api_diff` commands.
- Modify: `CLAUDE.md` Commands: add the export and `api_diff` commands, and note that a
  `[REBRAND]` apply or an upstream merge changes help text, so it must regenerate the asset
  (descriptive change, no version bump).
- Create: `docs/superpowers/handoffs/2026-09-26-api-assets.md`. It holds:
  - the phase 1 state;
  - the corrections filed (0001–0011);
  - AFD-ARCH-CORR-0008, the size budget, named for the owner;
  - phase 2 next.

- [ ] **Step 1: Write them.**
- [ ] **Step 2: Final gates, once each, citing the counts and the SHA:**
  - the tools suite;
  - `afenda_runtime`, `afenda_api_docs`, `afenda_brand` and `afenda_brand_digest` installed
    together (the CI shape);
  - a fresh-database simulation of the `afenda-image` Odoo steps plus the asset step;
  - `test_deploy_static`.
- [ ] **Step 3: Commit, then open the PR.** The PR text names AFD-ARCH-CORR-0008, the 1.5 MiB
  budget, and AFD-ARCH-CORR-0007, the areas, for the owner.
