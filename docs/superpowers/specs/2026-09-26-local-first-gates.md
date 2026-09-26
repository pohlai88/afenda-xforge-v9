# Local-first gates: one check, a push gate, and a faster CI

Status: direction approved by the owner on 2026-09-26 ("A + B"). This spec awaits the owner's
review before a plan is written. Evidence: the audit and research of the same day (numbers
below; sources in the research list at the end).

## Problem, measured

The repository's whole CI history (2026-09-22 → 26): 95 workflow runs, about 4.7 h of CI
wall-clock.

- **The loop is pushes, not re-runs.** Every run was a first attempt (`run_attempt` 1, 0 of 95).
  PR #5 took 7 pushes in 33 minutes, each firing all three workflows: 21 runs for one PR. PRs
  #2–#8: 19 pushes, 90 runs. Nothing requires a passing local check before a push, so a push is
  the cheapest way to find out, and CI becomes the test runner.
- **The image build is the cost.** `afenda-image`'s `docker build` job: median 294 s, max 575 s,
  and no cache of any kind. Every run rebuilds unchanged dependency layers (2–4 min).
- **One duplicate trigger.** `afenda-pr` fires on `edited` as well as `synchronize`, so one push
  plus a description update runs the same check twice on the same commit (PR #7: 4 runs, 2 SHAs).
- **The agent guardrail has holes** (`.claude/hooks/rerun_guard.py`):
  - keyed by session, so a sub-agent starts a fresh count;
  - matched on the exact command text, so `-v` or a reordered flag resets it;
  - blind to `git push` and to CI.
- **The evidence check trusts the text.** `afenda/tools/pr_evidence.py` accepts any hex string
  as the commit. A stale or copied commit id passes.

Rules that say "no trial and error" already exist in `CLAUDE.md`, the steward skill and the
orchestrate skill. They are prose; what they need is a mechanism.

## Decisions

### 1. One check command: `python -m afenda.tools.check`

A standard-library module that knows every gate, picks the ones the change needs, runs each once,
and prints one result table.

- **Scope.** It compares HEAD with the merge base against `origin/main`. It refuses to start
  while tracked files under `afenda .github .claude docs CLAUDE.md deploy` have uncommitted
  changes, because it certifies a commit, not a working tree. That is the rerun guard's scope:
  root `odoo/` and `addons/` stay out, since a rebrand apply leaves about 19,000 modified files
  there and a whole-tree status takes two minutes.
- **Gates it selects** (the same list CI runs):

  | Gate | When | Local cost |
  |---|---|---|
  | tools suite (`unittest discover afenda/tools/tests`) | always | ~50 s |
  | api contract (`afenda.tools.api_diff check --base-ref <merge base>`) | always | seconds |
  | pr-evidence self-test of the description file, if one is given | when `--pr-body` is passed | seconds |
  | the four AFENDA module suites (`/afenda_brand,/afenda_runtime,/afenda_api_docs,/afenda_brand_digest`) | anything under `afenda/addons/`, `deploy/Dockerfile`, `requirements.txt` | ~3–4 min |
  | the industry packs | `afenda/addons/afenda_industry_*` | ~1 min |
  | nginx -t | `deploy/nginx/**`, only when docker is present; otherwise reported as "CI only" | seconds |

- **Odoo database.** `--db` (default `afenda`, or `AFENDA_CHECK_DB`). The module suites install
  missing modules and update installed ones, so a fresh container works after the "first run" command.
- **Output.** One table: gate · command · printed result (the count line, verbatim) · commit.
  It can be pasted straight into the PR's Verification section.
- **The stamp.** On success it writes `.git/afenda-check/<tree sha>.json`: the gates, their
  printed counts, the commit and the time. `.git/` is shared by every session and sub-agent in the
  worktree and is never pushed. A failed run writes no stamp.
- **Single source for CI.** The gate list, the module list and the test floors
  (`ODOO_TESTS_MIN`, `PACK_TESTS_MIN`) live in `check.py`, so there is one source.
  - `afenda-ci`'s tools and api-contract jobs call `check.py` for their gate.
  - `afenda-image` keeps its in-image run (a fresh database, the `afenda_app` role and the
    image's venv are the point of that job), but reads the module list and floors from
    `check.py --print …` instead of its own copy.

### 2. The push gate: `.claude/hooks/push_gate.py`

A `PreToolUse` hook on `Bash` for every agent session and sub-agent in the repo:

- **Blocks `git push`** (any form except `--dry-run`, and pushes of tags only) unless a stamp
  exists for the tree of every commit being pushed. In practice that is the branch head's
  `HEAD^{tree}`. The message names the command to run: `python -m afenda.tools.check`.
- **No bypass by environment variable or flag.** A docs-only change passes through `check` in
  about a minute (tools suite plus api contract), so no exception is needed. A command that tries
  to switch the hook off is refused like any unstamped push.
- **GitHub file-writing tools are blocked** (`mcp__github__push_files`,
  `mcp__github__create_or_update_file`, `mcp__github__delete_file`). They write commits without
  git and would route around the gate; agents push with git only.
- **Fails closed on its own errors,** unlike the rerun guard. If it cannot compute the tree or
  read the stamp, the push waits. A push is the one action a false block costs minutes on,
  while a false pass costs a CI cycle.
- **Effect on the loop.** After a red CI run, the only way to push again is a new commit whose
  tree passed `check`. That is a diagnosed fix, never "push and see".

Humans get the same gate as an opt-in git hook (`git config core.hooksPath afenda/tools/githooks`,
a `pre-push` that runs the same stamp lookup). `--no-verify` can skip a git hook, so the real
guarantee for a human merge is the owner's required status checks (decision 6).

### 3. The rerun guard, hardened

`.claude/hooks/rerun_guard.py` keeps its rule (a gate's third run on an unchanged tree is
blocked) and its fail-open behaviour. It changes what "the same run" means:

- **Key.** The ledger moves from one file per session to `.git/afenda-rerun-ledger.json`, keyed
  by `(gate identity, tree fingerprint)`. A sub-agent inherits the count.
- **Gate identity is semantic.** It is the gate kind plus its sorted targets:
  - unittest: the module or discover path;
  - odoo-bin: the sorted `--test-tags` set;
  - `afenda.tools.check`: its selected gates.

  Verbosity, fail-fast, output redirection, env prefixes and flag order do not change it.
- **Coverage.** Adds `afenda.tools.check` and `pytest` to the recognised gates.

### 4. The evidence check verifies the commit

`pr_evidence.py` also requires at least one cited commit id to be a prefix of a commit in the PR
(`git rev-list <base>..<head>`, passed to the script through `env:` as `PR_COMMITS`, never through
`${{ }}` in a script). A copied id from another PR fails. The printed counts stay "cited, not
proven". Proving them would mean CI parsing its own logs, and the stamp plus a reviewer already
cover that.

### 5. A faster CI (the "B" half)

- **Image build cache.** `docker/setup-buildx-action` plus `docker/build-push-action` with
  `cache-from: type=gha` and `cache-to: type=gha,mode=max`, and `load: true` so the later steps
  still run the local image. Expected: the dependency layers come from cache on most runs, saving
  2–4 min per run. The acceptance measures it.
- **pip cache.** `actions/setup-python` with `cache: pip` and the tools requirements as the
  dependency path.
- **No double fire.** `afenda-pr` runs on `edited` only when the body changed
  (`if: github.event.action != 'edited' || github.event.changes.body != null`).
- **Unchanged.**
  - Concurrency with cancel-in-progress is already on all three workflows.
  - The tools matrix keeps 3.11 and 3.12 (a deliberate, recorded choice, and parallel, so it
    costs no wall-clock time).
  - Timeouts stay.

### 6. For the owner (GitHub settings; no agent can make these)

Branch protection on `main`: require `tools suite`, `tools suite (Python 3.12)`, `api contract`,
`nginx -t`, `docker build` and `pr evidence` (a skipped `docker build` reports success, per the
`changes` job), and "require branches to be up to date". A merge queue is not proposed (option
C, declined).

### 7. The written rules follow the mechanism

`CLAUDE.md` ("Execution discipline", "Pull requests") and the steward skill replace "run the
gates once before pushing" with "`python -m afenda.tools.check`, then push; the push gate
enforces it". The orchestrate skill's "gates once" step names the same command. Nothing else in
those files changes.

## Non-goals

- No automatic deploy (the owner removed it in PR #7) and no change to `deploy/redeploy.sh`.
- No merge queue, no cap on pushes per hour (option C).
- No attempt to make CI read the local stamp. CI re-verifies in its own environment, and the
  stamp only guarantees that a push was checked before it left.

## Acceptance

- `python -m unittest discover afenda/tools/tests` prints the previous 355 plus the new tests,
  OK. New tests cover:
  - `check`'s gate selection per changed path;
  - the refusal on a dirty tree;
  - the stamp written on pass and absent on fail;
  - the push gate on stamped, unstamped, `--dry-run` and bypass-attempt commands, and on the
    GitHub file-writing tools;
  - the guard's semantic identity (`-v` and a reordered flag count as the same gate) and its
    shared ledger;
  - `pr_evidence` with a foreign commit id.
- **Push gate, shown live:** in a cloud session, a `git push` on an unstamped tree is blocked with
  the message. After `python -m afenda.tools.check` passes, the same push goes through.
- **Image cache, measured:** on the PR that lands this, a second `afenda-image` run with an
  unchanged `deploy/Dockerfile` and `requirements.txt` finishes the `docker build` step at least
  60 s faster than the first (both durations quoted from the run logs).
- **Single trigger:** a description edit with no body change triggers no `pr evidence` run, and a
  body edit triggers exactly one.
- **One push:** the PR that lands this spec reaches green with one push after the spec and plan
  commits, using `check` before it. Any further push is named, with its cause, in the PR.

## Research list (2025–2026 sources)

- Job-level path gating so required checks still report: github.com/orgs/community/discussions/26251
- BuildKit GitHub Actions cache: docs.docker.com/build/cache/backends/gha/
- Same toolchain locally and in CI: oneuptime.com/blog/post/2026-07-28-same-toolchain-local-ci/view
- Claude Code hooks (PreToolUse blocking): code.claude.com/docs/en/hooks
- Flaky-test policy, no blind re-runs: tenki.cloud/blog/flaky-test-quarantine-github-actions
- Pre-push hooks are skippable with `--no-verify`, so server-side required checks stay the net:
  gitscripts.com/git-pre-push-hook

## Corrections after review (2026-09-26, owner: "proceed to implement")

The review in `reports/Gates CI and agent rules review.md` (local, not committed) checked this
spec against Claude Code's hooks and permissions docs and against git and Actions behaviour.
These corrections bind the plan; where they differ from the decisions above, they win.

1. **The push gate fails closed by its own code, not the harness.** A hook timeout (default 600 s)
   does not block, and any exit code other than 2 does not block. `push_gate.py` therefore:
   - runs every subprocess with a short timeout (5 s, as `rerun_guard.py` does);
   - wraps its whole body so any exception exits 2 with the reason.
2. **"No bypass" means no bypass inside the hook.** `claude --settings '{"disableAllHooks": true}'`
   can switch every hook off. For agents as for humans, the real backstop is required status checks
   (decision 6).
3. **The gate checks the tip tree of the ref being pushed.** The refspec is resolved with
   `git rev-parse`, including bare `git push`, `HEAD`, `HEAD:refs/heads/x`, `<sha>:main`, `+ref`,
   `--force-with-lease[=…]` and `--delete`. A delete or tag-only push needs no stamp. Anything that
   cannot be resolved is blocked.
4. **Residual risk, named.** A wrapper script, alias, Makefile target, or a raw `curl`/`gh api`
   write to GitHub is invisible to a PreToolUse hook on `git push`. Branch protection covers it.
5. **One shared git-identity helper.** `afenda/tools/_git_identity.py` provides the scoped tree
   fingerprint and the tree sha, used by `rerun_guard.py`, `check.py` and `push_gate.py`. It holds
   the one copy of the scoped path list.
6. **The image cache is measured, not assumed.**
   - Settings: `cache-to: type=gha,mode=max,scope=afenda-image`, `load: true`, `--progress=plain`.
   - The acceptance compares the `docker build` step time across two runs and reports the layers
     marked `CACHED`.
   - If the gha cache does not warm without a registry push (moby/buildkit#2887), the PR says so
     with the numbers. It does not add a registry.
7. **The `edited` filter is a job-level `if:`.** It is
   `github.event.action != 'edited' || github.event.changes.body != null`.
8. **`pr_evidence` reads the PR's commits from the GitHub API** (`GET /repos/{repo}/pulls/{n}/commits`
   with the job's `GITHUB_TOKEN` and `pull-requests: read`), not from `git rev-list`. The shallow
   checkout lacks the graph.
9. **The metric** is 23,291 files in `odoo/` and `addons/` after a rebrand apply (119 hand-authored,
   23,172 generated), not "about 19,000".
10. **Floors stay in the workflow.** CI keeps its own gate commands. A static test asserts that each
    CI command equals the command `check.py` runs for the same gate, so the two cannot drift.
    `check.py` does not own the floors.
11. **Folded in from the review:**
    - **Repairs:**
      - `corpus.py`'s default ref and the brand-image test that silently skips;
      - the superdesign skill's dangling references;
      - `launch.json` references;
      - `api_contract`'s push fetch fails open;
      - the steward skill says the required checks are not live yet;
      - `scan()` gets unit tests.
    - **Optimizations:**
      - sparse checkout for the `tools` and `api_contract` jobs, with no submodules in `tools`;
      - `lru_cache` on `icon_png`;
      - `permissions.deny` for edits to root `odoo/` and `addons/`;
      - `permissionMode: plan` for the librarian and the reviewer;
      - `model: sonnet` for the test runner;
      - the duplicated Environment section leaves `odoo-agent-rules.md`.
    - **Not adopted:**
      - the `code-review`, `commit-commands`, `hookify` and `pr-review-toolkit` plugins;
      - `claude-code-action` in `@claude`-mention mode;
      - `security-guidance`, pending a cost check;
      - moving CLAUDE.md sections into `.claude/rules/` (its own later plan).
