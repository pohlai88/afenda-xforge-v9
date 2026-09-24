# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_industry_base.tests.common import IndustryPackMixin

MODULE = "afenda_industry_bakery"


# post_install, not at_install: odoo/modules/loading.py:148,282 runs a module's
# at_install suite the moment that module loads, which for a pack can be before
# the rest of the graph is up. Task 1 hit exactly that -- res.partner without
# account's NOT NULL autopost_bills column (addons/account/models/partner.py:610)
# -- and the result was a suite that passed under -i and errored under -u. Every
# industry pack carries this tag for that reason; do not remove it.
@tagged("post_install", "-at_install")
class TestBakeryPack(IndustryPackMixin, TransactionCase):
    """The bakery preset: what it installs, and what it must never install."""

    def test_products_and_categories_installed(self):
        categories = self.env["ir.model.data"].search_count(
            [("module", "=", MODULE), ("model", "=", "product.category")]
        )
        self.assertEqual(categories, 3)
        products = self.env["ir.model.data"].search_count(
            [("module", "=", MODULE), ("model", "=", "product.template")]
        )
        self.assertEqual(products, 25, "10 raw + 12 finished + 3 packaging")

    def test_raw_materials_use_expiration(self):
        flour = self.env.ref(f"{MODULE}.product_flour_t55")
        self.assertTrue(flour.is_storable)
        self.assertEqual(flour.tracking, "lot")
        self.assertTrue(
            flour.use_expiration_date,
            "a bakery's reason for an ERP is shelf life; raw materials must carry it",
        )
