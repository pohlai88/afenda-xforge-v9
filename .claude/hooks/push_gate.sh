#!/usr/bin/env bash
# Launcher for push_gate.py (PreToolUse). It runs the gate with the repo's .venv interpreter, or
# python3 when .venv does not exist yet, and turns any non-zero exit into 2 (a block): the gate
# fails closed. With no Python at all it refuses only a push or a GitHub-write MCP tool and lets
# everything else through, so a fresh clone can still run the commands that create .venv.
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
py="$dir/.venv/Scripts/python"
[ -x "$py" ] || py="$(command -v python3 || true)"
if [ -n "$py" ]; then
    "$py" "$dir/.claude/hooks/push_gate.py" || exit 2
    exit 0
fi
input="$(cat)"
case "$input" in
    *'git push'* | *'"mcp__github__'*)
        echo "push-gate: no Python to check this push; create .venv first (CLAUDE.md, first run)" >&2
        exit 2
        ;;
esac
exit 0
