# AFENDA domain cutover and gate hardening — implementation plan

Spec: `docs/superpowers/specs/2026-09-23-afenda-platform-architecture.md`
Date: 2026-09-23. Branch: `afenda/deidentify-phase1` (renamed `main` on 2026-09-25).

## Context

The real product domain arrived (`www.nexuscanon.com`), replacing the `afenda.app`
placeholder. `9b6cf8325` changed `BRAND["domain"]`, the three manifests and the tests, but
**1,822 files under `addons/` and `odoo/` still carry the old domain and nothing will fix
them**: the rebrand engine matches only `odoo.com` (`afenda/tools/rules.py:51`), and a
full-tree dry run with the new value reported `0 total (would apply)`. The engine is
converged, so changing an input is a no-op on output it already produced.

Verifying that exposed three further defects, all in the same family — a gate or a review
step that cannot see what it is supposed to protect.

## Global constraints (binding on every task)

- Odoo 19.0 only. Root `odoo/` and `addons/` are **generated output**: never hand-edit
  them. Brand text changes through `afenda/tools/` rules, reviewed on the corpus, then
  applied once.
- `.venv/Scripts/python` only. Never the global interpreter.
- Stage explicit paths. Never `git add -A` or `git commit -am`. Use
  `git commit --only -F msgfile -- <paths>`.
- Commit subjects use Odoo tags. **Generated output is `[REBRAND]`**, never `[FIX]`.
- Read the printed test count, never the exit code — `log_level = warn` silences a passing
  Odoo run.
- Gates that must hold at the end: tools suite **≥ 101 OK**; `scan_identity` at its
  baseline with **delta +0** (the baseline may only move in the same commit that changes
  it, with the new value written into `scan_identity.py`).
- One owner per file. Tasks are dispatched serially; no two implementers run at once.

## Rulings made up front

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| R1 | Reach the 1,822 files with a **one-shot superseded-domain rule**, not by re-deriving from upstream | Re-derivation is the better answer but is blocked: the clone is shallow and `upstream-19.0` is an orphan root with no merge base. The superseded-value pattern is already proven twice in this repo (`_SUPERSEDED_EMAIL_COLORS`, `_SUPERSEDED_LOGO_SHA256` in `afenda_brand/hooks.py`) | A temporary rule outlives its purpose. Mitigated by Task 1 requiring a removal note naming the condition for deletion |
| R2 | Fix `corpus.py`'s output encoding rather than documenting `PYTHONUTF8=1` as a workaround | It is the command `CLAUDE.md` mandates before any rule change; a review step that crashes is not a review step | Trivial — a one-line I/O change |
| R3 | Adopt the evidence hierarchy and the correction-ledger format into `.claude/odoo-agent-rules.md` | That file is the one all six `odoo-*` sub-agents read; rules placed anywhere else do not bind them | Rules nobody follows. No code risk |
| R4 | Fix all three `guides.xml` defects together, not just the manifest | Fixing the manifest alone yields a loaded-but-unreachable template — a change that looks done and is not | Wasted round trip |

---

## Task 1: Reach the 1,822 files carrying the superseded domain

Files: `afenda/tools/rules.py`, `afenda/tools/tests/test_rebrand.py`,
`afenda/tools/tests/corpus/golden.txt`, plus the rendered output under `addons/` and `odoo/`.

1. Add a rule named `superseded_domain` to `RULES` in `afenda/tools/rules.py` that rewrites
   the previously-shipped brand domain to the current `brand["domain"]`. Source the old
   value from an explicit module-level tuple, e.g.
   `_SUPERSEDED_DOMAINS = ("afenda.app",)`, so the list is the record of what has shipped.
   Match the bare host with a word boundary so `accounts.afenda.app`, `jane@afenda.app` and
   `https://www.afenda.app/x` are all reached. Do **not** match the current domain — a rule
   that rewrites the current value loops forever and must be impossible by construction.
2. Comment it in the same voice as `_SUPERSEDED_EMAIL_COLORS`
   (`afenda/addons/afenda_brand/hooks.py`): why it exists, that it is migration-local, and
   the condition under which it is deleted (no tree still carries the old value).
3. Tests in `afenda/tools/tests/test_rebrand.py`: the old bare host, a subdomain form, an
   email form, and a `www.` URL form each become the current domain; and the **current**
   domain is left untouched (the anti-loop assertion). Derive expectations from `BRAND`, as
   the file now does — never a literal.
4. Review before applying, in this order, and report each result:
   `python -m afenda.tools.corpus diff` → expect only old-domain lines to change;
   `python -m afenda.tools.corpus golden`; `python -m afenda.tools.rebrand` (dry run, report
   the total); `python -m afenda.tools.rebrand --apply`;
   `python -m afenda.tools.scan_identity` (must hold at baseline, delta +0 — the old domain
   is not an Odoo identity string, so this number must not move).
5. Confirm `grep -rl "afenda\.app" addons/ odoo/ | wc -l` returns **0**, and that a second
   `rebrand` dry run returns `0 total` (idempotence).
6. Two commits, explicit paths: `[IMP] afenda/tools: rewrite the superseded brand domain`
   for tools and tests, then `[REBRAND] carry the tree to the nexuscanon.com domain` for the
   rendered output under `addons/` and `odoo/`.

## Task 2: Make `corpus diff` runnable on Windows

Files: `afenda/tools/corpus.py`, `afenda/tools/tests/test_corpus.py`.

`python -m afenda.tools.corpus diff` dies with
`UnicodeEncodeError: 'charmap' codec can't encode character 'ỗ'` at `corpus.py:123`,
because the corpus holds non-Latin text and Windows stdout is cp1252. `CLAUDE.md` mandates
this command before every rule change, so on this platform the documented review step
cannot run.

1. Write the diff to stdout as UTF-8 regardless of the console encoding — reconfigure the
   stream or write bytes. Do not require the caller to set `PYTHONUTF8`.
2. A test that fails on the current code: feed content containing a non-Latin character
   (`ỗ` is the real one) through whatever function the CLI uses to emit, and assert it
   survives. If the emit path is inseparable from `main`, refactor the write into a small
   named function and test that.
3. Verify by running `python -m afenda.tools.corpus diff` with **no** `PYTHONUTF8` set.
4. Commit: `[FIX] afenda/tools: let corpus diff run where stdout is not UTF-8`.

## Task 3: Adopt the evidence hierarchy and the correction ledger

File: `.claude/odoo-agent-rules.md` (a dotfile — needs `git add -f`).

1. Add an **evidence hierarchy** section, in descending authority: (1) this fork's source at
   the release SHA — highest authority for runtime behaviour; (2) observed execution or test
   output from that SHA; (3) AFENDA specs and ADRs — normative intent, which must cite (1)
   or (2) for any load-bearing claim; (4) official Odoo 19 documentation — intended
   behaviour and operational guidance; (5) upstream Odoo source — comparison and upgrade
   analysis, never assumed identical to this fork; (6) external articles and forum answers —
   context only, never authority.
2. State the required shape for a load-bearing claim: `claim → afenda file:path:line →
   observed behaviour → conclusion`, and name the anti-pattern it replaces
   (`claim → external URL → assume the fork behaves the same`).
3. Add the **correction ledger** format, for retracting a claim rather than quietly editing
   it: an `AFD-ARCH-CORR-nnnn` id, `previous_claim`, `evidence` as a list of
   `path:line`, `disposition` (RETRACTED / AMENDED), `replacement`, `introduced_in`.
4. Add the hard metric rule: **no report, release gate or architectural metric may combine
   authored and derived deltas into one "changed files" number.** Authored delta is what
   humans changed; derived delta is what the compiler generated. `23,291` is a distribution
   footprint, not a complexity measure.
5. Commit with `git add -f`: `[IMP] .claude: evidence hierarchy and the correction ledger`.

## Task 4: Make the generated guides reachable

Files: `afenda/addons/afenda_api_docs/__manifest__.py`,
`afenda/addons/afenda_api_docs/controllers/landing.py`,
`afenda/addons/afenda_api_docs/tests/` (new or extended).

Three defects compound here; fixing any one alone leaves the guides invisible.

1. `views/guides.xml` is git-tracked and is `afenda/tools/build_docs.py`'s output, but
   `__manifest__.py:14` is `"data": ["views/landing.xml"]` — the templates never load. Add it.
2. `controllers/landing.py:11-16` routes both `/docs` and `/docs/<path:subpath>` to one
   handler that always renders `afenda_api_docs.landing`. Dispatch a subpath to its guide
   template when one exists, and keep the landing page for `/docs` itself. A missing guide
   must 404 rather than silently render the landing page.
3. `build_docs.py:5` claims a `test_guides_in_sync` test that **does not exist** — the
   string appears nowhere but in its own docstring. Write it: regenerate to a temp location
   and compare against the committed `views/guides.xml`, so a hand-edit or a stale
   regeneration fails. It needs no database, so prefer `afenda/tools/tests/`.
4. A route test asserting a guide URL returns 200 and contains that guide's `<h1>`, and that
   an unknown subpath returns 404.
5. Verify with the Odoo suite for `/afenda_api_docs` — read the printed count.
6. Commit: `[FIX] afenda_api_docs: load the generated guides and serve them`.

---

## Verification (whole branch, at the end)

```bash
.venv/Scripts/python -m unittest discover afenda/tools/tests          # >= 101 OK
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda \
  -u afenda_brand,afenda_api_docs,afenda_brand_digest --test-enable \
  --test-tags "/afenda_brand,/afenda_api_docs,/afenda_brand_digest" \
  --stop-after-init --http-port 8179                                   # read the count
.venv/Scripts/python -m afenda.tools.scan_identity                     # baseline, delta +0
grep -rl "afenda\.app" addons/ odoo/ | wc -l                           # 0
```

The Odoo suite needs port 8179 and the dev database; nothing else may hold it during the run.
