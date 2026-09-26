---
name: orchestrate
description: "Use in afenda-xforge-v9 whenever a unit of work has more than one task, review or gate — executing a plan, reviewing a branch, fixing a set of findings, preparing a PR — and before dispatching any sub-agent. It decides what runs in parallel (a conflict map), what starts first (the slowest real-environment signal), how problems are found (one parallel review sweep split by dimension) and fixed (one fix wave, one scoped re-review), and how tests are run (guard first, narrowest per edit, gates once, cited not re-run). Reach for it especially when the next step is 'review, fix, review again' or 'run it again to be sure'."
---

# Orchestrate

**Find every problem in one sweep, fix them in one wave, and never pay for the same signal
twice.**

`CLAUDE.md` → "Execution discipline" is binding; this skill is how an orchestrator meets it
when several agents, reviews or gates are in play. `.claude/skills/steward/SKILL.md` takes over
once a PR is open. Spec: `docs/superpowers/specs/2026-09-26-orchestration-discipline.md`.

The cost this prevents, measured on PR #5: four serial layers (task reviews → branch review →
fix wave → first real CI run), each discovered only after the previous one closed, and the
one problem only CI could show (a missing `--addons-path`) found last.

## 1. Conflict map — before any dispatch

Write a table: one row per task, with the files it writes, the shared resources it uses
(database name, HTTP port, the git index, a generated asset, a counted test suite), and what it
needs from another row.

- Rows that share nothing → dispatch in **one message**, in parallel.
- Rows that share a file or a generated output → serial, in dependency order.
- A shared *count* (the tools suite, an Odoo suite) is not a conflict: each lane names its new
  tests; the orchestrator runs the combined gate once at the end.
- Shared database or port → give each lane its own (`afenda_<lane>`, 8179/8189/8199); copy the
  filestore when cloning a database (`CLAUDE.md` → Gotchas).
- Commits from parallel lanes use `git commit --only -F msg -- <own paths>`, never a bare commit.

Record the table in the plan or the ledger. "They look independent" is not a map.

## 2. Slowest signal first

Some things only the real environment proves: a CI workflow, the Docker image, a fresh-database
install, the deploy path. Start them **on the first push that contains them** (a push itself needs the owner's standing
instruction for this branch, per `CLAUDE.md`'s stop list) — with
`workflow_dispatch` on the branch if no event would — and let them run while reviews and other
lanes run. Never leave the slowest signal for last.

## 3. One sweep, one fix wave, one re-review

**Sweep.** Dispatch the reviews as one parallel wave, one reviewer per dimension, all on the same
diff file, each writing its findings to its own file:

| Dimension | Asks |
|---|---|
| Spec compliance | every requirement present; nothing extra; rulings honoured |
| Correctness | edge cases, error paths, concurrency, the code's own contracts |
| Tests | each behaviour has a test that would fail without it; no vacuous assertion; counts collected (not silently dropped) |
| CI/local parity | every command CI runs, in CI's environment (see the steward skill's gap table) |
| Docs vs code | every command, path, constant and count a doc states, checked against the source |
| Security | auth, input handling, secrets, what a response discloses |

Small diffs may merge dimensions into fewer reviewers; never split one dimension across rounds.

**Rule.** When every reviewer has reported — not before — deduplicate, verify each load-bearing
claim against the source, and rule on every finding in one pass (fix now · park with reason ·
reject with evidence), one line each: decision · evidence · cost if wrong.

**Fix wave.** One dispatch per file-ownership group, parallel where the groups are disjoint,
carrying every ruled finding for those files. No fix goes out while a sweep is still reporting.

**Re-review.** One scoped re-review of the fix diff against the findings list only. New issues
outside the fix diff are recorded, not a reason for another sweep.

## 4. Tests

- **Guard first:** the test that fails for the named cause, run and seen failing (the RED line
  with its failure count), before the fix.
- **Narrowest per edit:** one test class or method, or one `afenda/tools/tests` module.
- **Gates once** per unit of work, at the end: `python -m afenda.tools.check` (the tools suite,
  the touched modules' Odoo suites), plus `scan_identity` and `corpus diff` when a rule changed.
- **Cite, don't re-run:** a passed gate is recorded as command · printed count · SHA and cited
  until something it covers changes. `.claude/hooks/rerun_guard.py` blocks the third run of a
  gate on an unchanged tree.
- A count that differs from the expectation is a finding to explain from the output, never a
  reason to run again.

## 5. Dispatch contents

Every dispatch carries: the task, the exact files it may write (and those it must not), the
acceptance check with its expected count, the rulings it depends on, and the report-file path.
Reports go to files; the reply is status, SHA, one count line, concerns. If a sub-agent has to
rediscover context, the dispatch was defective.

## Red flags

- "Review it, fix it, then review again to see what's left." → one sweep first.
- "CI will tell us once we're done." → start it now.
- "Let me re-run the suite to be sure." → cite the recorded count.
- "These two can run together" without a table. → write the map.
- A fix dispatched while a reviewer is still running.
