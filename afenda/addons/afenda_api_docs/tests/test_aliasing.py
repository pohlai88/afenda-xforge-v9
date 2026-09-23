from odoo.tests import BaseCase

from odoo.addons.afenda_brand.brand import BRAND
from odoo.addons.afenda_api_docs.aliasing import alias_prose


class TestAliasProse(BaseCase):
    def test_capitalised_product_name(self):
        self.assertEqual(alias_prose("Powered by Odoo"), "Powered by AFENDA xForge")

    def test_lowercase_is_aliased_too(self):
        # The file-level rules skip lowercase because a file has imports and
        # license headers to protect. A prose field has neither.
        self.assertEqual(alias_prose("sent from odoo"), "sent from AFENDA xForge")

    def test_legal_name_beats_product_name(self):
        self.assertEqual(alias_prose("Copyright Odoo S.A."), "Copyright AFENDA")

    def test_bot_name(self):
        self.assertEqual(alias_prose("Ask OdooBot"), "Ask AFENDA Bot")

    def test_domain(self):
        # Read the expectation from BRAND rather than hard-coding it: aliasing.py
        # substitutes BRAND["domain"], so a hard-coded value here goes stale the
        # moment the real domain lands and tests a string nothing produces.
        self.assertEqual(
            alias_prose("see odoo.com for more"),
            f"see {BRAND['domain']} for more",
        )

    def test_documentation_link_goes_same_origin(self):
        self.assertEqual(
            alias_prose("read https://www.odoo.com/documentation/19.0/x.html"),
            "read /docs/x.html",
        )

    def test_identifiers_embedded_in_prose_survive(self):
        # Word boundaries: these are field names a reader may need verbatim.
        for identifier in ("odoobot_state", "odoobot_failed", "delete_odoo"):
            self.assertIn(identifier, alias_prose(f"Set {identifier} to done"))

    def test_dotted_wire_values_survive(self):
        # `\b` alone is satisfied by a dot on either side, so a naive
        # `\bodoo\b` would split these into "AFENDA xForge.BALANCE" etc.
        # ODOO.BALANCE, ODOO.PIVOT and friends are real spreadsheet function
        # names in this codebase and must reach the reader unchanged.
        for wire_value in ("ODOO.BALANCE", "ODOO.PIVOT.HEADER", "res.odoo.field"):
            self.assertIn(wire_value, alias_prose(f"Use {wire_value} here"))

    def test_sentence_ending_period_still_aliases(self):
        # A trailing "." is punctuation, not a dotted wire token, so this
        # must not fall into the same guard that protects ODOO.BALANCE.
        self.assertEqual(alias_prose("This runs on odoo."), "This runs on AFENDA xForge.")

    def test_none_and_empty_pass_through(self):
        self.assertIsNone(alias_prose(None))
        self.assertEqual(alias_prose(""), "")

    def test_is_idempotent(self):
        once = alias_prose("Odoo and odoo and odoo.com")
        self.assertEqual(alias_prose(once), once)
