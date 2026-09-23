"""Drift protection for the committed `afenda_api_docs/views/guides.xml`.

`build_docs.py`'s own docstring has claimed since it was written that a
`test_guides_in_sync` test holds the generated file honest, but no such test
existed anywhere in the repo — the string appeared only in that docstring.
This is the test the docstring promised: regenerate the guides to a temp
file from the same committed Markdown sources and compare, byte for byte,
against the committed `views/guides.xml`. A hand-edit of the XML, or a stale
regeneration after editing a `.md` source, fails this test.

Needs no database, so it lives in `afenda/tools/tests/` and runs in the fast
`python -m unittest discover afenda/tools/tests` suite.
"""
import tempfile
import unittest
from pathlib import Path

from afenda.tools.build_docs import OUT, SRC, build


class GuidesInSyncTests(unittest.TestCase):
    def test_guides_in_sync(self):
        committed = OUT.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            regenerated_path = Path(tmp) / "guides.xml"
            build(SRC, regenerated_path)
            regenerated = regenerated_path.read_text(encoding="utf-8")
        self.assertEqual(
            regenerated,
            committed,
            "afenda_api_docs/views/guides.xml is out of sync with its "
            "Markdown sources under afenda_api_docs/docs/ — regenerate it "
            "with `python -m afenda.tools.build_docs`.",
        )


if __name__ == "__main__":
    unittest.main()
