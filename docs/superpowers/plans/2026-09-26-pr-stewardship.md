# PR stewardship — implementation plan

Spec: `docs/superpowers/specs/2026-09-26-pr-stewardship.md`. Branch: the PR #5 head branch.

## Global constraints

- Standard library only in `afenda/tools/pr_evidence.py`; Python 3.11 and 3.12.
- The PR body reaches CI through `env: PR_BODY: ${{ github.event.pull_request.body }}`; no
  `${{ }}` expression appears inside any `run:` script of the new workflow.
- Count patterns accepted as printed evidence: `Ran <N> test` / `Ran <N> tests` (unittest) and
  `of <N> tests` (Odoo's `odoo.tests.result` line). Commit id: 7–40 lowercase hex characters as
  a whole word. Both must appear after a line whose text is `Verification` as a Markdown heading
  (`#`–`####`) or bold paragraph (`**Verification**`), case-insensitive, before the next heading
  of the same or higher level (bold-paragraph form: to the end of the body).
- Commit subjects use Odoo tags; stage explicit paths; `.claude/` needs `git add -f`.

## Task 1 — the check, its workflow, the template (implementer)

Files: create `afenda/tools/pr_evidence.py`, `afenda/tools/tests/test_pr_evidence.py`,
`.github/workflows/afenda-pr.yml`; replace `.github/PULL_REQUEST_TEMPLATE.md`; add one test to
`afenda/tools/tests/test_deploy_static.py`.

1. RED: tests for `pr_evidence.check(body) -> list[str]` (empty list = pass, else one message
   per missing item): (a) a body with a heading `## Verification` and a table row holding
   `Ran 307 tests … OK` and `5d6b77378` passes; (b) the bold form `**Verification**` with
   `0 failed, 0 error(s) of 184 tests` and a 40-hex SHA passes; (c) no Verification section
   fails naming the section; (d) a section with a SHA but only "exit 0" fails naming the count;
   (e) a section with a count but no SHA fails naming the commit; (f) a count and SHA that
   appear only *before* the section do not count; (g) an empty or `None` body fails.
   CLI: `python -m afenda.tools.pr_evidence` reads `PR_BODY` from the environment, prints each
   message as `::error::<message>` and exits 1, or prints `pr evidence: ok` and exits 0; one
   test drives the CLI through `subprocess` with `PR_BODY` set.
2. GREEN: implement.
3. Workflow `afenda-pr.yml`: `name: afenda-pr`; `on: pull_request: branches: [main], types:
   [opened, edited, synchronize, reopened, ready_for_review]`; `permissions: contents: read`;
   `concurrency` per PR ref with cancel-in-progress; job id `pr_evidence`, `name: pr evidence`,
   `runs-on: ubuntu-24.04`, `timeout-minutes: 5`; steps: checkout (`fetch-depth: 1`,
   `sparse-checkout: afenda/tools`), setup-python 3.11, run
   `python -m afenda.tools.pr_evidence` with `env: PR_BODY: ${{ github.event.pull_request.body }}`.
   A header comment says what it enforces and points at the steward skill.
4. Static test in `test_deploy_static.py`: `afenda-pr.yml` triggers on `edited`, passes the body
   through `env`, and no `run:` block contains `${{`.
5. Template: sections `Why`, `Before`, `After`, `Verification` (a table: Gate · Command ·
   Printed result · SHA, with one example row and the rule "printed counts, never exit codes"),
   `For the owner` (decisions or corrections needing them; "none" if none), `Not verified`
   (what no run exercised). No CLA line.
6. Gates once: the tools suite (expect previous 307 + the new tests, OK, skipped=1); run
   `PR_BODY="$(cat <the PR #5 body file>)" python -m afenda.tools.pr_evidence` and expect
   `pr evidence: ok`.
7. Commit `[ADD] ci: pr evidence — a PR into main must cite printed counts and a commit`.

## Task 2 — the procedure (orchestrator, in parallel; no shared files with Task 1)

Create `.claude/skills/steward/SKILL.md`; add a "Pull requests" section to `CLAUDE.md`; add
the owner's branch-protection action to `docs/superpowers/handoffs/2026-09-26-api-assets.md`
under "Waiting on the owner". Commit `[ADD] docs: the PR steward procedure, binding on every PR`.

## Then

Push once; update PR #5's description to the new template; drive PR #5 by the steward skill to
merged.
