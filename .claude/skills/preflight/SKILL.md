---
name: preflight
description: "Use before every git push in afenda-xforge-v9, and before opening or updating a pull request. Runs the local gate (python -m afenda.tools.check, which stamps the tree the push gate checks), a correctness review of the branch diff, a security review when the diff touches controllers or access rules, and names the owner-only /verify when a UI change needs it; prints one table for the PR's Verification section. Reach for it whenever the next step is a push."
argument-hint: "[--db NAME]"
allowed-tools: Bash(.venv/Scripts/python -m afenda.tools.check*) Bash(git diff*) Bash(git log*) Bash(git status*) Read Grep
---

# Preflight

One pass, in this order, then one push. The push gate (`.claude/hooks/push_gate.py`) refuses a
push whose tree has no passing stamp in `.git/afenda-check/`; this skill is how that stamp is
earned. It never replaces a step with a guess, and it never re-runs a step on an unchanged tree.

1. **Commit first.** `check` certifies a commit, not a working tree: it refuses while tracked or new
   files under `afenda .github .claude docs CLAUDE.md deploy` are uncommitted.
2. **Gate.** `.venv/Scripts/python -m afenda.tools.check $ARGUMENTS` (the database defaults to
   `afenda`, or `AFENDA_CHECK_DB`; the cloud container uses `--db afenda_t7`). It picks the gates
   the diff against `origin/main` needs — the tools suite and the API contract always, the Odoo
   module suites when `afenda/addons/**`, `deploy/Dockerfile` or `requirements.txt` changed —
   runs each once, prints the table and writes the stamp. A failed gate is diagnosed
   (`superpowers:systematic-debugging`): read the whole failure, name the cause as `path:line`,
   fix, commit, and start again at step 2. Never re-run a failed gate unchanged.
3. **Review the diff** (`git diff origin/main...HEAD`), correctness only. Use the bundled
   `/code-review` when it is available to you; if the Skill tool refuses it, dispatch the
   read-only `odoo-reviewer` agent with the diff range instead. Only CRITICAL and HIGH findings
   block: fix them in one wave, commit, and go back to step 2 (the tree changed, so the stamp
   did too). Everything else is listed in the PR, not fixed now.
4. **Security** — only when the diff touches `controllers/`, `security/`, `ir.model.access.csv`,
   record rules, `http.route`, `sudo(`, or hooks under `.claude/hooks/`: the bundled
   `/security-review`, or the same reviewer agent briefed on security only.
5. **Seen running** — when the diff touches views, templates, `static/` or anything a user sees,
   the change is not done until it has been seen: `/verify` (and `/run`) are owner-invoked only,
   so write "owner: run /verify" in the table rather than skipping the row. After the owner has
   run `/run-skill-generator` once, `/verify` follows the recorded Odoo launch recipe.
6. **Report and push.** Print one table — step · command · printed result (the count line
   verbatim) · commit — for the PR's Verification section, then push as a command of its own:
   `git push -u origin <branch>` (the push gate blocks a push chained to other commands).
