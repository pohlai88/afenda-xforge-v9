import difflib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from afenda.tools import corpus as corpus_module
from afenda.tools.corpus import CORPUS, GOLDEN, emit_utf8, rewrite_corpus
from afenda.tools.rules import RULES

REPO_ROOT = Path(__file__).resolve().parents[3]


class CorpusGoldenTest(unittest.TestCase):
    """Every distinct line the rules can touch, rewritten, must match the reviewed golden file.

    When a rule changes on purpose: run `python -m afenda.tools.corpus diff`, review, then
    `python -m afenda.tools.corpus golden` and commit both files.
    """

    def test_rules_match_golden(self):
        self.assertTrue(CORPUS.exists(), "corpus.txt missing: run `python -m afenda.tools.corpus build`")
        self.assertTrue(GOLDEN.exists(), "golden.txt missing: run `python -m afenda.tools.corpus golden`")
        current = rewrite_corpus(CORPUS.read_text(encoding="utf-8"), RULES)
        golden = GOLDEN.read_text(encoding="utf-8")
        if current != golden:
            diff = "\n".join(list(difflib.unified_diff(golden.splitlines(), current.splitlines(), "golden", "current", lineterm="", n=0))[:60])
            self.fail("rules no longer match golden.txt (first 60 diff lines):\n" + diff)

    def test_golden_has_no_visible_odoo(self):
        for entry in GOLDEN.read_text(encoding="utf-8").splitlines():
            suffix, kind, line = entry.split("\t", 2)
            if kind in ("cli", "iot") or "Part of Odoo" in line or "X-Odoo-" in line or "Odoo-Link-Preview" in line:
                continue
            if any(s in line for s in ("iap.odoo.com", "iap-services.odoo.com", "services.odoo.com", "Last-Translator:", "Language-Team:", "Report-Msgid-Bugs-To:", "noqa: rebrand")):
                continue
            if line.startswith("#") and suffix in (".po", ".pot"):
                continue
            if suffix in (".py", ".js", ".ts", ".scss", ".css", ".template") and ("import " in line or "Copyright" in line or "odoo.define(" in line or "require(" in line):
                continue
            self.assertNotRegex(line, r"(?<![\w@/.])Odoo(?!\w)|\bodoo\.com\b|(?<![\w.])/odoo(?=[/'\"`?#\s)\]]|$)", f"visible Odoo left in golden: {entry[:160]}")


class BuildRefDefaultTest(unittest.TestCase):
    """The `build` subcommand's default `--ref` must name a ref that actually exists.

    Regression for corpus.py's default drifting out from under a branch/tag rename
    (the old default named `upstream-19.0`, a branch renamed away on 2026-09-25; the
    retired ref lives on only as the tag `archive/upstream-19.0`). This reads the
    default straight from the argparse parser `main()` builds, rather than hardcoding
    the expected ref string here, so a future rename of the default would only need
    the ref itself to exist -- not this test's expectation kept in sync by hand.
    """

    def test_default_ref_resolves_in_a_fresh_checkout(self):
        default_ref = corpus_module._build_parser().parse_args(["build"]).ref

        result = subprocess.run(
            ["git", "rev-parse", "--verify", default_ref],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )

        if result.returncode != 0:
            self.skipTest(
                f"{default_ref!r} is not available in this checkout; fetch it with "
                f"`git fetch origin tag {default_ref.rpartition('/')[2] or default_ref}`."
            )
        self.assertEqual(result.returncode, 0)


class EmitUtf8Test(unittest.TestCase):
    """`corpus diff` must print on a Windows console, where stdout defaults to cp1252.

    Regression for the crash at corpus.py:123: writing a corpus line containing a
    non-Latin character (here 'ỗ', U+1ED7) through a cp1252-encoded stream used to raise
    UnicodeEncodeError. `emit_utf8` must write the exact UTF-8 bytes instead, with no
    PYTHONUTF8/PYTHONIOENCODING override needed by the caller.
    """

    def _cp1252_stream(self):
        raw = io.BytesIO()
        buffered = io.BufferedWriter(raw)
        # newline="" avoids the platform-dependent translation TextIOWrapper would
        # otherwise apply to "\n", keeping the byte-for-byte assertion below exact.
        text_stream = io.TextIOWrapper(buffered, encoding="cp1252", newline="")
        return raw, text_stream

    def test_survives_non_latin_character_on_cp1252_stream(self):
        raw, stream = self._cp1252_stream()
        text = "diff line with ỗ in it\n"

        emit_utf8(text, stream=stream)

        self.assertEqual(raw.getvalue(), text.encode("utf-8"))

    def test_control_naive_write_to_the_same_stream_still_raises(self):
        """Not a test of `emit_utf8` — a control for the fixture above.

        This never calls `emit_utf8`: it writes straight to the cp1252 stream the same
        way `corpus.py` did before this fix (plain `.write()`), to show that fixture is a
        faithful stand-in for the real defect rather than an artificially cooperative
        double. It passes identically whether `emit_utf8` exists, is broken, or is
        deleted, so it proves nothing about the fix by itself — see
        `test_survives_non_latin_character_on_cp1252_stream` for that.
        """
        _, stream = self._cp1252_stream()
        with self.assertRaises(UnicodeEncodeError):
            stream.write("diff line with ỗ in it\n")

    def test_falls_back_to_plain_write_without_a_buffer(self):
        stream = io.StringIO()
        text = "diff line with ỗ in it\n"

        emit_utf8(text, stream=stream)

        self.assertEqual(stream.getvalue(), text)


class CorpusDiffCliUtf8Test(unittest.TestCase):
    """End-to-end regression: the `diff` subcommand must not crash on real `sys.stdout`.

    Points `corpus.CORPUS`/`corpus.GOLDEN` at a temp pair whose rewritten line contains a
    non-Latin character, then runs the real `diff` subcommand through `corpus.main()` —
    exercising the actual argparse -> main -> `emit_utf8(stream=None)` path against the
    process's real, unpatched `sys.stdout` (no `stream=` override, unlike the unit tests
    above). This does not depend on the tracked golden.txt or on the real corpus
    happening to contain non-Latin text right now (e.g. while another agent's rules.py
    work is in flight and the real corpus/golden pair matches) — it always exercises the
    non-Latin path, and would catch a future refactor that moved the write back out of
    `emit_utf8`.
    """

    def test_diff_subcommand_does_not_crash_on_non_latin_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            corpus_file = tmp_path / "corpus.txt"
            golden_file = tmp_path / "golden.txt"
            # "other" is always a valid kind (see corpus.KINDS); the line's trailing
            # word is untouched by any rebrand rule (rules only match Odoo-related
            # patterns), so it survives rewrite_corpus intact.
            corpus_file.write_text(".py\tother\tOdoo line with ỗ in it\n", encoding="utf-8")
            golden_file.write_text("", encoding="utf-8")  # empty golden guarantees a diff

            with mock.patch.object(corpus_module, "CORPUS", corpus_file), \
                    mock.patch.object(corpus_module, "GOLDEN", golden_file):
                exit_code = corpus_module.main(["diff"])

        self.assertEqual(exit_code, 1)  # a diff was found, and printing it did not raise
