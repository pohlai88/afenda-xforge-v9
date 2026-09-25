# Handoff: cloud session of 2026-09-25 → the next local session

Read this before starting work on a local checkout. It records what a Claude Code on the web
session did, the owner's decisions, what is waiting on the owner, and what is still open. Its
progress ledger lived in the cloud container and is gone; this file replaces it. Where it
disagrees with the tree, the tree wins. Correct this file rather than work around it.

## Start here (local)

1. `git fetch origin && git checkout main && git pull --ff-only`. `main` is the only product
   branch.
2. Confirm PR #4 is merged (it carries this file). If it is still open, check its CI on GitHub
   before building on it.
3. The superpowers plugin is enabled for the project (`.claude/settings.json`). Accept the
   install prompt. `CLAUDE.md` → "Superpowers skills" says which skills to use and where
   `CLAUDE.md` overrides them.
4. `.claude/hooks/session-start.sh` is for cloud sessions only and exits at once locally. Your
   Windows setup (`.venv/Scripts/python`, PostgreSQL on 5444) is unchanged.

## What landed on `main`

| PR | What |
|---|---|
| #2 | Superpowers plugin enabled; the cloud SessionStart hook; the "Superpowers skills" and "Cloud sessions" sections of `CLAUDE.md` |
| #3 | The industry packs finished; the generated API reference; Python 3.12 CI; CI and doc fixes (below) |
| #4 | `afenda_api_docs` installed in production; automatic deploys; this handoff |

### Industry packs (`afenda_industry_base`, `afenda_industry_bakery`)

- **State:** restored unchanged from the tag `archive/industry-packs-wip`, then plan Tasks 4–7
  finished (`docs/superpowers/plans/2026-09-24-afenda-industry-packs.md`).
- **Review:** `odoo-reviewer` → fix round → scoped re-review, verdict merge. Spec deviations are
  recorded in `docs/superpowers/specs/2026-09-24-afenda-industry-packs-design.md`:
  - no `hr.employee` demo (`hr` is not a dependency);
  - no POS-session demo;
  - one-company BoM headers accepted under ruling 1.
- **Install order:** the pack refuses a company with no chart of accounts
  (`hooks.py`, `_check_accounting_is_set_up`). Install `account` in one run and the packs in a
  later one. The spec's "Acceptance" section has the exact commands.
- **Tests:** 17 (base 4, bakery 13).

### API reference (`afenda_api_docs`, plan `docs/superpowers/plans/2026-09-23-afenda-api-docs.md`)

- **Routes:**
  - `/docs/openapi.json`: OpenAPI 3.1, `auth='user'`, per app via `?app=`, generated from the
    live registry.
  - `/docs/api`: vendored Redoc 2.5.4. Its sha256 is pinned in `static/lib/redoc/README.md`.
- **Security:**
  - Redoc runs with `sanitize="true"`. That was a stored-XSS fix: field help and docstrings had
    rendered as raw HTML.
  - CSP `img-src 'self' data:; frame-ancestors 'self'`.
  - The JSON is sent with `Cache-Control: private, no-store`.
- **Cache:** the document is cached per caller in `models/api_docs.py` (`ormcache` on app, lang,
  su, groups, company, allowed companies).
- **Guides:**
  - Help links shaped `/docs/19.0/…/page.html` now reach their guide.
  - Only QWeb views named `afenda_api_docs.guide_*` can render.
  - A page with no guide redirects to `/docs`.
- **Tests:** 75.

### CI (`.github/workflows/`)

- `afenda-image` also runs on pull requests. Its path filter lists every Dockerfile `COPY` source,
  plus `.dockerignore` and the workflow itself.
- It runs the AFENDA module suites (floor 146), then `account`, then the pack suites (floor 17),
  sharing one data directory across the runs.
- `afenda-ci`: the tools suite runs on 3.11 and 3.12. The 3.11 check keeps its name
  `tools suite`.
- `afenda/tools/requirements.txt` pins Pillow per Python tier: 9.4.0 below 3.12, 10.2.0 on 3.12.
  All 126 generated images were byte-identical across the two, and equal to the committed files.
  That was measured on Linux only.
- `afenda-deploy` is new (see "Waiting on the owner").

### Numbers to expect (read the printed line, never the exit code)

| Suite | Count |
|---|---|
| `afenda_api_docs` + `afenda_brand` + `afenda_brand_digest` + `afenda_runtime`, installed together | `0 failed, 0 error(s) of 146 tests` |
| `afenda_industry_base` + `afenda_industry_bakery` | `of 17 tests` |
| `afenda_api_docs` alone | `of 75 tests` |
| tools suite | `Ran 278 tests … OK (skipped=1)` |

**Local trap:** `afenda_brand`'s `test_every_auth_page_is_one_poster` fails on a database where
`afenda_runtime` is not installed. The request-access link shows only when signup is closed, and
`afenda_runtime` closes it. `afenda_brand`'s `/docs` test likewise needs `afenda_api_docs`. So
install all four AFENDA modules in your `afenda` database, as CI does, before reading an
`afenda_brand` failure as a regression.

## Owner decisions (binding)

- **API docs live, guides not written.** `afenda_api_docs` joins `MODULES` in `deploy/init.sh`.
  Hand-written guides were **rejected**: do not author guide pages. The one existing guide
  (`applications/general/users.md`) stays; every other help link redirects to `/docs`.
- **Automatic deploys.** A push to `main` that passes both CI workflows deploys itself (below).
- **G2** (S3 attachments, Redis sessions, a separate cron service) waits. The platform spec is not
  approved for implementation. Revisit it when a second or third paying tenant or an uptime
  promise is near.
- **The `online_jobs` icon is closed as not applicable.** The manifest names an app this tree
  does not ship.

## Waiting on the owner (no agent can do these)

1. **One-time automatic-deploy setup:** `deploy/README.md` → "Automatic deploys".
   - Run `./redeploy.sh` once by hand on the host. This also puts `/docs` live.
   - Create the restricted key.
   - Add the `production` environment's four secrets in GitHub.
   - Until then, `afenda-deploy` ends each run with a "not set up yet" notice.
2. **The first automatic deploy** is the first real test of the SSH leg. The cloud sandbox had no
   sshd, so `ci-redeploy.sh` was tested only against stand-ins. Read its log under Actions →
   afenda-deploy.
3. **The live admin password:** empty `secrets/admin_password` on the host once it is spent
   (`deploy/secrets/README.md`). No record says this was done.
4. **`catchall@nexuscanon.com`** has no mailbox yet (Zoho).

## Open, repo-only (none started; pick up with the normal plan → review loop)

- **Budget:** the `base` app's OpenAPI document is 995 KiB against the 1 MiB test budget. The next
  addition to every operation crosses it. Narrow the method set or raise the budget with a reason.
- **Redoc design tokens:** the spec says `/docs/api` uses the web client's design tokens. It still
  uses Redoc's default theme (deferred as cosmetic).
- **No browser check of Redoc sanitising.** The proof is the attribute test plus the bundle code
  path (`Gw` → `Kw` → `this.sanitize=Ei(...)` → DOMPurify).
- **Industry-pack tests:**
  - `test_install_without_chart_of_accounts_names_this_pack` calls
    `_check_accounting_is_set_up` directly, so removing its call from `post_init_hook` would go
    unnoticed.
  - The hook's message uses `env._`, so it is always English on a UI install. There is no
    `i18n/` yet.
- **Test imports:**
  - `afenda/addons/afenda_brand/tests/test_branding.py:26` imports `afenda.tools` at module
    level. Where the repo root is not on `sys.path`, the whole test package fails to import. The
    same issue was fixed in `afenda_api_docs/tests/test_identity.py` with a `skipTest`.
  - `afenda_api_docs` tests use `auth_signup`, `mail` and `portal` methods that reach the module
    only through `afenda_brand`'s dependencies.
- **Platform-spec defects still open** (dated status at the top of its "Defects found while
  verifying"):
  - Scan scope beyond `addons/` and `odoo/`. `doc/`, `setup/` and `debian/` hold 1,177 hits,
    mostly CLA records and packaging; widening needs an allowlist design.
  - The Odoo image on Python 3.12 / `ubuntu:noble`.
  - **The Windows-side Pillow determinism hash.** A local Windows session is the one place to
    close it:
    1. run the same 126-image render on Windows under 3.11 + 9.4.0;
    2. compare its hashes with the committed files;
    3. record the result in the spec.
- **Stale plan text:** the historical per-task "11 tests" lines in the pack plan's Task 5 and 6
  sections were left as written. The final counts are updated.

## Where things are

- **Plans and specs:** `docs/superpowers/plans/`, `docs/superpowers/specs/`.
- **Deploy runbook:** `deploy/README.md`. Its "Upgrades" section now says a module newly added to
  `MODULES` is installed on the existing database.
- **Cloud environment:** `CLAUDE.md` → "Cloud sessions" and `.claude/hooks/session-start.sh`.
