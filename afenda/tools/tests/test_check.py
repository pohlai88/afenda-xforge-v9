"""Tests for the one local check (`afenda/tools/check.py`) and the shared
git-identity helper it stands on (`afenda/tools/_git_identity.py`).

Every test that needs git builds a throwaway repository per test (the way
`test_rerun_guard.py` does), so the tree sha, the scoped fingerprint and the
stamp directory are real and nothing reads or writes this checkout's own
`.git/`. No test runs a real gate: `check.main` takes an `executor` seam, and
the tests hand it canned output in the exact shapes the real gates print
(unittest's `Ran N tests` / `OK`, Odoo's `odoo.tests.result` line).

The one exception is `CiCommandsMatchGatesTests`, a static read of
`.github/workflows/afenda-ci.yml`: CI keeps its own gate commands (the spec's
"Corrections after review", item 10), and this is what stops the two copies
from drifting.
"""
import io
import json
import re
import shlex
import subprocess
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

from afenda.tools import _git_identity, check

REPO = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPO / ".github" / "workflows" / "afenda-ci.yml"


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


class _TempRepo(unittest.TestCase):
    """A repo with `main` (one commit) and a `feature` branch checked out."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _git(["init", "-q", "-b", "main"], self.repo)
        _git(["config", "user.email", "test@example.com"], self.repo)
        _git(["config", "user.name", "Test"], self.repo)
        _git(["config", "commit.gpgsign", "false"], self.repo)
        self.write("afenda/tools/tool.py", "value = 1\n")
        self.write("addons/web/upstream.py", "upstream = 1\n")
        self.commit("initial", "afenda/tools/tool.py", "addons/web/upstream.py")
        _git(["checkout", "-q", "-b", "feature"], self.repo)

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, message, *paths):
        _git(["add", "--", *paths], self.repo)
        _git(["commit", "-q", "-m", message], self.repo)
        return _git(["rev-parse", "HEAD"], self.repo)


class GitIdentityTests(_TempRepo):
    def test_scoped_paths_are_the_one_list(self):
        self.assertEqual(
            _git_identity.SCOPED_PATHS,
            ("afenda", ".github", ".claude", "docs", "CLAUDE.md", "deploy"),
        )

    def test_repo_root_from_a_subdirectory_and_outside_a_repo(self):
        self.assertEqual(
            _git_identity.repo_root(self.repo / "afenda" / "tools"),
            self.repo.resolve(),
        )
        self.assertIsNone(_git_identity.repo_root(Path(self._tmp.name)))

    def test_tree_sha_is_the_commits_tree(self):
        self.assertEqual(
            _git_identity.tree_sha(self.repo),
            _git(["rev-parse", "HEAD^{tree}"], self.repo),
        )
        self.assertEqual(
            _git_identity.tree_sha(self.repo, "main"),
            _git(["rev-parse", "main^{tree}"], self.repo),
        )

    def test_tree_sha_of_an_unknown_rev_raises(self):
        with self.assertRaises(_git_identity.GitIdentityError):
            _git_identity.tree_sha(self.repo, "no-such-ref")

    def test_fingerprint_moves_with_a_scoped_edit_only(self):
        head = _git(["rev-parse", "HEAD"], self.repo)
        before = _git_identity.scoped_fingerprint(self.repo)
        self.assertTrue(before.startswith(head))

        self.write("addons/web/upstream.py", "upstream = 2\n")
        self.assertEqual(_git_identity.scoped_fingerprint(self.repo), before)

        self.write("afenda/tools/tool.py", "value = 2\n")
        self.assertNotEqual(_git_identity.scoped_fingerprint(self.repo), before)

    def test_scoped_dirty_lists_tracked_scoped_changes_only(self):
        self.assertEqual(_git_identity.scoped_dirty(self.repo), [])
        self.write("addons/web/upstream.py", "upstream = 2\n")  # out of scope
        self.write("afenda/untracked.py", "x = 1\n")  # untracked
        self.assertEqual(_git_identity.scoped_dirty(self.repo), [])
        self.write("afenda/tools/tool.py", "value = 2\n")
        self.assertEqual(_git_identity.scoped_dirty(self.repo), ["afenda/tools/tool.py"])

    def test_every_git_call_has_a_five_second_timeout(self):
        real_run = subprocess.run
        seen = []

        def spy(*args, **kwargs):
            seen.append(kwargs.get("timeout"))
            return real_run(*args, **kwargs)

        with unittest.mock.patch.object(_git_identity.subprocess, "run", spy):
            _git_identity.repo_root(self.repo)
            _git_identity.tree_sha(self.repo)
            _git_identity.scoped_fingerprint(self.repo)
            _git_identity.scoped_dirty(self.repo)
            _git_identity.git_common_dir(self.repo)
        self.assertTrue(seen)
        self.assertEqual(set(seen), {5})

    def test_a_git_timeout_raises(self):
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

        with unittest.mock.patch.object(_git_identity.subprocess, "run", slow):
            with self.assertRaises(_git_identity.GitIdentityError):
                _git_identity.tree_sha(self.repo)

    def test_stamp_lives_under_the_common_git_dir(self):
        tree = _git_identity.tree_sha(self.repo)
        self.assertEqual(
            _git_identity.stamp_path(self.repo, tree),
            (self.repo / ".git" / "afenda-check" / f"{tree}.json").resolve(),
        )
        self.assertFalse(_git_identity.has_passing_stamp(self.repo, tree))
        path = _git_identity.stamp_path(self.repo, tree)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"tree": tree, "passed": False}), encoding="utf-8")
        self.assertFalse(_git_identity.has_passing_stamp(self.repo, tree))
        path.write_text(json.dumps({"tree": tree, "passed": True}), encoding="utf-8")
        self.assertTrue(_git_identity.has_passing_stamp(self.repo, tree))


class SelectionTests(unittest.TestCase):
    def test_docs_only_selects_the_two_fast_gates(self):
        self.assertEqual(
            check.select_gates(["docs/x.md", "CLAUDE.md", ".claude/hooks/push_gate.py"]),
            ["tools", "api_contract"],
        )

    def test_nothing_changed_still_selects_the_two_fast_gates(self):
        self.assertEqual(check.select_gates([]), ["tools", "api_contract"])

    def test_addons_dockerfile_and_requirements_select_odoo(self):
        for path in (
            "afenda/addons/afenda_brand/models/x.py",
            "deploy/Dockerfile",
            "requirements.txt",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    check.select_gates([path]), ["tools", "api_contract", "odoo"]
                )

    def test_an_industry_pack_selects_odoo_and_packs(self):
        self.assertEqual(
            check.select_gates(["afenda/addons/afenda_industry_bakery/hooks.py"]),
            ["tools", "api_contract", "odoo", "packs"],
        )

    def test_nginx_config_selects_nginx(self):
        self.assertEqual(
            check.select_gates(["deploy/nginx/afenda.conf"]),
            ["tools", "api_contract", "nginx"],
        )

    def test_other_deploy_files_select_nothing_extra(self):
        self.assertEqual(
            check.select_gates(["deploy/redeploy.sh", "afenda/tools/check.py"]),
            ["tools", "api_contract"],
        )


class GateCommandTests(unittest.TestCase):
    def test_the_exact_commands(self):
        self.assertEqual(
            check.gate_command("tools"), "python -m unittest discover afenda/tools/tests"
        )
        self.assertEqual(
            check.gate_command("api_contract", base="origin/main"),
            "python -m afenda.tools.api_diff check --base-ref origin/main",
        )
        mods = "afenda_brand,afenda_runtime,afenda_api_docs,afenda_brand_digest"
        tags = "/afenda_brand,/afenda_runtime,/afenda_api_docs,/afenda_brand_digest"
        self.assertEqual(
            check.gate_argv("odoo", db="afenda_t7"),
            ["python", "odoo-bin", "-c", "afenda/odoo.conf", "-d", "afenda_t7",
             "-i", mods, "-u", mods, "--test-enable", "--test-tags", tags,
             "--stop-after-init", "--http-port", "8179"],
        )
        packs = "afenda_industry_base,afenda_industry_bakery"
        self.assertEqual(
            check.gate_argv("packs", db="x"),
            ["python", "odoo-bin", "-c", "afenda/odoo.conf", "-d", "x",
             "-i", packs, "-u", packs, "--test-enable", "--test-tags",
             "/afenda_industry_base,/afenda_industry_bakery",
             "--stop-after-init", "--http-port", "8179"],
        )


class ParseTests(unittest.TestCase):
    def test_unittest_ok_and_failed(self):
        ok = "....\n----\nRan 12 tests in 0.5s\n\nOK (skipped=1)\n"
        self.assertEqual(check.parse_result("tools", 0, ok), ("Ran 12 tests in 0.5s · OK (skipped=1)", True))
        bad = "F.\n----\nRan 2 tests in 0.1s\n\nFAILED (failures=1)\n"
        self.assertEqual(check.parse_result("tools", 1, bad), ("Ran 2 tests in 0.1s · FAILED (failures=1)", False))
        self.assertEqual(check.parse_result("tools", 0, "nothing"), ("no unittest result line", False))

    def test_odoo_line_is_quoted_verbatim(self):
        out = (
            "2026 WARNING x\n"
            "2026-09-26 INFO afenda_t7 odoo.tests.result: 0 failed, 0 error(s) of 190 tests "
            "when loading database 'afenda_t7'\n"
        )
        self.assertEqual(
            check.parse_result("odoo", 0, out),
            ("0 failed, 0 error(s) of 190 tests when loading database 'afenda_t7'", True),
        )
        bad = "ERROR odoo.tests.result: 1 failed, 0 error(s) of 190 tests when loading database 'x'\n"
        self.assertFalse(check.parse_result("odoo", 1, bad)[1])
        empty = "WARNING odoo.tests.result: 0 failed, 0 error(s) of 0 tests when loading database 'x'\n"
        self.assertFalse(check.parse_result("odoo", 0, empty)[1])
        self.assertEqual(check.parse_result("packs", 0, ""), ("no Odoo test result line", False))

    def test_api_diff_counts(self):
        full = "Breaking:\nAdditive:\n  a\n  b\nDescriptive:\n  c\n"
        self.assertEqual(
            check.parse_result("api_contract", 0, full),
            ("breaking: 0, additive: 2, descriptive: 1", True),
        )
        short = "breaking: 0, additive: 3, descriptive: 0\nno base contract\n"
        self.assertEqual(
            check.parse_result("api_contract", 0, short),
            ("breaking: 0, additive: 3, descriptive: 0 (no base contract)", True),
        )
        self.assertFalse(check.parse_result("api_contract", 1, "Breaking:\n  x\nAdditive:\nDescriptive:\n")[1])


class _Executor:
    """Records each argv and answers with canned output per gate."""

    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def __call__(self, argv, cwd):
        self.calls.append(argv)
        joined = " ".join(argv)
        if "unittest" in joined:
            if "tools" in self.fail:
                return 1, "Ran 3 tests in 0.1s\n\nFAILED (failures=1)\n"
            return 0, "Ran 3 tests in 0.1s\n\nOK\n"
        if "api_diff" in joined:
            return 0, "Breaking:\nAdditive:\nDescriptive:\n"
        if "--test-enable" in argv:
            if "odoo" in self.fail:
                return 1, "1 failed, 0 error(s) of 190 tests when loading database 'x'\n"
            return 0, "0 failed, 0 error(s) of 190 tests when loading database 'x'\n"
        return 0, ""


class CheckMainTests(_TempRepo):
    def run_check(self, *args, executor=None):
        executor = executor or _Executor()
        out = io.StringIO()
        with redirect_stdout(out):
            code = check.main(["--base", "main", *args], cwd=self.repo, executor=executor)
        return code, out.getvalue(), executor

    def stamp(self):
        return _git_identity.stamp_path(self.repo, _git_identity.tree_sha(self.repo))

    def test_dirty_scoped_tree_is_refused_without_running_anything(self):
        self.write("afenda/tools/tool.py", "value = 2\n")
        code, out, executor = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn("afenda/tools/tool.py", out)
        self.assertEqual(executor.calls, [])
        self.assertFalse(self.stamp().exists())

    def test_a_dirty_tree_outside_the_scope_is_not_refused(self):
        self.write("addons/web/upstream.py", "upstream = 2\n")
        code, _out, _executor = self.run_check()
        self.assertEqual(code, 0)

    def test_pass_prints_the_table_and_writes_the_stamp(self):
        self.write("docs/note.md", "note\n")
        head = self.commit("docs", "docs/note.md")
        code, out, executor = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(len(executor.calls), 2)
        self.assertIn("| gate | command | printed result | commit |", out)
        self.assertIn(
            "| tools | `python -m unittest discover afenda/tools/tests` | Ran 3 tests in 0.1s · OK | "
            + head[:12] + " |",
            out,
        )
        self.assertIn("`python -m afenda.tools.api_diff check --base-ref main`", out)

        stamp = json.loads(self.stamp().read_text(encoding="utf-8"))
        self.assertEqual(stamp["tree"], _git_identity.tree_sha(self.repo))
        self.assertEqual(stamp["head"], head)
        self.assertEqual(stamp["base"], "main")
        self.assertIs(stamp["passed"], True)
        self.assertIn("time", stamp)
        self.assertEqual(
            [g["name"] for g in stamp["gates"]], ["tools", "api_contract"]
        )
        self.assertEqual(
            stamp["gates"][0],
            {"name": "tools", "command": "python -m unittest discover afenda/tools/tests",
             "result": "Ran 3 tests in 0.1s · OK"},
        )

    def test_a_failed_gate_exits_1_and_writes_no_stamp(self):
        code, out, _executor = self.run_check(executor=_Executor(fail={"tools"}))
        self.assertEqual(code, 1)
        self.assertIn("FAILED (failures=1)", out)
        self.assertFalse(self.stamp().exists())

    def test_an_addon_change_runs_the_odoo_gate_on_the_named_db(self):
        self.write("afenda/addons/afenda_brand/x.py", "x = 1\n")
        self.commit("addon", "afenda/addons/afenda_brand/x.py")
        code, out, executor = self.run_check("--db", "afenda_t7")
        self.assertEqual(code, 0)
        odoo_calls = [a for a in executor.calls if "--test-enable" in a]
        self.assertEqual(len(odoo_calls), 1)
        self.assertEqual(odoo_calls[0][odoo_calls[0].index("-d") + 1], "afenda_t7")
        self.assertIn("0 failed, 0 error(s) of 190 tests when loading database 'x'", out)

    def test_a_failed_odoo_gate_fails_the_check(self):
        self.write("afenda/addons/afenda_brand/x.py", "x = 1\n")
        self.commit("addon", "afenda/addons/afenda_brand/x.py")
        code, _out, _executor = self.run_check(executor=_Executor(fail={"odoo"}))
        self.assertEqual(code, 1)
        self.assertFalse(self.stamp().exists())

    def test_gate_flag_runs_on_a_dirty_tree_but_stamps_nothing(self):
        self.write("afenda/tools/tool.py", "value = 2\n")
        code, out, executor = self.run_check("--gate", "tools")
        self.assertEqual(code, 0)
        self.assertEqual(len(executor.calls), 1)
        self.assertIn("Ran 3 tests", out)
        self.assertFalse(self.stamp().exists())

    def test_a_subset_of_the_selected_gates_stamps_nothing(self):
        code, _out, executor = self.run_check("--gate", "tools")
        self.assertEqual(code, 0)
        self.assertEqual(len(executor.calls), 1)
        self.assertFalse(self.stamp().exists())

    def test_list_prints_the_selection_and_runs_nothing(self):
        self.write("deploy/nginx/afenda.conf", "server {}\n")
        self.commit("nginx", "deploy/nginx/afenda.conf")
        code, out, executor = self.run_check("--list")
        self.assertEqual(code, 0)
        self.assertEqual(executor.calls, [])
        for name in ("tools", "api_contract", "nginx"):
            self.assertIn(name, out)
        self.assertNotIn("odoo-bin", out)

    def test_nginx_without_docker_is_reported_ci_only(self):
        self.write("deploy/nginx/afenda.conf", "server {}\n")
        self.commit("nginx", "deploy/nginx/afenda.conf")
        with unittest.mock.patch.object(check, "_docker_available", return_value=False):
            code, out, _executor = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("CI only", out)

    def test_an_unknown_base_exits_2(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = check.main(["--base", "no-such-ref"], cwd=self.repo, executor=_Executor())
        self.assertEqual(code, 2)


class CiCommandsMatchGatesTests(unittest.TestCase):
    """Each gate command in afenda-ci.yml's `run:` blocks equals `GATES`'."""

    @staticmethod
    def _run_block_commands():
        """Every command line inside a `run:` block, as argv up to the first
        shell operator or redirection."""
        commands = []
        in_run, run_indent = False, 0
        for raw in CI_WORKFLOW.read_text(encoding="utf-8").splitlines():
            indent = len(raw) - len(raw.lstrip())
            stripped = raw.strip()
            if in_run and stripped and indent <= run_indent:
                in_run = False
            match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", raw)
            if match:
                run_indent = len(match.group(1))
                rest = match.group(2).strip()
                if rest in ("|", ">", "|-", ">-"):
                    in_run = True
                elif rest:
                    commands.append(rest)
                continue
            if in_run and stripped:
                commands.append(stripped)
        argvs = []
        for line in commands:
            # Only gate lines; others (e.g. `\` continuations) need not lex.
            if not line.startswith("python -m "):
                continue
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            argv = []
            for token in lexer:
                if token and set(token) <= set("|&;<>()"):
                    if token[0] in "<>" and argv and argv[-1].isdigit():
                        argv.pop()  # the fd of `2>&1`, which shlex splits off
                    break
                argv.append(token)
            if argv:
                argvs.append(argv)
        return argvs

    def test_tools_command(self):
        found = [a for a in self._run_block_commands() if a[:3] == ["python", "-m", "unittest"]]
        self.assertTrue(found, "no unittest command in afenda-ci.yml")
        for argv in found:
            self.assertEqual(argv, check.gate_argv("tools"))

    def test_api_contract_commands(self):
        found = [
            a for a in self._run_block_commands()
            if a[:3] == ["python", "-m", "afenda.tools.api_diff"]
        ]
        self.assertEqual(len(found), 2, found)
        bases = []
        for argv in found:
            base = argv[-1]
            bases.append(base)
            self.assertEqual(argv, check.gate_argv("api_contract", base=base))
        self.assertEqual(sorted(bases), ["$BEFORE", "origin/main"])


if __name__ == "__main__":
    unittest.main()
