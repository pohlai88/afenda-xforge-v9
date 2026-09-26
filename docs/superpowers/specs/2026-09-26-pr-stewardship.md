# PR stewardship: one documented way from "PR opened" to "PR closed", enforced

Status: approved by the owner's instruction of 2026-09-26 ("open the PR and complete the entire
coding process until it is closed … find the correct way, document it, enforce it; no trial and
error"). The decisions below are the orchestrator's rulings under that instruction.

## Problem

`CLAUDE.md` binds every session to evidence-first work ("no trial and error", "test the edit,
not the world", "cite the printed count and the SHA"). Nothing carries that discipline across
the last mile — the pull request:

- No written procedure says what a PR must show before it merges, in what order its events are
  worked, how a CI failure is diagnosed, or when an agent must stop and report.
- The PR template is upstream Odoo's (a CLA line and three blank prompts); nothing asks for
  evidence.
- Nothing mechanical rejects a PR whose description claims "tests pass" without a printed count
  and a commit.
- `main` has no required status checks; that is a repository setting only the owner can change.

Measured cost on PR #5's branch: the first real `afenda-image` run failed on a missing
`--addons-path` that local runs could never reveal (`afenda/odoo.conf` supplies it). The fix
came from the job log in one pass, but the method used lived only in the session.

## Decisions

1. **The procedure is a repository skill,** `.claude/skills/steward/SKILL.md`. The Claude Code
   harness reads `steward/SKILL.md` from a PR's head branch before acting on CI or review
   events on a PR it drives, so the procedure reaches every agent without being re-explained.
   `CLAUDE.md` gains a "Pull requests" section that makes it binding on humans and agents alike.
2. **The PR template asks for evidence.** `.github/PULL_REQUEST_TEMPLATE.md` becomes AFENDA's:
   why, before, after, a `Verification` table (gate · command · printed result · SHA), owner
   decisions, and what was not verified. (This file is not under root `odoo/` or `addons/`; an
   upstream merge that touches it keeps AFENDA's side.)
3. **CI enforces the evidence.** A new workflow `afenda-pr.yml`, job `pr evidence`, runs on every
   pull request into `main`, including when its description is edited, and fails unless the
   description has a `Verification` section holding at least one printed test count (`Ran N
   tests` or `of N tests`) and at least one commit id (7–40 hex characters with at least one
   letter a–f, or a full 40-character id). The check is
   `afenda/tools/pr_evidence.py` (standard library only), unit-tested in the tools suite. The
   body reaches the script through `env:`, never through `${{ }}` inside the script.
4. **Merge method: rebase and merge,** as PRs #2–#4 were (each commit kept, author dates intact,
   the owner as committer). A PR merges only when the steward skill's "done" list holds.
5. **Required status checks are the owner's action.** Branch protection on `main` requiring
   `tools suite`, `tools suite (Python 3.12)`, `api contract`, `nginx -t` and `pr evidence` is
   what makes the checks binding on a human merge too (`docker build`, i.e. `afenda-image`, is
   not in that list: it runs only when a PR touches the image's inputs, so on a docs-only PR
   it never reports and a required check on it would block the merge forever). No agent can
   set it; the handoff lists it under "Waiting on the owner".

## Non-goals

- No bot that merges on green. Merging stays a deliberate act.
- No check on the *truth* of the cited numbers; reviewers compare them to the CI logs. The CI
  job enforces that evidence is cited, not that it is honest.

## Acceptance

- `python -m unittest discover afenda/tools/tests` prints the prior count plus the new tests, OK.
- On PR #5, `pr evidence` passes against the PR description, which carries a Verification table.
- `CLAUDE.md` names the steward skill as binding; the skill states the done list, the event
  order, the CI-failure procedure, the stop conditions, and the merge and post-merge steps.
