"""Tests for the rerun-guard PreToolUse hook (`.claude/hooks/rerun_guard.py`).

The hook blocks a gate command (a test suite, `api_diff`, `corpus`,
`scan_identity`, `pr_evidence`) the third time it is issued in one session on
an unchanged tree. It is loaded by path (not as a package: it lives under
`.claude/`, a dotfile directory upstream's `.gitignore` excludes from normal
package discovery) and driven through its `main(stdin_text, env) -> (exit_code,
stderr_text)` entry point, the way `test_api_diff.py`'s `BaseRefTests` reads
real git history rather than fixtures -- here a throwaway repo built fresh per
test, so the fingerprint (`HEAD` + a scoped `git diff`/`git status`) is real
and no test depends on this checkout's own state.
"""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

_HOOK_PATH = (
    Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "rerun_guard.py"
)


def _load_hook():
    spec = importlib.util.spec_from_file_location("rerun_guard", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rerun_guard = _load_hook()


def _run_git(args, cwd):
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout


class RerunGuardTestCase(unittest.TestCase):
    """Builds a throwaway git repo (git init, one committed file under
    `afenda/`) per test, and a temporary ledger directory pointed at via
    `RERUN_GUARD_LEDGER_DIR`, so nothing here reads or writes this checkout's
    own `.claude/.rerun-ledger`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _run_git(["init", "-q"], self.repo)
        _run_git(["config", "user.email", "test@example.com"], self.repo)
        _run_git(["config", "user.name", "Test"], self.repo)
        (self.repo / "afenda").mkdir()
        self.tracked_file = self.repo / "afenda" / "tracked.py"
        self.tracked_file.write_text("value = 1\n", encoding="utf-8")
        # Mirrors this checkout's own root .gitignore (dotfiles ignored, see
        # CLAUDE.md -> Gotchas): without it, a ledger written under the
        # default `<repo>/.claude/.rerun-ledger/` would itself show up as an
        # untracked file under the `.claude` fingerprint path and perturb the
        # very fingerprint it is trying to record against.
        (self.repo / ".gitignore").write_text(".*\n!.gitignore\n", encoding="utf-8")
        _run_git(["add", "afenda/tracked.py"], self.repo)
        _run_git(["commit", "-q", "-m", "initial"], self.repo)

        self.ledger_dir = Path(self._tmp.name) / "ledger"
        self.env = {"RERUN_GUARD_LEDGER_DIR": str(self.ledger_dir)}

    def _payload(self, command, session_id="session-1", tool_name="Bash"):
        return json.dumps(
            {
                "tool_name": tool_name,
                "tool_input": {"command": command},
                "session_id": session_id,
                "cwd": str(self.repo),
            }
        )

    def test_non_gate_command_passes(self):
        exit_code, stderr = rerun_guard.main(
            self._payload("ls -la afenda"), self.env
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

    def test_non_bash_tool_passes_without_touching_git(self):
        # A gate-looking command under a non-Bash tool must not even reach
        # git: pass a cwd that is not a git repo at all to prove it.
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"command": "python -m unittest afenda.tools.tests"},
                "session_id": "session-1",
                "cwd": "/nonexistent/not-a-repo",
            }
        )
        exit_code, stderr = rerun_guard.main(payload, self.env)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

    def test_gate_command_blocked_on_third_run_of_unchanged_tree(self):
        command = "python -m unittest afenda.tools.tests.test_rerun_guard"
        first = rerun_guard.main(self._payload(command), self.env)
        second = rerun_guard.main(self._payload(command), self.env)
        third = rerun_guard.main(self._payload(command), self.env)

        self.assertEqual(first, (0, ""))
        self.assertEqual(second, (0, ""))

        exit_code, stderr = third
        self.assertEqual(exit_code, 2)
        self.assertIn(command, stderr)
        self.assertIn("unchanged tree", stderr)

    def test_each_gate_pattern_is_recognised(self):
        commands = [
            "python -m unittest discover afenda/tools/tests",
            ".venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda -u afenda_brand --test-enable --test-tags /afenda_brand",
            ".venv/Scripts/python -m afenda.tools.api_diff check --base-ref origin/main",
            ".venv/Scripts/python -m afenda.tools.corpus diff",
            ".venv/Scripts/python -m afenda.tools.scan_identity",
            ".venv/Scripts/python -m afenda.tools.pr_evidence",
        ]
        for command in commands:
            with self.subTest(command=command):
                session_id = f"session-{hash(command)}"
                first = rerun_guard.main(self._payload(command, session_id=session_id), self.env)
                second = rerun_guard.main(self._payload(command, session_id=session_id), self.env)
                third = rerun_guard.main(self._payload(command, session_id=session_id), self.env)
                self.assertEqual(first[0], 0)
                self.assertEqual(second[0], 0)
                self.assertEqual(third[0], 2, command)

    def test_odoo_bin_without_test_enable_is_not_a_gate_command(self):
        command = ".venv/Scripts/python odoo-bin -c afenda/odoo.conf -d afenda"
        for _ in range(3):
            exit_code, stderr = rerun_guard.main(self._payload(command), self.env)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")

    def test_editing_a_tracked_file_resets_the_count(self):
        command = "python -m unittest afenda.tools.tests.test_rerun_guard"
        rerun_guard.main(self._payload(command), self.env)
        rerun_guard.main(self._payload(command), self.env)

        # Edit a tracked file under a fingerprinted path (afenda/): the tree
        # is no longer the one the first two runs saw, so the third run must
        # be allowed, not blocked.
        self.tracked_file.write_text("value = 2\n", encoding="utf-8")

        exit_code, stderr = rerun_guard.main(self._payload(command), self.env)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

    def test_different_session_id_has_its_own_count(self):
        command = "python -m unittest afenda.tools.tests.test_rerun_guard"
        rerun_guard.main(self._payload(command, session_id="session-a"), self.env)
        rerun_guard.main(self._payload(command, session_id="session-a"), self.env)
        third_a = rerun_guard.main(self._payload(command, session_id="session-a"), self.env)
        self.assertEqual(third_a[0], 2)

        # A different session id must not have inherited session-a's count.
        first_b = rerun_guard.main(self._payload(command, session_id="session-b"), self.env)
        second_b = rerun_guard.main(self._payload(command, session_id="session-b"), self.env)
        self.assertEqual(first_b, (0, ""))
        self.assertEqual(second_b, (0, ""))

    def test_malformed_json_passes(self):
        exit_code, stderr = rerun_guard.main("{not json", self.env)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

    def test_not_a_git_repository_passes(self):
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest afenda.tools.tests"},
                "session_id": "session-1",
                "cwd": str(Path(self._tmp.name)),  # a temp dir, never git-inited
            }
        )
        exit_code, stderr = rerun_guard.main(payload, self.env)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

    def test_missing_command_passes(self):
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {},
                "session_id": "session-1",
                "cwd": str(self.repo),
            }
        )
        exit_code, stderr = rerun_guard.main(payload, self.env)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")

    def test_ledger_dir_defaults_under_repo_when_env_var_absent(self):
        # No RERUN_GUARD_LEDGER_DIR: the ledger must land at
        # <repo>/.claude/.rerun-ledger/<session id>.json.
        command = "python -m unittest afenda.tools.tests.test_rerun_guard"
        rerun_guard.main(self._payload(command, session_id="default-dir"), {})
        rerun_guard.main(self._payload(command, session_id="default-dir"), {})
        third = rerun_guard.main(self._payload(command, session_id="default-dir"), {})
        self.assertEqual(third[0], 2)
        ledger_file = self.repo / ".claude" / ".rerun-ledger" / "default-dir.json"
        self.assertTrue(ledger_file.exists())


if __name__ == "__main__":
    unittest.main()
