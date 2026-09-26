# Orchestration discipline: find every problem in one sweep, fix once, never rerun blind

Status: approved by the owner's instruction of 2026-09-26 ("create a skill and enforce the
parallel agents … when no conflicts, the best practice of review code, test … do not keep
starting from the beginning and rerun … find out all the problems and resolve once").

## What went wrong (measured on PR #5's branch)

Problems were found one layer at a time, each layer only after the previous fix landed:

| Order | Layer | Found | Could it have run earlier? |
|---|---|---|---|
| 1 | per-task review (7 tasks) | per-task defects | — |
| 2 | Task 7 review + whole-branch review | 4 Important, 4 Minor (docs vs code, gate gaps) | yes: in parallel with Task 7, and its dimensions in one wave |
| 3 | fix wave + scoped re-review | all addressed | — |
| 4 | first real `afenda-image` run | missing `--addons-path` in the exporter call | yes: CI could have run on the first push of Task 6 |

Layer 4 was discoverable only by the real environment, and it ran last. Every earlier layer
was a sequential round trip that paid the full context cost again.

## Decisions

1. **A repository skill, `.claude/skills/orchestrate/SKILL.md`, is the method** for any unit of
   work with more than one task, review or gate. Its rules:
   - **Conflict map before dispatch:** tasks × files (and databases, ports, the git index); rows
     that share nothing run in one message, in parallel; rows that share anything run serially.
   - **Slowest signal first:** anything only the real environment can prove (a CI workflow, the
     image build, the deploy path) is started on the first push that contains it — by
     `workflow_dispatch` if needed — and runs while reviews run.
   - **One sweep, then one fix wave:** reviews run as one parallel wave split by dimension
     (spec compliance; correctness; tests; CI/local parity; docs-vs-code; security), each
     writing findings to a file; the orchestrator deduplicates and rules on all of them, then
     dispatches one fix wave (split by file ownership, parallel where disjoint), then one scoped
     re-review. No fix is dispatched while a sweep is still reporting.
   - **Tests:** guard first (RED with its failure count), the narrowest run per edit, gates once
     per unit of work, a passed gate is cited (command · count · SHA), never re-run.
2. **The rerun rule is enforced by a hook.** `.claude/hooks/rerun_guard.py`, a `PreToolUse`
   hook on `Bash`, blocks a gate command (a test suite, `api_diff`, `corpus`, `scan_identity`,
   `pr_evidence`) the third time it is issued in one session on an unchanged tree (same `HEAD`
   and the same scoped working-tree diff). CLAUDE.md already says "about to run the same command
   a third time with no code change in between? Stop and report"; the hook makes that
   mechanical. It fails open on any internal error, so it never blocks unrelated work.
3. `CLAUDE.md` makes the skill binding next to the steward skill.

## Non-goals

- No automatic parallelism: dispatching stays the orchestrator's act; the skill says when.
- The hook does not judge whether a first or second run was needed; it only stops the third.

## Acceptance

- The hook's unit tests (in the tools suite) show: a non-gate command passes; a gate command
  passes twice and is blocked the third time on the same tree; a changed tree resets the count;
  malformed input fails open.
- The skill states the conflict map, slowest-signal-first, one-sweep/one-fix-wave, the review
  dimensions and the test tiers; `CLAUDE.md` names it as binding.
