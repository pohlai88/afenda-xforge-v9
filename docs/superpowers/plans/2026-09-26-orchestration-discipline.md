# Orchestration discipline — implementation plan

Spec: `docs/superpowers/specs/2026-09-26-orchestration-discipline.md`. Branch: PR #5's head.

## Conflict map (this plan runs beside the stewardship plan's Task 1)

| Lane | Files | Shares with |
|---|---|---|
| Stewardship Task 1 (running) | `afenda/tools/pr_evidence.py`, `afenda/tools/tests/test_pr_evidence.py`, `afenda/tools/tests/test_deploy_static.py`, `.github/workflows/afenda-pr.yml`, `.github/PULL_REQUEST_TEMPLATE.md` | the tools-suite count; the git index (`commit --only`) |
| A — rerun guard (sub-agent) | `.claude/hooks/rerun_guard.py`, `.claude/settings.json`, `afenda/tools/tests/test_rerun_guard.py` | the tools-suite count; the git index |
| B — the skill (orchestrator) | `.claude/skills/orchestrate/SKILL.md`, `CLAUDE.md`, this plan, the spec | nothing |

No file is shared, so A, B and Task 1 run in parallel. The tools-suite count is shared: each
lane reports its own new tests by name, and the orchestrator runs the combined gate once after
all three land.

## Lane A — the rerun guard

1. RED: `afenda/tools/tests/test_rerun_guard.py` loads `.claude/hooks/rerun_guard.py` by path
   (`importlib.util.spec_from_file_location`) and drives its `main(stdin_text, env) -> (exit_code,
   stderr_text)` entry point with a temporary ledger directory and a temporary git repository
   (so the fingerprint is real). Cases: a non-gate command → 0; a gate command → 0, 0, then 2
   with a message naming the command and "unchanged tree"; editing a tracked file under a
   fingerprinted path resets the count; a different session id has its own count; malformed JSON
   → 0; not a git repository → 0.
2. GREEN: the hook.
   - Input: the PreToolUse JSON on stdin (`tool_name`, `tool_input.command`, `session_id`,
     `cwd`). Anything but `Bash` → exit 0.
   - Gate commands (regex, case-sensitive): `unittest`, `odoo-bin` together with
     `--test-enable`, `afenda.tools.api_diff`, `afenda.tools.corpus`,
     `afenda.tools.scan_identity`, `afenda.tools.pr_evidence`.
   - Tree fingerprint, run in the repository root (`git rev-parse --show-toplevel` from `cwd`):
     `HEAD` sha + sha256 of `git diff HEAD --no-ext-diff -- afenda .github .claude docs
     CLAUDE.md deploy` + `git status --porcelain -- <same paths>`. Scoped on purpose: an
     unscoped `git status` takes about two minutes on this tree.
   - Key: sha256 of session id + whitespace-normalised command + fingerprint. Ledger:
     `<repo>/.claude/.rerun-ledger/<session id>.json` (a dotfile path, so git ignores it).
   - Count 0 or 1 → record and exit 0. Count 2 → exit 2; stderr: `rerun-guard: "<command>" has
     already run twice in this session on this unchanged tree (HEAD <short>). CLAUDE.md →
     Execution discipline: cite the earlier printed count, or change code first, or stop and
     report.`
   - Any exception, a missing git, a timeout (5 s per git call) → exit 0.
   - Standard library only; runs on Python 3.11 and 3.12, on Linux and Windows Git Bash.
3. `.claude/settings.json`: add a `PreToolUse` entry, matcher `Bash`, command
   `"$CLAUDE_PROJECT_DIR"/.venv/Scripts/python "$CLAUDE_PROJECT_DIR"/.claude/hooks/rerun_guard.py`.
   Keep the SessionStart hook and the plugin settings unchanged.
4. Gates once: `.venv/Scripts/python -m unittest afenda.tools.tests.test_rerun_guard` (report the
   count), then the tools suite (report the count and name the tests that are not yours if the
   count includes other lanes' uncommitted files).
5. Commit `[ADD] hooks: a gate command cannot run a third time on an unchanged tree`
   (`git add -f` for `.claude/` paths; `git commit --only`).

## Lane B — the skill

`.claude/skills/orchestrate/SKILL.md` per the spec's decision 1; `CLAUDE.md` names it as binding
(in "Execution discipline" → "Orchestrators decide; sub-agents execute") and names the hook in
"Gotchas". Commit `[ADD] docs: the orchestrate skill — one sweep, one fix wave, parallel by
conflict map`.

## Then

One combined tools-suite gate by the orchestrator; one push; `afenda-ci` and `afenda-pr` on the
pushed SHA; PR #5's description updated; the steward skill's merge.
