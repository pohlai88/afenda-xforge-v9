"""Tests for the PR-evidence gate (`afenda/tools/pr_evidence.py`).

One test per rule in the plan's Task 1 (a)-(g), plus a CLI test that drives
the module through `subprocess` with `PR_BODY` set, the way the workflow
itself will invoke it. `PrCommitsTests` and the matching `CliTests` cover the
`PR_COMMITS` contract (docs/superpowers/specs/2026-09-26-local-first-gates.md
decision 4 and Corrections after review item 8): a cited commit id must be a
prefix of one of the PR's real commits, fetched by the workflow from the
GitHub API, never from a local `git rev-list`. `PR_COMMITS` unset (`None`)
must keep today's behaviour exactly, which the pre-existing tests above
already exercise unchanged.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from afenda.tools.pr_evidence import check, main

REPO = Path(__file__).resolve().parents[3]


class CheckTests(unittest.TestCase):
    def test_heading_section_with_count_and_sha_passes(self):
        body = (
            "## Verification\n"
            "\n"
            "| Gate | Result | SHA |\n"
            "|---|---|---|\n"
            "| Tools suite | Ran 307 tests … OK (skipped=1) | 5d6b77378 |\n"
        )
        self.assertEqual(check(body), [])

    def test_bold_paragraph_section_with_count_and_sha_passes(self):
        body = (
            "Some prose before.\n"
            "\n"
            "**Verification** (printed counts, never exit codes):\n"
            "\n"
            "0 failed, 0 error(s) of 184 tests\n"
            "commit 1234567890abcdef1234567890abcdef12345678\n"
        )
        self.assertEqual(check(body), [])

    def test_no_verification_section_fails_naming_the_section(self):
        body = "Just a description. No section here at all.\n"
        errors = check(body)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Verification section", errors[0])

    def test_section_with_sha_but_no_count_fails_naming_the_count(self):
        body = (
            "## Verification\n"
            "\n"
            "It works, exit 0, commit 5d6b77378.\n"
        )
        errors = check(body)
        self.assertTrue(any("printed test count" in e for e in errors), errors)
        self.assertFalse(any("commit id" in e for e in errors), errors)

    def test_section_with_count_but_no_sha_fails_naming_the_commit(self):
        body = (
            "## Verification\n"
            "\n"
            "Ran 307 tests in 12.3s OK\n"
        )
        errors = check(body)
        self.assertTrue(any("commit id" in e for e in errors), errors)
        self.assertFalse(any("printed test count" in e for e in errors), errors)

    def test_pure_decimal_short_id_is_not_a_commit(self):
        # An issue/PR reference like `#1234567` is 7 decimal digits with no
        # a-f letter and is not 40 characters long: it must not be accepted
        # as a commit id.
        body = (
            "## Verification\n"
            "\n"
            "Ran 307 tests … OK, see issue #1234567.\n"
        )
        errors = check(body)
        self.assertTrue(any("commit id" in e for e in errors), errors)

    def test_forty_digit_all_decimal_id_passes_as_commit(self):
        # Exactly 40 hex characters is unambiguously a full commit id, even
        # if every digit happens to be decimal.
        body = (
            "## Verification\n"
            "\n"
            "Ran 307 tests … OK, commit 1234567890123456789012345678901234567890.\n"
        )
        self.assertEqual(check(body), [])

    def test_short_sha_with_a_letter_passes_as_commit(self):
        body = (
            "## Verification\n"
            "\n"
            "Ran 307 tests … OK, commit 5d6b77378.\n"
        )
        self.assertEqual(check(body), [])

    def test_evidence_before_the_section_does_not_count(self):
        # The count and the commit id both appear only above the Verification
        # heading; the section itself (a bare heading, nothing else) has
        # neither, so both errors must still be reported.
        body = (
            "Ran 307 tests … OK, commit 5d6b77378.\n"
            "\n"
            "## Verification\n"
            "\n"
            "Nothing here.\n"
        )
        errors = check(body)
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("printed test count" in e for e in errors), errors)
        self.assertTrue(any("commit id" in e for e in errors), errors)

    def test_empty_body_fails(self):
        errors = check("")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Verification section", errors[0])

    def test_none_body_fails(self):
        errors = check(None)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Verification section", errors[0])

    def test_heading_section_ends_before_next_heading_of_same_or_higher_level(self):
        # A count/SHA placed under a later heading of the same level must
        # not count towards an earlier Verification section.
        body = (
            "## Verification\n"
            "\n"
            "Nothing here.\n"
            "\n"
            "## Owner notes\n"
            "\n"
            "Ran 307 tests … OK, commit 5d6b77378.\n"
        )
        errors = check(body)
        self.assertEqual(len(errors), 2, errors)

    def test_bold_paragraph_section_runs_to_end_of_body(self):
        # Unlike the heading form, a later heading-looking line after a bold
        # paragraph does not end the section: the evidence below it still
        # counts.
        body = (
            "**Verification**\n"
            "\n"
            "## Not really a new section, just prose that looks like one\n"
            "\n"
            "Ran 307 tests … OK, commit 5d6b77378.\n"
        )
        self.assertEqual(check(body), [])

    def test_the_real_pr5_body_sample_passes(self):
        # The sample dropped for this task: a bold-paragraph Verification
        # section followed immediately by a two-row table, two gates cited.
        body = (
            "Description of the issue/feature this PR addresses:\n"
            "\n"
            "Phase 1 of \"AFENDA-owned API and doc assets\".\n"
            "\n"
            "**Verification** (printed counts, never exit codes):\n"
            "\n"
            "| Gate | Result | SHA |\n"
            "|---|---|---|\n"
            "| Tools suite (`python -m unittest discover afenda/tools/tests`) "
            "| `Ran 307 tests … OK (skipped=1)` | 5d6b77378 |\n"
            "| Four AFENDA modules together, fresh DB | `0 failed, 0 error(s) of 184 tests` "
            "| 5c71e380d |\n"
        )
        self.assertEqual(check(body), [])


class PrCommitsTests(unittest.TestCase):
    """`check(body, pr_commits)`: a cited id must prefix one of `pr_commits`."""

    def test_unset_pr_commits_keeps_todays_behaviour(self):
        # No second argument at all (every pre-existing call above) and an
        # explicit `None` must behave identically: the format-only check,
        # with no cross-check against any commit list.
        body = "## Verification\n\nRan 307 tests … OK, commit 5d6b77378.\n"
        self.assertEqual(check(body), [])
        self.assertEqual(check(body, None), [])

    def test_empty_pr_commits_list_also_skips_the_match_check(self):
        # An empty list is falsy, same as None: nothing to compare against
        # (e.g. the API call returned no commits), so the format-only rule
        # still governs rather than failing every PR outright.
        body = "## Verification\n\nRan 307 tests … OK, commit 5d6b77378.\n"
        self.assertEqual(check(body, []), [])

    def test_cited_id_matching_a_pr_commit_prefix_passes(self):
        body = "## Verification\n\nRan 307 tests … OK, commit abc1234.\n"
        pr_commits = ["abc1234" + "0" * 33]  # 40 hex chars, prefixed by the cited id
        self.assertEqual(len(pr_commits[0]), 40)
        self.assertEqual(check(body, pr_commits), [])

    def test_cited_id_not_matching_any_pr_commit_fails_naming_the_id(self):
        body = "## Verification\n\nRan 307 tests … OK, commit abc1234.\n"
        pr_commits = ["deadbee" + "0" * 33]  # a real commit, but not this one
        errors = check(body, pr_commits)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("abc1234", errors[0])
        self.assertIn("does not match", errors[0])

    def test_one_matching_id_among_several_cited_is_enough(self):
        body = (
            "## Verification\n\n"
            "Ran 307 tests … OK, commit foreign12.\n"
            "0 failed, 0 error(s) of 184 tests, commit abc1234.\n"
        )
        pr_commits = ["abc1234" + "0" * 33]
        self.assertEqual(check(body, pr_commits), [])


class TemplateTests(unittest.TestCase):
    def test_unedited_template_fails_the_evidence_check(self):
        # The committed PR template is a blank form: nobody has pasted a
        # real printed count or commit id into it yet, so it must fail the
        # same check the workflow runs against a real PR body. If it
        # passes, an author who never fills in Verification would still
        # get a green pr-evidence check.
        template = (REPO / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(
            encoding="utf-8"
        )
        self.assertNotEqual(check(template), [])


class CliTests(unittest.TestCase):
    def _run(self, body, pr_commits=None):
        env = dict(os.environ)
        if body is None:
            env.pop("PR_BODY", None)
        else:
            env["PR_BODY"] = body
        # Isolated from whatever the host shell happens to have set, unless
        # this test explicitly supplies it: PR_COMMITS unset must reproduce
        # today's behaviour exactly, never accidentally pick up a stray
        # ambient value.
        if pr_commits is None:
            env.pop("PR_COMMITS", None)
        else:
            env["PR_COMMITS"] = " ".join(pr_commits)
        return subprocess.run(
            [sys.executable, "-m", "afenda.tools.pr_evidence"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_cli_passes_and_prints_ok(self):
        body = "## Verification\n\nRan 307 tests … OK, commit 5d6b77378.\n"
        proc = self._run(body)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("pr evidence: ok", proc.stdout)

    def test_cli_fails_and_prints_error_annotations(self):
        proc = self._run("No section at all.\n")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("::error::", proc.stdout)
        self.assertIn("Verification section", proc.stdout)

    def test_cli_fails_when_pr_commits_is_set_and_the_cited_id_is_foreign(self):
        # A commit id copied from another PR (spec decision 4): the format
        # check alone would accept it, but it is not a prefix of anything in
        # this PR's own PR_COMMITS, fetched by the workflow from the GitHub
        # API.
        body = "## Verification\n\nRan 307 tests … OK, commit abc1234.\n"
        proc = self._run(body, pr_commits=["deadbee" + "0" * 33])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("abc1234", proc.stdout)

    def test_cli_passes_when_pr_commits_matches_the_cited_prefix(self):
        body = "## Verification\n\nRan 307 tests … OK, commit abc1234.\n"
        proc = self._run(body, pr_commits=["abc1234" + "0" * 33])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("pr evidence: ok", proc.stdout)

    def test_cli_unset_pr_commits_keeps_todays_behaviour(self):
        body = "## Verification\n\nRan 307 tests … OK, commit 5d6b77378.\n"
        proc = self._run(body, pr_commits=None)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_main_function_matches_the_cli(self):
        # main() itself (not just the subprocess) reads PR_BODY and returns
        # the same exit status, exercised directly for coverage of the
        # in-process path the CLI test above cannot see.
        old = os.environ.get("PR_BODY")
        try:
            os.environ["PR_BODY"] = "## Verification\n\nRan 1 test OK, commit abc1234.\n"
            self.assertEqual(main([]), 0)
        finally:
            if old is None:
                os.environ.pop("PR_BODY", None)
            else:
                os.environ["PR_BODY"] = old


if __name__ == "__main__":
    unittest.main()
