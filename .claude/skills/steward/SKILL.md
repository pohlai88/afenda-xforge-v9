---
name: steward
description: "Use when a pull request into main in afenda-xforge-v9 is opened, receives a CI result, a review, a merge conflict or a check-in, or is about to be merged — by any agent or person driving it. It is the one procedure from 'PR opened' to 'PR closed': what done means, the order events are worked, how a red check is diagnosed without trial and error, when to stop and report, and how the merge and the post-merge steps go. Reach for it especially when a check is red and a quick re-run or a speculative push is tempting."
---

# PR steward

**A pull request is driven, not waited on, and every move on it is backed by evidence.**

`CLAUDE.md` → "Execution discipline" binds every session; this skill applies it to the pull
request. Where the two differ, `CLAUDE.md` wins. Its stop-before-push rule stands: every push
below happens only under the owner's standing instruction to drive this PR (given for PR #5 on
2026-09-26); without one, stop and ask before the first push. Spec:
`docs/superpowers/specs/2026-09-26-pr-stewardship.md`.

## Done — the PR merges only when all of these hold on its current head commit

1. **CI green on that exact SHA**: `afenda-ci` (`tools suite`, `tools suite (Python 3.12)`,
   `api contract`, `nginx -t`), `afenda-pr` (`pr evidence`), and `afenda-image` (`docker build`:
   always required; skipped counts as passed — its own `changes` job decides from the diff
   whether to run the real build or skip it, and GitHub reports a skip as success). A green run
   on an older SHA proves nothing about the head. This list is the intended required-checks
   setting on `main`'s branch protection; until the owner sets it, nothing but this skill and
   the local push gate enforces it.
2. **No merge conflict** with `main`.
3. **No open review thread** waiting on the PR's side: every one is fixed and resolved, or
   answered with a reason.
4. **The description is current**: its `Verification` table cites the printed counts and the
   SHAs of the last gate runs (the `pr evidence` check enforces that they are cited; the
   reviewer compares them with the CI logs).
5. **The owner asked for it to merge**, or the session holds a standing instruction to finish
   the PR. An agent never merges on its own initiative.

## Order of work on every event or check-in

Look at the whole PR on its current head (merge state, every check, every open thread), then:

1. **Merge conflict** → merge `main` into the branch (never rebase or force-push a branch
   someone else pushed to), regenerate generated files with their tools (the OpenAPI asset
   with the exporter, never by hand), run the gates the conflicted paths touch, push once.
2. **A red check** → the procedure below.
3. **Review comments** → fix what is small and local; answer what is not with a proposal;
   resolve what you fixed.
4. **All green, nothing open** → update the description's Verification table if a push landed
   since it was written, then merge per "Merge".

A red check or a conflict is never "waiting on review". Doing nothing about one is not an
option on any event.

## A red check: diagnosis before any edit

1. **Read the failing step's log** (the job log, not the summary). Quote the line that failed:
   the traceback's last frame, the `::error::` line, or the assertion. No log line, no
   diagnosis.
2. **Name the cause** as `path:line` plus the evidence line, and say why it failed here but
   not before (what differs: config the local run supplies, the interpreter, a path, a
   fresh database, the base branch). Write it in the ledger or the handoff before editing.
3. **Is it this PR's?** Check the same job on `main`'s head. Red there too → not this PR's:
   port an existing fix, or comment once on the PR naming the check, the cause and the fix
   that is missing. Never widen the PR silently.
4. **Guard first**: add the narrowest test that fails for the named cause (a static test for
   a workflow or deploy file, a unit test for code) and see it fail — the RED line with its
   failure count.
5. **Fix at the cause**, one change. Run that test: the GREEN line.
6. **Gates once** for what the change touches — `python -m afenda.tools.check` (`CLAUDE.md` →
   "Test the edit, not the world") — then **one push**; `.claude/hooks/push_gate.py` enforces
   that the stamp exists. The commit message carries the cause, the evidence line, the guard,
   and the RED, GREEN and gate counts.
7. **Re-run a job without a change only** when it died before any test body ran (checkout,
   install, runner loss) or it passed on this exact SHA before — once. "Flaky" is not a cause.
8. **Same fix fails twice → stop.** Go back to step 1 with the new log. Never try a third
   variation; report the cause, the two attempts and their logs to the owner instead.

Never skip, disable, quarantine or loosen a test or a gate to get green. Never push an empty
commit or close and reopen a PR to re-trigger CI.

### The local-to-CI gap

A local run is not evidence for a CI step whose environment differs. The known differences:

| Local | CI (`afenda-image`) |
|---|---|
| `afenda/odoo.conf` supplies `addons_path`, ports, `log_handler` | none: every `odoo-bin` call passes `--addons-path` explicitly (a static test enforces it) |
| database `afenda`, superuser `odoo` | fresh databases, the NOSUPERUSER role `afenda_app` |
| the `.venv` Python 3.11 | the image's `/opt/venv` |
| a working tree you edited | a clean checkout of the pushed SHA |

When a change touches a CI step, simulate the step's own command, not the local shortcut. When
it touches only CI, the proof is the next CI run on the pushed SHA; say so rather than claim
it passed.

## Stop and report to the owner — only for these

Secrets, credentials, hosts, DNS, repository settings (branch protection, environments); an
irreversible or outward step no instruction covers; the same fix failing twice; two of the
owner's stated goals conflicting. Everything else is decided from the spec, the plan, the
evidence, and this skill, and each decision is written as one line: decision · evidence · cost
if wrong.

## Merge

- Method: **rebase and merge**, as PRs #2–#4 were (each commit kept, author dates intact).
- Pass the head SHA you verified as the expected head, so a later push cannot slip in.

## After the merge

1. Watch the push-triggered `afenda-ci` and `afenda-image` on `main`'s new head; a red run on
   `main` is worked by this same procedure at once. Deploying is a manual `./redeploy.sh` on
   the host by the owner (`deploy/README.md` → "Upgrades").
2. If work remains, restart the session's branch from the new `main` (a merged PR never takes
   new commits) and open a new PR.
3. Update the newest handoff in `docs/superpowers/handoffs/` with what merged, the counts, and
   what waits on the owner.
4. Stop watching the PR (unsubscribe) once it is merged or closed.

## Red flags — stop and return to "A red check"

- "Let me just re-run it."
- "It's probably X; I'll push and see."
- "The local run passed, so CI will."
- "I'll bump the timeout / loosen the assertion / skip this test for now."
- A second push for the same red check without a new log line in hand.
