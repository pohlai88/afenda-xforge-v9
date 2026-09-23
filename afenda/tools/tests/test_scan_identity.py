import unittest

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


if __name__ == "__main__":
    unittest.main()
