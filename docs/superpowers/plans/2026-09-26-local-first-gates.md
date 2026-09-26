# Local-first gates — implementation plan

Spec: `docs/superpowers/specs/2026-09-26-local-first-gates.md` (decisions 1–7 plus "Corrections
after review", which win where they differ). Owner: direction "A + B" approved, then "proceed to
implement" (2026-09-26). Branch `claude/superpowerskill-agent-setup-x5fcyv`, restarted from `main`
at 2354e4332.

## Global constraints

- `.venv/Scripts/python` only. The tools are standard library, except where a tool already uses a pinned dependency.
- Never edit root `odoo/` or `addons/`. Deploys stay manual. No merge queue, no push caps.
- Commits:
  - use Odoo tags;
  - `git commit --only -F <msg> -- <paths>`;
  - `git add` (`-f` under `.claude/`) a new file in the same shell call;
  - end with the two trailer lines (Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>;
    Claude-Session: https://claude.ai/code/session_01D9u4Ku5BM4uG3ooDBk15bB).
- Lanes do not push; only the orchestrator pushes, once.
- Each lane runs the narrowest test per edit and its own test modules once at the end, and quotes the printed "Ran N tests … OK" line.

## Shared interface (every lane builds against exactly this)

- `afenda/tools/_git_identity.py` (Lane A):
  - `SCOPED_PATHS = ("afenda", ".github", ".claude", "docs", "CLAUDE.md", "deploy")`;
  - `repo_root(cwd) -> Path | None`;
  - `tree_sha(root, rev="HEAD") -> str`;
  - `scoped_fingerprint(root) -> str` (HEAD sha + sha256 of scoped `git diff HEAD` and scoped
    `git status --porcelain`);
  - `scoped_dirty(root) -> list[str]` (tracked, modified paths in scope);
  - every git call has `timeout=5`.
- `python -m afenda.tools.check` (Lane A):
  - `[--base REF] [--db NAME] [--gate NAME ...] [--list]`.
  - Gates and their exact commands, as a module-level `GATES` dict:
    - `tools`: `python -m unittest discover afenda/tools/tests`;
    - `api_contract`: `python -m afenda.tools.api_diff check --base-ref <base>`;
    - `odoo`: `odoo-bin -c afenda/odoo.conf -d <db> -i <M> -u <M> --test-enable --test-tags "<tags>" --stop-after-init --http-port 8179`, with M the four AFENDA modules;
    - `packs`: the two industry packs, same shape;
    - `nginx`: docker `nginx -t` as in CI, or "CI only" without docker.
  - Selection from `git diff --name-only <merge-base(base, HEAD)>..HEAD`:
    - always `tools` and `api_contract`;
    - `odoo` for `afenda/addons/**`, `deploy/Dockerfile` or `requirements.txt`;
    - `packs` for `afenda/addons/afenda_industry_*/**`;
    - `nginx` for `deploy/nginx/**`.
  - Refuses (exit 2) when `scoped_dirty()` is non-empty, unless `--gate` is given.
  - Prints a Markdown table: gate · command · printed result (the count line verbatim) · commit.
  - On all-pass, writes `.git/afenda-check/<tree_sha>.json`
    (`{"tree","head","base","gates":[{"name","command","result"}],"passed":true,"time"}`).
  - Exit 0 on pass, 1 on a failed gate.
- `.claude/hooks/push_gate.py` (Lane A):
  - PreToolUse on `Bash` and on `mcp__github__push_files|mcp__github__create_or_update_file|mcp__github__delete_file`.
  - Blocks (exit 2, reason on stderr) a `git push` whose resolved tip tree has no passing stamp, and always blocks the three MCP tools.
  - Fails closed: any exception or timeout exits 2.

## Lanes (disjoint files; run in parallel)

| Lane | Owner | Files (only these) |
|---|---|---|
| A — gate core | general-purpose (most capable) | new `afenda/tools/_git_identity.py`, `afenda/tools/check.py`, `.claude/hooks/push_gate.py`, `afenda/tools/tests/test_check.py`, `afenda/tools/tests/test_push_gate.py`; edit `.claude/hooks/rerun_guard.py`, `afenda/tools/tests/test_rerun_guard.py`, `.claude/settings.json` |
| B — CI | general-purpose | `.github/workflows/afenda-ci.yml`, `afenda-image.yml`, `afenda-pr.yml`, `afenda/tools/pr_evidence.py`, `afenda/tools/tests/test_pr_evidence.py`, `afenda/tools/tests/test_deploy_static.py` |
| C — tool repairs | general-purpose | `afenda/tools/corpus.py`, `afenda/tools/tests/test_corpus.py`, `afenda/tools/tests/test_brand_images.py`, `afenda/tools/xforge_icons_v3/render_png.py`, `afenda/tools/tests/test_xforge_v3.py` (only if needed), `afenda/tools/scan_identity.py` (only if `scan()` needs a seam), `afenda/tools/tests/test_scan_identity.py` |
| D — rules and agents | general-purpose | `CLAUDE.md`, `.claude/odoo-agent-rules.md`, `.claude/skills/{steward,orchestrate,afenda-superdesign}/SKILL.md`, `.claude/agents/odoo-{docs-librarian,reviewer,test-runner}.md` |

### Lane A tasks

1. `_git_identity.py` and its tests.
2. `rerun_guard.py`:
   - ledger shared at `.git/afenda-rerun-ledger.json`, keyed `(gate identity, scoped fingerprint)`;
   - gate identity is semantic: unittest → module or discover path; odoo-bin → sorted `--test-tags`; `afenda.tools.check` → its gates; plus `pytest`. Flags `-v`/`-q`/`--failfast`, redirections and env prefixes are ignored;
   - uses `_git_identity`;
   - still fails open;
   - the docstring stops citing "CLAUDE.md's Lane A";
   - prunes ledger entries older than 7 days.
3. `check.py`, including the static test that each CI command in `afenda-ci.yml` equals `GATES[...]`'s command (`tools`, `api_contract`).
4. `push_gate.py` with tests for:
   - stamped, unstamped, `--dry-run`, `--delete` and tag-only pushes;
   - `+ref`, `--force-with-lease=x:y`, `HEAD:refs/heads/x`, a bare `git push`, and an unresolvable ref (blocked);
   - `git -C path push`;
   - the three MCP tools blocked;
   - an exception → exit 2.
5. `.claude/settings.json`:
   - PreToolUse `push_gate.py` beside `rerun_guard.py` (Bash), plus a second matcher for the three MCP tools;
   - `permissions.deny` on Edit/Write for root `odoo/**` and `addons/**`, using the path syntax code.claude.com/docs/en/permissions documents for "relative to project root". Verify the syntax from the docs, then probe once: a Write to `odoo/__probe__` must be refused. If it is not, delete the file and report.

Acceptance: `.venv/Scripts/python -m unittest afenda.tools.tests.test_check afenda.tools.tests.test_push_gate afenda.tools.tests.test_rerun_guard` prints `Ran N tests … OK`. One live run of `python -m afenda.tools.check --db afenda_t7` on a clean tree selects the right gates, prints the table, and writes a stamp. The Odoo gate prints `0 failed, 0 error(s) of 190 tests`.

### Lane B tasks

1. `afenda-ci.yml`:
   - `tools` and `api_contract` use a cone sparse checkout (`afenda`, `deploy`, `.github`, and the one `addons/web/static/img` path a test reads; verify by grep what the tools tests open under `odoo/` or `addons/`);
   - `tools` drops `submodules: true`;
   - the `api_contract` push fetch fails open like `afenda-image.yml`'s `changes` job;
   - `actions/setup-python` gets `cache: pip` with the tools requirements;
   - gate command strings are unchanged.
2. `afenda-image.yml`: `docker/setup-buildx-action@v3` + `docker/build-push-action@v6` (`context: .`, `file: deploy/Dockerfile`, `tags: afenda/xforge:ci`, `load: true`, `cache-from: type=gha,scope=afenda-image`, `cache-to: type=gha,mode=max,scope=afenda-image`), with plain progress. Nothing else changes.
3. `afenda-pr.yml`:
   - job-level `if: github.event.action != 'edited' || github.event.changes.body != null`;
   - `permissions: pull-requests: read`;
   - a step fetches the PR's commit shas from the API into `PR_COMMITS` (through `env`, never `${{ }}` in `run:`).
4. `pr_evidence.py`: when `PR_COMMITS` is set, at least one cited id must be a prefix of one of them, or it fails naming the ids; unset keeps today's behaviour.
5. Static tests in `test_deploy_static.py` for each change; `test_pr_evidence.py` for the commit rule.

Acceptance: `.venv/Scripts/python -m unittest afenda.tools.tests.test_deploy_static afenda.tools.tests.test_pr_evidence` → `Ran N tests … OK`; every workflow parses with `yaml.safe_load`.

### Lane C tasks

1. `corpus.py`: the default `--ref` and the docstring example become `archive/upstream-19.0`. Add a test that the argparse default resolves with `git rev-parse --verify` (skip if the ref is absent, with a reason naming the fetch command).
2. `test_brand_images.py`: the ref becomes `archive/upstream-19.0`. The previously skipped assertion must now run; if it fails, report the finding rather than weaken it.
3. `render_png.py`: `functools.lru_cache(maxsize=None)` on `icon_png` (callers only read the image; confirm, or return a copy).
4. `test_scan_identity.py`: tests of `scan()` on a temp tree:
   - a genuine hit is reported;
   - an ALLOW line is not;
   - the path exclusions are skipped.

Acceptance: each touched test module once, plus the full tools suite once, `Ran N tests … OK`. Record `test_xforge_v3` before and after, in seconds.

### Lane D tasks

1. `CLAUDE.md`:
   - the metric: 23,291 / 119 / 23,172;
   - drop the nonexistent "odoo-afenda" launch config;
   - "Pull requests" and "Execution discipline": run `python -m afenda.tools.check` before a push; the push gate enforces it; the stamp lives in `.git/afenda-check/`;
   - Gotchas: the push gate, `disableAllHooks` is not a licence, branch protection is the backstop;
   - the fingerprint scope names `afenda/tools/_git_identity.py` as the single copy.
   - Keep under 219 lines (net-zero or smaller).
2. `.claude/odoo-agent-rules.md`: the Environment section becomes one line pointing at CLAUDE.md; drop the launch.json mention.
3. `steward/SKILL.md`:
   - the required-checks list is the intended owner setting, not live until the owner sets it;
   - "gates once" is `python -m afenda.tools.check`.
4. `orchestrate/SKILL.md`: its gates step names the same command.
5. `afenda-superdesign/SKILL.md`: replace the two dangling `afenda-odoo-dev` references with `.claude/odoo-agent-rules.md` and `superpowers:verification-before-completion`.
6. Agents:
   - `odoo-docs-librarian.md` and `odoo-reviewer.md`: `permissionMode: plan`;
   - `odoo-test-runner.md`: `model: sonnet`.

Acceptance: `grep -rn "afenda-odoo-dev\|launch.json\|19,000" CLAUDE.md .claude` prints nothing; `wc -l CLAUDE.md` ≤ 219.

## Then (orchestrator)

1. **Gates once on the combined head:**
   - `python -m afenda.tools.check --db afenda_t7`, which runs the tools suite and api contract, plus `odoo` if selected;
   - `scan_identity` is not needed (no rule changed).
2. **One review sweep** split by dimension (hooks and check correctness · CI YAML · docs consistency) → one fix wave → a scoped re-review.
3. **One push, gated by the new push gate itself.** Open the PR with the Verification table from `check`'s output.
4. **Watch CI.** On the image job, record the `docker build` step time. Merge after the owner's go-ahead.
