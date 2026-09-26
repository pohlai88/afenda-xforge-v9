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
import os
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

    def run_hook(self, command, cwd=None, tool_name="Bash", env=None):
        payload = {
            "tool_name": tool_name,
            "tool_input": {"command": command},
            "session_id": "s",
            "cwd": str(cwd or self.repo),
        }
        return push_gate.main(json.dumps(payload), env or {})

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
        self.assertIn(
            "run /preflight (or python -m afenda.tools.check) first; it stamps this tree", stderr
        )

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

    def test_push_affecting_config_is_refused_even_on_a_stamped_head(self):
        # Codex P1 on PR #9: `-c remote.origin.push=other` makes git push `other`,
        # while the gate would check HEAD. Any per-command config on a push is refused.
        self.stamp("HEAD")
        for command in (
            "git -c remote.origin.push=other push origin",
            "git -c push.default=matching push",
            "git --config-env=remote.origin.push=X push origin",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=remote.origin.push GIT_CONFIG_VALUE_0=other git push origin",
            "GIT_CONFIG_PARAMETERS=\"'remote.origin.push=other'\" git push origin",
        ):
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_repo_option_makes_every_positional_a_refspec(self):
        # Codex P1 on PR #9: with --repo, `other` is a refspec, not the remote.
        self.stamp("HEAD")
        self.assertBlocked("git push --repo=origin other")
        self.assertBlocked("git push --repo origin other")
        self.stamp("other")
        self.assertAllowed("git push --repo=origin other")

    def test_bypass_attempts_are_checked_like_any_push(self):
        for command in (
            "AFENDA_SKIP_PUSH_GATE=1 git push origin main",
            "git push --no-verify origin main",
            "git -c core.hooksPath=/dev/null push origin main",
            "bash -c 'git push origin main'",
            "sh -c \"git push origin main\"",
            "bash -lc 'git push origin main'",
            "bash -ec 'git push origin main'",
            "eval git push origin main",
            "git status && git push origin main",
            "true; git push origin main | cat",
            "env X=1 git push origin main",
            "command git push origin main",
            "/usr/bin/git push origin main",
        ):
            with self.subTest(command=command):
                self.assertBlocked(command)

    # -- a push runs alone (sweep 2: C1, H1, H3) ---------------------------

    PUSH_ALONE = (
        "push alone: run `git push …` as its own command after /preflight "
        "(python -m afenda.tools.check) passed on this tree"
    )

    def assertPushAlone(self, command, **kwargs):
        stderr = self.assertBlocked(command, **kwargs)
        self.assertIn(self.PUSH_ALONE, stderr, command)

    def test_a_commit_then_push_in_one_call_is_blocked_on_a_stamped_tree(self):
        # PreToolUse sees the tree before `git commit` runs: HEAD is stamped
        # now, the commit the push would send is not (C1).
        self.stamp()
        (self.repo / "a.txt").write_text("changed\n", encoding="utf-8")
        _git(["add", "a.txt"], self.repo)
        self.assertPushAlone("git commit -qam x && git push origin HEAD")
        self.assertPushAlone("git commit -am '[FIX] x' && git push")

    def test_a_push_with_any_other_command_or_shell_syntax_is_blocked(self):
        self.stamp("main")
        self.stamp("other")
        for command in (
            "git checkout other && git push origin HEAD",
            "git status && git push origin main",
            "git push origin main && git status",
            "git push origin main || true",
            "true; git push origin main",
            "git push origin main;",
            "git push origin main | cat",
            "git push origin main &",
            "git status\ngit push origin main",
            "echo $(git push origin main)",
            "echo `git push origin main`",
            "{ git push origin main; }",
            "if true; then git push origin main; fi",
            "if git diff --quiet; then git push origin HEAD; fi",
            "for x in 1; do git push origin main; done",
            "while false; do git push origin main; done",
            "until true; do git push origin main; done",
            "case x in x) git push origin main;; esac",
            "! git push origin main",
            "(cd {repo} && git push origin main)",
            "bash -c 'git status; git push origin main'",
            "sh -c 'git commit -qam x && git push origin main'",
            "eval 'git commit -qam x; git push origin main'",
            ".venv/Scripts/python -m afenda.tools.check && git push -u origin HEAD",
            "cat > m.txt <<'EOF'\nmsg\nEOF\ngit push origin main",
            "cd /tmp && cd {repo} && git push origin main",
            "git push origin main <<<x",
        ):
            with self.subTest(command=command):
                self.assertPushAlone(command.replace("{repo}", str(self.repo)))

    def test_a_push_alone_still_passes_when_stamped(self):
        self.stamp()
        for command in (
            "git push origin main",
            "git push -u origin HEAD",
            f"cd {self.repo} && git push origin main",
            f"git -C {self.repo} push origin main",
            "command git push origin main",
            "/usr/bin/git push origin main",
            "env X=1 git push origin main",
            "X=1 git push origin main",
            "git push origin main 2>&1",
            "git push origin main > /dev/null",
            "bash -c 'git push origin main'",
            "git push origin main  # after /preflight",
        ):
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_other_git_commands_that_say_push_are_not_pushes(self):
        for command in (
            "git stash push -m wip && git status",
            "git stash push; git stash list",
            "git commit -m 'push later' && git log -1",
            "git log --grep=push | head",
        ):
            with self.subTest(command=command):
                self.assertAllowed(command)

    # -- backslash-newline continuations (H2) -------------------------------

    def test_a_backslash_newline_continues_the_push(self):
        self.assertBlocked("git push -u origin \\\n  main")
        stderr = self.assertBlocked("git push origin \\\nmain")
        self.assertIn("no passing check stamp", stderr)
        self.stamp()
        self.assertAllowed("git push -u origin \\\n  main")
        self.assertAllowed("git push \\\n  origin \\\n  HEAD")

    def test_a_heredoc_body_line_ending_in_a_backslash_still_ends_at_its_delimiter(self):
        self.stamp()
        command = "cat > m.txt <<'EOF'\nline \\\nEOF\ngit push origin main"
        self.assertPushAlone(command)

    # -- the matching refspec (H4) ----------------------------------------

    def test_the_matching_refspec_is_not_a_delete(self):
        self.stamp("main")
        self.stamp("other")
        for command in ("git push origin :", "git push origin +:"):
            with self.subTest(command=command):
                stderr = self.assertBlocked(command)
                self.assertIn("matching", stderr)

    # -- variables in a leading cd / -C path (M4) ----------------------------

    def test_a_leading_cd_or_dash_c_path_expands_the_hook_environment(self):
        self.stamp()
        env = {"CLAUDE_PROJECT_DIR": str(self.repo), "HOME": str(self.outside)}
        for command in (
            'cd "$CLAUDE_PROJECT_DIR" && git push -u origin HEAD',
            "cd ${CLAUDE_PROJECT_DIR} && git push -u origin HEAD",
            "cd $HOME/repo && git push -u origin HEAD",
            "cd ~/repo && git push -u origin HEAD",
            "git -C $CLAUDE_PROJECT_DIR push origin main",
            'git -C "${HOME}/repo" push origin main',
            "git -C ~/repo push origin main",
        ):
            with self.subTest(command=command):
                self.assertAllowed(command, cwd=self.outside, env=env)

    def test_an_unexpandable_path_says_so(self):
        self.stamp()
        stderr = self.assertBlocked("cd $NOPE && git push origin main", cwd=self.outside)
        self.assertIn("cannot expand", stderr)
        stderr = self.assertBlocked("cd $HOME/repo && git push origin main", cwd=self.outside)
        self.assertIn("cannot expand", stderr)

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
        self.assertTrue(any("push_gate.sh" in c for c in by_matcher["Bash"]))
        mcp = "|".join(MCP_TOOLS)
        self.assertTrue(any("push_gate.sh" in c for c in by_matcher[mcp]))
        self.assertEqual(tuple(push_gate.BLOCKED_MCP_TOOLS), MCP_TOOLS)

    def test_the_push_gate_is_wired_through_its_launcher(self):
        # push_gate.sh fails closed itself (any non-zero exit of the gate becomes 2) and
        # falls back to python3, so the settings carry no `|| exit 2` (code review #4).
        settings = json.loads(self.SETTINGS.read_text(encoding="utf-8"))
        commands = [
            hook["command"] for entry in settings["hooks"]["PreToolUse"] for hook in entry["hooks"]
        ]
        gates = [c for c in commands if "push_gate" in c]
        self.assertEqual(len(gates), 2)
        for command in gates:
            self.assertIn(".claude/hooks/push_gate.sh", command)
            self.assertNotIn("exit 2", command)

    @unittest.skipUnless(os.name == "posix" and os.path.exists("/bin/bash"), "runs the launcher under bash")
    def test_without_any_python_only_a_push_is_refused(self):
        # A fresh clone has no .venv: `python -m venv .venv` must still run (code review #4),
        # while a push stays blocked.
        launcher = _HOOK_PATH.with_name("push_gate.sh")
        with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as bindir:
            os.symlink("/bin/cat", os.path.join(bindir, "cat"))
            env = {"CLAUDE_PROJECT_DIR": empty, "PATH": bindir}
            def run(payload):
                return subprocess.run(
                    ["/bin/bash", str(launcher)], input=json.dumps(payload),
                    capture_output=True, text=True, env=env, timeout=60,
                ).returncode
            self.assertEqual(run({"tool_name": "Bash", "tool_input": {"command": "python3 -m venv .venv"}}), 0)
            self.assertEqual(run({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}), 2)
            self.assertEqual(run({"tool_name": MCP_TOOLS[0], "tool_input": {}}), 2)

    @unittest.skipUnless(os.name == "posix" and os.path.exists("/bin/bash"), "runs the launcher under bash")
    def test_the_launcher_fails_closed_when_the_gate_errors(self):
        launcher = _HOOK_PATH.with_name("push_gate.sh")
        with tempfile.TemporaryDirectory() as project:
            hooks = os.path.join(project, ".claude", "hooks")
            os.makedirs(hooks)
            with open(os.path.join(hooks, "push_gate.py"), "w") as handle:
                handle.write("raise SystemExit(1)\n")
            result = subprocess.run(
                ["/bin/bash", str(launcher)], input="{}", capture_output=True, text=True,
                env={"CLAUDE_PROJECT_DIR": project, "PATH": os.environ.get("PATH", "")}, timeout=60,
            )
        self.assertEqual(result.returncode, 2)

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
