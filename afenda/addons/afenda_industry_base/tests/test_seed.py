# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_industry_base.seed import load_company_records

MODULE = "afenda_industry_base"


# post_install is required, not stylistic. Odoo runs a module's at_install suite
# the moment that module loads, inside the graph walk
# (odoo/modules/loading.py:148 iterates the graph, :282 runs the suite). This
# module depends on `base` alone, so under `-u` it sits at graph depth 1 and its
# tests would run before `account` is loaded -- while `account`'s
# res.partner.autopost_bills column (addons/account/models/partner.py:610) is
# already NOT NULL in the database. The seeded partner would then be INSERTed
# without that column and Postgres would reject it. Running post_install waits
# for the whole registry, so the suite passes under `-u` and `-i` alike. Do not
# remove this tag: `-u` is the documented command in
# .claude/odoo-agent-rules.md:186-190, and every industry pack copies this shape.
@tagged("post_install", "-at_install")
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

    def test_load_company_records_skips_company_on_company_less_model(self):
        """The `pin_company is False` branch: a model with no `company_id`.

        `pos.category` is the real downstream case, but point_of_sale is not a
        dependency of this module. `res.partner.category` is the same shape in
        `base`: no `company_id` field (odoo/addons/base/models/res_partner.py:140-154).
        Without this, seeding any company-less model is untested and a
        `company_id` passed to a model that has none would raise at install.
        """
        model = "res.partner.category"
        self.assertNotIn(
            "company_id",
            self.env[model]._fields,
            f"{model} was chosen because it has no company_id; if that changed, "
            f"this test no longer covers the pin_company is False branch",
        )
        records = load_company_records(
            self.env, MODULE, model, [("seed_tag_a", {"name": "Seed Tag A"})]
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(self.env.ref(f"{MODULE}.seed_tag_a"), records)
        self.assertEqual(records.name, "Seed Tag A")
