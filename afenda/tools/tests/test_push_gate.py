"""Tests for the push gate PreToolUse hook (`.claude/hooks/push_gate.py`).

The hook blocks (exit 2) a `git push` whose resolved tip tree has no passing
stamp from `python -m afenda.tools.check`, always blocks the three GitHub
file-writing MCP tools, and fails closed: an exception is a block, never a
pass. It is loaded by path, like `test_rerun_guard.py` loads its hook, and
driven through `main(stdin_text, env) -> (exit_code, stderr_text)` against a
throwaway repository built per test, so the refspec resolution is real git.
No test pushes anything: the hook only resolves refs and reads stamps.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from afenda.tools import _git_identity

_HOOK_PATH = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "push_gate.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("push_gate", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


push_gate = _load_hook()

MCP_TOOLS = (
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
    "mcp__github__delete_file",
)


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


class PushGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.outside = Path(self._tmp.name)
        self.repo = self.outside / "repo"
        self.repo.mkdir()
        _git(["init", "-q", "-b", "main"], self.repo)
        _git(["config", "user.email", "test@example.com"], self.repo)
        _git(["config", "user.name", "Test"], self.repo)
        _git(["config", "commit.gpgsign", "false"], self.repo)
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(["add", "a.txt"], self.repo)
        _git(["commit", "-q", "-m", "first"], self.repo)
        _git(["tag", "v1"], self.repo)
        _git(["tag", "-a", "v1-annotated", "-m", "annotated"], self.repo)
        _git(["checkout", "-q", "-b", "other"], self.repo)
        (self.repo / "b.txt").write_text("b\n", encoding="utf-8")
        _git(["add", "b.txt"], self.repo)
        _git(["commit", "-q", "-m", "second"], self.repo)
        _git(["checkout", "-q", "main"], self.repo)

    def stamp(self, rev="HEAD"):
        tree = _git(["rev-parse", f"{rev}^{{tree}}"], self.repo)
        path = _git_identity.stamp_path(self.repo, tree)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tree": tree, "passed": True}), encoding="utf-8")

    def run_hook(self, command, cwd=None, tool_name="Bash"):
        payload = {
            "tool_name": tool_name,
            "tool_input": {"command": command},
            "session_id": "s",
            "cwd": str(cwd or self.repo),
        }
        return push_gate.main(json.dumps(payload), {})

    def assertBlocked(self, command, **kwargs):
        code, stderr = self.run_hook(command, **kwargs)
        self.assertEqual(code, 2, f"{command!r} was not blocked")
        self.assertTrue(stderr)
        return stderr

    def assertAllowed(self, command, **kwargs):
        self.assertEqual(self.run_hook(command, **kwargs), (0, ""), command)

    # -- not a push -------------------------------------------------------

    def test_other_commands_pass_without_any_git_call(self):
        with unittest.mock.patch("subprocess.run") as run:
            for command in ("ls", "git status", "git commit -m 'push later'",
                            "echo git push", "grep -rn 'git push' docs"):
                self.assertAllowed(command)
        run.assert_not_called()

    def test_other_tools_pass(self):
        self.assertEqual(self.run_hook("git push", tool_name="Edit"), (0, ""))
        self.assertEqual(self.run_hook("", tool_name="mcp__github__get_me"), (0, ""))

    # -- stamped / unstamped ----------------------------------------------

    def test_unstamped_push_is_blocked_with_the_command_to_run(self):
        stderr = self.assertBlocked("git push origin main")
        self.assertIn("python -m afenda.tools.check", stderr)

    def test_stamped_push_passes(self):
        self.stamp()
        self.assertAllowed("git push origin main")
        self.assertAllowed("git push -u origin HEAD")

    def test_a_stamp_for_another_tree_does_not_count(self):
        self.stamp("main")
        self.assertBlocked("git push origin other")
        self.stamp("other")
        self.assertAllowed("git push origin other")

    def test_bare_push_checks_the_current_branch(self):
        self.assertBlocked("git push")
        self.assertBlocked("git push origin")
        self.stamp()
        self.assertAllowed("git push")
        self.assertAllowed("git push origin")

    def test_detached_head_bare_push_is_blocked(self):
        self.stamp()
        _git(["checkout", "-q", "--detach", "HEAD"], self.repo)
        self.assertBlocked("git push")

    # -- exemptions -------------------------------------------------------

    def test_dry_run_passes_unstamped(self):
        self.assertAllowed("git push --dry-run origin main")
        self.assertAllowed("git push -n origin main")

    def test_delete_passes_unstamped(self):
        self.assertAllowed("git push origin --delete other")
        self.assertAllowed("git push -d origin other")
        self.assertAllowed("git push origin :other")

    def test_tag_only_pushes_pass_unstamped(self):
        self.assertAllowed("git push origin v1")
        self.assertAllowed("git push origin v1-annotated")
        self.assertAllowed("git push origin tag v1")
        self.assertAllowed("git push origin refs/tags/v1:refs/tags/v1")
        self.assertAllowed("git push --tags")
        self.assertAllowed("git push origin --tags")

    def test_a_tag_pushed_onto_a_branch_needs_a_stamp(self):
        self.assertBlocked("git push origin v1:refs/heads/main")
        self.assertBlocked("git push origin v1:main")
        self.assertBlocked("git push --tags origin main")

    # -- refspec forms ----------------------------------------------------

    def test_forced_forms_are_checked_like_any_push(self):
        for command in (
            "git push origin +main",
            "git push --force-with-lease=main:abc123 origin main",
            "git push --force-with-lease origin main",
            "git push -f origin main",
            "git push origin HEAD:refs/heads/x",
            "git push origin main:main",
        ):
            with self.subTest(command=command):
                self.assertBlocked(command)
        self.stamp()
        for command in (
            "git push origin +main",
            "git push --force-with-lease=main:abc123 origin main",
            "git push origin HEAD:refs/heads/x",
            "git push origin " + _git(["rev-parse", "HEAD"], self.repo) + ":main",
        ):
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_every_refspec_must_be_stamped(self):
        self.stamp("main")
        self.assertBlocked("git push origin main other")
        self.stamp("other")
        self.assertAllowed("git push origin main other")

    def test_unresolvable_ref_is_blocked(self):
        self.stamp()
        stderr = self.assertBlocked("git push origin no-such-branch")
        self.assertIn("no-such-branch", stderr)
        self.assertBlocked("git push origin 'refs/heads/*:refs/heads/*'")

    def test_all_and_mirror_are_blocked(self):
        self.stamp("main")
        self.stamp("other")
        self.assertBlocked("git push --all origin")
        self.assertBlocked("git push --mirror origin")

    def test_git_dash_c_path(self):
        self.assertBlocked(f"git -C {self.repo} push origin main", cwd=self.outside)
        self.stamp()
        self.assertAllowed(f"git -C {self.repo} push origin main", cwd=self.outside)

    def test_cd_before_push_is_followed(self):
        self.assertBlocked(f"cd {self.repo} && git push origin main", cwd=self.outside)
        self.stamp()
        self.assertAllowed(f"cd {self.repo} && git push origin main", cwd=self.outside)

    def test_push_outside_any_repository_is_blocked(self):
        self.assertBlocked("git push origin main", cwd=self.outside)

    # -- no bypass inside the hook -----------------------------------------

    def test_bypass_attempts_are_checked_like_any_push(self):
        for command in (
            "AFENDA_SKIP_PUSH_GATE=1 git push origin main",
            "git push --no-verify origin main",
            "git -c core.hooksPath=/dev/null push origin main",
            "bash -c 'git push origin main'",
            "sh -c \"git push origin main\"",
            "eval git push origin main",
            "git status && git push origin main",
            "true; git push origin main | cat",
            "env X=1 git push origin main",
            "command git push origin main",
            "/usr/bin/git push origin main",
        ):
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_unparseable_command_mentioning_push_is_blocked(self):
        self.stamp()
        self.assertBlocked("git push origin 'main")

    def test_a_heredoc_body_is_data_not_a_push(self):
        # A commit message fed through a heredoc may say "push" and hold an
        # unbalanced apostrophe; neither is shell syntax.
        command = (
            "cat > msg.txt <<'EOF'\n"
            "[IMP] hooks: a git push goes only when check's stamp exists\n"
            "EOF\n"
            "git commit -q -F msg.txt"
        )
        self.assertAllowed(command)

    def test_a_heredoc_fed_to_a_shell_is_read_as_commands(self):
        self.assertBlocked("bash <<'EOF'\ngit push origin main\nEOF")

    # -- MCP tools and fail-closed -----------------------------------------

    def test_github_file_writing_tools_are_always_blocked(self):
        self.stamp()
        for tool in MCP_TOOLS:
            with self.subTest(tool=tool):
                code, stderr = push_gate.main(
                    json.dumps({"tool_name": tool, "tool_input": {}, "cwd": str(self.repo)}), {}
                )
                self.assertEqual(code, 2)
                self.assertIn("git push", stderr)

    def test_an_exception_blocks(self):
        with unittest.mock.patch.object(push_gate, "_check_push", side_effect=RuntimeError("boom")):
            code, stderr = self.run_hook("git push origin main")
        self.assertEqual(code, 2)
        self.assertIn("boom", stderr)

    def test_malformed_input_blocks(self):
        self.assertEqual(push_gate.main("{not json", {})[0], 2)

    def test_a_git_timeout_blocks(self):
        self.stamp()

        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

        with unittest.mock.patch.object(_git_identity.subprocess, "run", slow):
            code, _stderr = self.run_hook("git push origin main")
        self.assertEqual(code, 2)


class WiringTests(unittest.TestCase):
    """The hook is wired where the plan says, and runs as a script."""

    SETTINGS = _HOOK_PATH.parents[1] / "settings.json"

    def test_settings_wire_the_gate_for_bash_and_the_mcp_tools(self):
        settings = json.loads(self.SETTINGS.read_text(encoding="utf-8"))
        pre = settings["hooks"]["PreToolUse"]
        by_matcher = {
            entry["matcher"]: [hook["command"] for hook in entry["hooks"]] for entry in pre
        }
        self.assertTrue(any("rerun_guard.py" in c for c in by_matcher["Bash"]))
        self.assertTrue(any("push_gate.py" in c for c in by_matcher["Bash"]))
        mcp = "|".join(MCP_TOOLS)
        self.assertTrue(any("push_gate.py" in c for c in by_matcher[mcp]))
        self.assertEqual(tuple(push_gate.BLOCKED_MCP_TOOLS), MCP_TOOLS)

    def test_settings_deny_edits_to_root_odoo_and_addons(self):
        settings = json.loads(self.SETTINGS.read_text(encoding="utf-8"))
        deny = settings["permissions"]["deny"]
        self.assertIn("Edit(/odoo/**)", deny)
        self.assertIn("Edit(/addons/**)", deny)

    def test_the_script_exits_2_on_a_blocked_tool(self):
        payload = json.dumps({"tool_name": MCP_TOOLS[0], "tool_input": {}})
        result = subprocess.run(
            [sys.executable, str(_HOOK_PATH)], input=payload, capture_output=True,
            text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("push-gate", result.stderr)


if __name__ == "__main__":
    unittest.main()
