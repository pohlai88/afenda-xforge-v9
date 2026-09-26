#!/usr/bin/env bash
# SessionStart: put the one pre-push rule in front of every session and sub-agent, so it never
# depends on a skill being remembered. Plain stdout of a SessionStart hook is added to the
# model's context (code.claude.com/docs/en/hooks, "SessionStart decision control").
cat <<'EOF'
afenda-xforge-v9 push rule: before any git push, run /preflight (python -m afenda.tools.check,
then the diff reviews). The push gate refuses a push whose tree has no passing stamp, and a push
chained to other commands; push as a command of its own. Owner-only built-ins: /verify, /run,
/run-skill-generator.
EOF
