import difflib
import unittest

from afenda.tools.corpus import CORPUS, GOLDEN, rewrite_corpus
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
