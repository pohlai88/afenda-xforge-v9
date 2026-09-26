"""Tests for the rerun-guard PreToolUse hook (`.claude/hooks/rerun_guard.py`).

The hook blocks a gate (a unittest or pytest run, an Odoo test run,
`afenda.tools.check`, `api_diff`, `corpus`, `scan_identity`, `pr_evidence`)
the third time it runs on an unchanged scoped tree, counted in one ledger that
every session and sub-agent of the repository shares
(`<git common dir>/afenda-rerun-ledger.json`), and keyed on the gate's
semantic identity, not its command text. It is loaded by path (not as a package: it lives under
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
import time
import unittest
import unittest.mock
from pathlib import Path

from afenda.tools import _git_identity

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
    own `.git/afenda-rerun-ledger.json`."""

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

    def test_non_gate_command_never_calls_run_git(self):
        # A non-gate command must return before any git subprocess is
        # spawned at all -- not merely happen to pass on a repo that
        # tolerates it.
        with unittest.mock.patch("subprocess.run") as mock_run:
            for command in ("ls -la afenda", "grep -n pytest afenda/x.py",
                            "grep -rn afenda.tools.check docs"):
                exit_code, stderr = rerun_guard.main(self._payload(command), self.env)
                self.assertEqual((exit_code, stderr), (0, ""), command)
        mock_run.assert_not_called()

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

    def test_grepping_for_unittest_is_not_a_gate_command(self):
        # `grep -n unittest <file>` merely names the word "unittest" in a
        # search; it is not `python -m unittest ...` and must not be treated
        # as a gate command, or a third identical grep would be blocked.
        command = "grep -n unittest afenda/tools/pr_evidence.py"
        for _ in range(3):
            exit_code, stderr = rerun_guard.main(self._payload(command), self.env)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")

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

    def test_a_different_session_shares_the_count(self):
        # One ledger per repository: a sub-agent (its own session id) must
        # inherit the count, not start a fresh one.
        command = "python -m unittest afenda.tools.tests.test_rerun_guard"
        rerun_guard.main(self._payload(command, session_id="session-a"), self.env)
        rerun_guard.main(self._payload(command, session_id="session-a"), self.env)
        third_b = rerun_guard.main(self._payload(command, session_id="session-b"), self.env)
        self.assertEqual(third_b[0], 2)

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

    def test_ledger_defaults_to_the_common_git_dir_when_env_var_absent(self):
        # No RERUN_GUARD_LEDGER_DIR: the ledger must land at
        # <repo>/.git/afenda-rerun-ledger.json.
        command = "python -m unittest afenda.tools.tests.test_rerun_guard"
        rerun_guard.main(self._payload(command, session_id="default-dir"), {})
        rerun_guard.main(self._payload(command, session_id="default-dir"), {})
        third = rerun_guard.main(self._payload(command, session_id="default-dir"), {})
        self.assertEqual(third[0], 2)
        ledger_file = self.repo / ".git" / "afenda-rerun-ledger.json"
        self.assertTrue(ledger_file.exists())

    def test_the_ledger_update_holds_a_repository_lock(self):
        # Codex P2 on PR #9: two sessions must not both read count N and both write N+1.
        # The load-check-increment-save runs under an exclusive lock on a sibling file.
        import threading
        command = "python -m unittest afenda.tools.tests.test_rerun_guard"
        barrier = threading.Barrier(4)
        results = []
        def one():
            barrier.wait()
            results.append(rerun_guard.main(self._payload(command, session_id=threading.current_thread().name), self.env)[0])
        threads = [threading.Thread(target=one, name=f"s{i}") for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [0, 0, 2, 2])
        self.assertTrue(hasattr(rerun_guard, "_ledger_lock"))

    def _three(self, *commands):
        """Run the commands in order; return the exit codes."""
        return [rerun_guard.main(self._payload(c), self.env)[0] for c in commands]

    def test_verbosity_failfast_redirection_and_env_prefix_are_the_same_gate(self):
        codes = self._three(
            "python -m unittest afenda.tools.tests.test_a afenda.tools.tests.test_b",
            "MSYS_NO_PATHCONV=1 .venv/Scripts/python -m unittest -v --failfast "
            "afenda.tools.tests.test_b afenda.tools.tests.test_a 2>&1 | tail -5",
            "cd /x && .venv/Scripts/python -m unittest -q afenda.tools.tests.test_a "
            "afenda.tools.tests.test_b > out.log",
        )
        self.assertEqual(codes, [0, 0, 2])

    def test_odoo_test_tags_are_a_sorted_set(self):
        codes = self._three(
            "python odoo-bin -c afenda/odoo.conf -d a -u m --test-enable --test-tags /m1,/m2 --stop-after-init",
            'MSYS2_ARG_CONV_EXCL="*" python odoo-bin --test-enable -d a --test-tags "/m2,/m1"',
            "python odoo-bin --test-enable --test-tags=/m1,/m2 --http-port 8179",
        )
        self.assertEqual(codes, [0, 0, 2])

    def test_different_targets_are_different_gates(self):
        codes = self._three(
            "python -m unittest afenda.tools.tests.test_a",
            "python -m unittest afenda.tools.tests.test_a",
            "python -m unittest afenda.tools.tests.test_b",
        )
        self.assertEqual(codes, [0, 0, 0])

    def test_check_is_a_gate_keyed_on_its_gates(self):
        codes = self._three(
            ".venv/Scripts/python -m afenda.tools.check --gate tools --gate odoo",
            ".venv/Scripts/python -m afenda.tools.check --db x --gate odoo --gate tools",
            ".venv/Scripts/python -m afenda.tools.check --gate api_contract",
        )
        self.assertEqual(codes, [0, 0, 0])
        third = rerun_guard.main(
            self._payload("python -m afenda.tools.check --gate=odoo --gate=tools"), self.env
        )
        self.assertEqual(third[0], 2)

    def test_check_list_is_not_a_gate_run(self):
        codes = self._three(*["python -m afenda.tools.check --list"] * 3)
        self.assertEqual(codes, [0, 0, 0])

    def test_pytest_is_a_gate(self):
        codes = self._three("pytest tests/a.py -q", "python -m pytest tests/a.py", "pytest -v tests/a.py")
        self.assertEqual(codes, [0, 0, 2])

    def test_a_compound_command_counts_each_gate(self):
        self._three(
            "python -m unittest afenda.tools.tests.test_a",
            "python -m unittest afenda.tools.tests.test_a",
        )
        exit_code, stderr = rerun_guard.main(
            self._payload("python -m afenda.tools.scan_identity && python -m unittest afenda.tools.tests.test_a"),
            self.env,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("unittest", stderr)

    def test_entries_older_than_seven_days_are_pruned(self):
        ledger = self.ledger_dir / "afenda-rerun-ledger.json"
        self.ledger_dir.mkdir(parents=True)
        old = time.time() - 8 * 24 * 3600
        ledger.write_text(json.dumps({"stale": {"count": 2, "time": old, "gate": "x"}}), encoding="utf-8")
        rerun_guard.main(self._payload("python -m unittest afenda.tools.tests.test_a"), self.env)
        data = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertNotIn("stale", data)
        self.assertEqual(len(data), 1)

    def test_fingerprint_comes_from_the_shared_helper(self):
        with unittest.mock.patch.object(
            _git_identity, "scoped_fingerprint", return_value="fixed"
        ) as fingerprint:
            rerun_guard.main(self._payload("python -m unittest afenda.tools.tests.test_a"), self.env)
        fingerprint.assert_called_once()

    def test_a_broken_helper_fails_open(self):
        with unittest.mock.patch.object(rerun_guard, "_load_git_identity", side_effect=ImportError("x")):
            for _ in range(3):
                result = rerun_guard.main(
                    self._payload("python -m unittest afenda.tools.tests.test_a"), self.env
                )
                self.assertEqual(result, (0, ""))

    def test_a_heredoc_body_is_data_not_a_gate(self):
        # A commit message that names a gate command is not a gate run.
        command = (
            "cat > msg.txt <<'EOF'\n"
            "ran python -m unittest afenda.tools.tests.test_a\n"
            "EOF\n"
            "git commit -q -F msg.txt"
        )
        codes = self._three(command, command, command)
        self.assertEqual(codes, [0, 0, 0])

    def test_a_call_that_contains_a_git_push_is_never_counted(self):
        # The push gate blocks a gate chained with a push before it runs, so
        # counting it would lock the tree out of `check` (sweep 2, H1).
        check = ".venv/Scripts/python -m afenda.tools.check"
        codes = self._three(
            f"{check} && git push -u origin HEAD",
            f"{check} && git push -u origin HEAD",
            f"{check}; git -C . push origin main",
        )
        self.assertEqual(codes, [0, 0, 0])
        self.assertFalse((self.ledger_dir / "afenda-rerun-ledger.json").exists())
        self.assertEqual(self._three(check, check, check), [0, 0, 2])

    def test_a_git_stash_push_is_not_a_push(self):
        command = "git stash push && python -m unittest afenda.tools.tests.test_a"
        self.assertEqual(self._three(command, command, command), [0, 0, 2])

    def test_a_backslash_newline_continues_the_command(self):
        codes = self._three(
            "python -m unittest \\\n  afenda.tools.tests.test_a",
            "python -m unittest \\\n  afenda.tools.tests.test_b",
            "python -m unittest \\\n  afenda.tools.tests.test_c",
        )
        self.assertEqual(codes, [0, 0, 0])
        codes = self._three(
            "python -m unittest afenda.tools.tests.test_a",
            "MSYS_NO_PATHCONV=1 python odoo-bin -c afenda/odoo.conf \\\n  --test-enable --test-tags /x",
            "python odoo-bin --test-enable --test-tags /x",
        )
        self.assertEqual(codes, [0, 0, 0])
        self.assertEqual(
            rerun_guard.main(self._payload("python odoo-bin --test-tags /x --test-enable"), self.env)[0],
            2,
        )

    def test_docstring_no_longer_cites_a_lane(self):
        self.assertNotIn("Lane A", _HOOK_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
