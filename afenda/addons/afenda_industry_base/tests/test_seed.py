# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from odoo.tests import TransactionCase

from odoo.addons.afenda_industry_base.seed import load_company_records

MODULE = "afenda_industry_base"


class TestSeed(TransactionCase):
    """`load_company_records` is what keeps a pack uninstallable-clean."""

    def test_load_company_records_assigns_xmlid(self):
        records = load_company_records(
            self.env, MODULE, "res.partner", [("seed_partner_a", {"name": "Seed A"})]
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(self.env.ref(f"{MODULE}.seed_partner_a"), records)

    def test_load_company_records_is_idempotent(self):
        first = load_company_records(
            self.env, MODULE, "res.partner", [("seed_partner_b", {"name": "Seed B"})]
        )
        second = load_company_records(
            self.env, MODULE, "res.partner", [("seed_partner_b", {"name": "Seed B"})]
        )
        self.assertEqual(first, second, "a second call must reuse the XMLID, not create a twin")
        self.assertEqual(
            self.env["res.partner"].search_count([("name", "=", "Seed B")]), 1
        )

    def test_load_company_records_uses_env_company(self):
        records = load_company_records(
            self.env, MODULE, "res.partner", [("seed_partner_c", {"name": "Seed C"})]
        )
        self.assertEqual(records.company_id, self.env.company)
