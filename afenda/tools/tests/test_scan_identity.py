import tempfile
import unittest
from pathlib import Path

from afenda.tools import scan_identity


class BaselineTests(unittest.TestCase):
    """The scanner is a regression gate, not a zero-tolerance check.

    Phase 1 deliberately leaves identity in contexts the rules must not touch
    (translator attribution, package imports, API payload identifiers), so a
    non-zero count is the expected steady state. The gate is that it must not
    rise.
    """

    def test_baseline_is_recorded_and_not_zero(self):
        self.assertIsInstance(scan_identity.BASELINE, int)
        self.assertGreater(scan_identity.BASELINE, 0)

    def test_holding_at_the_baseline_passes(self):
        self.assertEqual(scan_identity.verdict(scan_identity.BASELINE), 0)

    def test_one_new_hit_fails(self):
        self.assertEqual(scan_identity.verdict(scan_identity.BASELINE + 1), 1)

    def test_a_drop_passes(self):
        self.assertEqual(scan_identity.verdict(scan_identity.BASELINE - 500), 0)


class ScanTests(unittest.TestCase):
    """Unit coverage for `scan()` itself, on a small temp tree.

    The four `BaselineTests` above only exercise `verdict()`, a one-line ternary; none
    of them calls `scan()`, which is where the actual SUSPECT/ALLOW/STRUCTURAL regexes
    and the two path exclusions (`odoo/cli/`, `iot_box_image`) live. A regression there
    -- e.g. ALLOW accidentally widened so it swallows a real identity hit -- would only
    be caught by the full-tree `scan_identity` gate, which CLAUDE.md says runs once per
    unit of work, not per edit. These tests close that gap cheaply, with no full-tree
    walk needed.
    """

    def _tree(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    def test_a_genuine_odoo_mention_is_reported(self):
        root = self._tree({"addons/foo/models/thing.py": "label = 'Odoo makes this'\n"})

        hits = scan_identity.scan(root)

        self.assertEqual(len(hits), 1)
        rel, lineno, line = hits[0]
        self.assertEqual(rel, "addons/foo/models/thing.py")
        self.assertEqual(lineno, 1)
        self.assertIn("Odoo makes this", line)

    def test_an_allow_listed_import_line_is_not_reported(self):
        root = self._tree({
            "addons/foo/models/thing.py": "import odoo\nlabel = 'Odoo makes this'\n",
        })

        hits = scan_identity.scan(root)

        # The ALLOW-listed import on line 1 is not reported; the genuine hit on
        # line 2 still is -- proving the line was scanned, not the whole file skipped.
        self.assertEqual([(rel, lineno) for rel, lineno, _ in hits], [("addons/foo/models/thing.py", 2)])

    def test_odoo_cli_and_iot_box_image_paths_are_excluded(self):
        root = self._tree({
            "odoo/cli/server.py": "print('Odoo command line')\n",
            "addons/iot_box_image/build.py": "print('Odoo image build')\n",
            "addons/foo/models/thing.py": "print('Odoo elsewhere')\n",
        })

        hits = scan_identity.scan(root)

        reported = {rel for rel, _, _ in hits}
        self.assertEqual(reported, {"addons/foo/models/thing.py"})


if __name__ == "__main__":
    unittest.main()
