from odoo.tests import BaseCase

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
        self.assertEqual(alias_prose("see odoo.com for more"), "see afenda.app for more")

    def test_documentation_link_goes_same_origin(self):
        self.assertEqual(
            alias_prose("read https://www.odoo.com/documentation/19.0/x.html"),
            "read /docs/x.html",
        )

    def test_identifiers_embedded_in_prose_survive(self):
        # Word boundaries: these are field names a reader may need verbatim.
        for identifier in ("odoobot_state", "odoobot_failed", "delete_odoo"):
            self.assertIn(identifier, alias_prose(f"Set {identifier} to done"))

    def test_none_and_empty_pass_through(self):
        self.assertIsNone(alias_prose(None))
        self.assertEqual(alias_prose(""), "")

    def test_is_idempotent(self):
        once = alias_prose("Odoo and odoo and odoo.com")
        self.assertEqual(alias_prose(once), once)
