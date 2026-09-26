# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""The PR-evidence gate: a pull request into `main` must cite a printed test
count and a commit id in its own description, not just claim "tests pass".

`check(body)` is the rule (docs/superpowers/specs/2026-09-26-pr-stewardship.md,
decision 3; the plan's Global constraints name the exact patterns): find the
`Verification` section — a Markdown heading (`#` through `####`) or a bold
paragraph (`**Verification**`), matched case-insensitively — and, inside it
only, require both a printed test count (`Ran <N> test(s)`, unittest's own
line, or `of <N> tests`, Odoo's `odoo.tests.result` line) and a commit id (7
to 40 lowercase hex characters, as a whole word). A heading-form section ends
before the next heading of the same or higher level; a bold-paragraph-form
section runs to the end of the body, since nothing marks its end the way a
heading's level does.

Evidence appearing only *before* the section does not count (rule f of the
plan's Task 1): the section boundaries are computed first, and the two
patterns are searched for only inside them.

A commit id is a whole-word run of 7 to 40 lowercase hex characters that
either contains at least one letter a-f, or is exactly 40 hex characters
long. This excludes a bare decimal run such as an issue or PR reference
(`#1234567`), which is 7-40 digits but neither has a hex letter nor reaches
the full 40-character length of a real SHA.

`check(body, pr_commits=None)` also takes the PR's own commit ids (spec
decision 4; Corrections after review item 8): when `pr_commits` is given and
non-empty, at least one cited id in the Verification section must be a
prefix of one of them, or the check fails naming the cited id(s). This
catches a stale or copied commit id that merely *looks* like a SHA. Passing
`None` (or an empty list) skips this cross-check entirely and reproduces the
format-only rule exactly -- the CLI's behaviour when `PR_COMMITS` is unset.
`pr_commits` is meant to come from the GitHub API
(`GET /repos/{repo}/pulls/{number}/commits`), not a local `git rev-list`: a
shallow, two-endpoint checkout (this repo's own CI pattern) has no commit
graph to walk, only the two endpoint trees.

Standard library only. CLI: reads `PR_BODY`, and optionally `PR_COMMITS` (a
whitespace-separated list of full commit SHAs), from the environment (never
from a shell-interpolated `${{ }}` in the calling workflow), prints one
`::error::<message>` per failure and exits 1, or prints `pr evidence: ok` and
exits 0.
"""
from __future__ import annotations

import os
import re
import sys

_HEADING_RE = re.compile(r"^(#{1,4})\s+verification\s*:?\s*$", re.IGNORECASE)
_ANY_HEADING_RE = re.compile(r"^(#{1,4})\s+\S")
_BOLD_RE = re.compile(r"^\*\*verification\*\*", re.IGNORECASE)

_COUNT_RE = re.compile(r"\bran\s+\d+\s+tests?\b|\bof\s+\d+\s+tests\b", re.IGNORECASE)
_SHA_CANDIDATE_RE = re.compile(r"\b[0-9a-f]{7,40}\b")

_NO_SECTION = "the PR description has no Verification section"
_NO_COUNT = "the Verification section has no printed test count (e.g. 'Ran N tests' or 'of N tests')"
_NO_SHA = "the Verification section has no commit id (7-40 lowercase hex characters, with a letter a-f, or 40 hex characters)"


def _is_commit_id(token: str) -> bool:
    """A candidate whole-word hex run counts as a commit id only when it
    could not plausibly be a bare decimal reference (e.g. `#1234567`): it
    either has at least one a-f letter, or is the full 40-character length
    of a real SHA."""
    return len(token) == 40 or any(ch in "abcdef" for ch in token)


def _cited_commit_ids(text: str) -> list:
    """The distinct, correctly-shaped commit-id candidates in `text`, in the
    order they first appear."""
    seen = []
    for token in _SHA_CANDIDATE_RE.findall(text):
        if _is_commit_id(token) and token not in seen:
            seen.append(token)
    return seen


def _no_match_error(candidates, pr_commits) -> str:
    ids = ", ".join(candidates)
    return (
        f"the Verification section cites {ids}, but that does not match any "
        f"commit in this pull request ({len(pr_commits)} commit(s) checked, "
        "fetched from the GitHub API)"
    )


def _find_section(lines: list) -> "tuple[int, int] | None":
    """The (start, end) line range of the Verification section, start
    inclusive and end exclusive, or None when no section marker is found.

    The first marker encountered, scanning top to bottom, wins: a heading
    ends the section before the next heading at the same or higher level (a
    smaller `#` count); a bold paragraph has no such marker, so it runs to
    the end of the body.
    """
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            end = len(lines)
            for later in range(index + 1, len(lines)):
                other = _ANY_HEADING_RE.match(lines[later].strip())
                if other and len(other.group(1)) <= level:
                    end = later
                    break
            return index, end
        if _BOLD_RE.match(stripped):
            return index, len(lines)
    return None


def check(body, pr_commits=None) -> list:
    """The list of evidence problems in `body`; empty means the PR passes.

    `pr_commits`, when truthy, is the PR's own full commit SHAs: at least one
    cited id must then be a prefix of one of them (see the module docstring).
    """
    if not body or not body.strip():
        return [_NO_SECTION]

    lines = body.splitlines()
    section = _find_section(lines)
    if section is None:
        return [_NO_SECTION]

    start, end = section
    section_text = "\n".join(lines[start:end])

    errors = []
    if not _COUNT_RE.search(section_text):
        errors.append(_NO_COUNT)
    candidates = _cited_commit_ids(section_text)
    if not candidates:
        errors.append(_NO_SHA)
    elif pr_commits and not any(sha.startswith(c) for c in candidates for sha in pr_commits):
        errors.append(_no_match_error(candidates, pr_commits))
    return errors


def main(argv=None) -> int:
    del argv  # The body comes from the environment, never argv (see module docstring).
    raw_commits = os.environ.get("PR_COMMITS")
    pr_commits = raw_commits.split() if raw_commits else None
    errors = check(os.environ.get("PR_BODY"), pr_commits)
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print("pr evidence: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
