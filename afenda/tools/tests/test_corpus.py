import difflib
import io
import unittest

from afenda.tools.corpus import CORPUS, GOLDEN, emit_utf8, rewrite_corpus
from afenda.tools.rules import RULES


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

    def test_direct_write_to_the_same_stream_would_raise(self):
        # Establishes that the cp1252 stream used above is a faithful stand-in for the
        # real defect: writing the same text to it the naive way (plain .write(), as
        # corpus.py did before this fix) still raises UnicodeEncodeError.
        _, stream = self._cp1252_stream()
        with self.assertRaises(UnicodeEncodeError):
            stream.write("diff line with ỗ in it\n")

    def test_falls_back_to_plain_write_without_a_buffer(self):
        stream = io.StringIO()
        text = "diff line with ỗ in it\n"

        emit_utf8(text, stream=stream)

        self.assertEqual(stream.getvalue(), text)
