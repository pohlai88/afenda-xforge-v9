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

    def _pack_records(self, model):
        """The records of `model` this module owns, as a recordset.

        Not a `test_` method, so afenda_brand's collection guard ignores it; the
        two tests below still resolve to TransactionCase through a base named in
        this file.
        """
        data = self.env["ir.model.data"].search(
            [("module", "=", MODULE), ("model", "=", model)]
        )
        return self.env[model].browse(data.mapped("res_id"))

    def test_products_and_categories_installed(self):
        self.assertEqual(len(self._pack_records("product.category")), 3)
        products = self._pack_records("product.template")
        self.assertEqual(len(products), 25, "10 raw + 12 finished + 3 packaging")

        # The row count alone cannot see the split, so on its own the message
        # above asserts a fact it does not check -- it would pass on 25/0/0.
        # _read_group, not read_group: the latter is deprecated in 19.0
        # (odoo/orm/models.py:1867 is the supported entry point).
        raw = self.env.ref(f"{MODULE}.categ_raw")
        finished_categ = self.env.ref(f"{MODULE}.categ_finished")
        packaging = self.env.ref(f"{MODULE}.categ_packaging")
        split = {
            category.id: count
            for category, count in self.env["product.template"]._read_group(
                [("id", "in", products.ids)],
                groupby=["categ_id"],
                aggregates=["__count"],
            )
        }
        self.assertEqual(
            split,
            {raw.id: 10, finished_categ.id: 12, packaging.id: 3},
            "10 raw + 12 finished + 3 packaging, and nothing in a fourth category",
        )

        # available_in_pos defaults to False
        # (addons/point_of_sale/models/product_template.py:24), so a finished
        # good that does not set it is absent from the Bakery Counter grid Task 4
        # builds -- the pack would install clean and configure nothing.
        finished = products.filtered(lambda p: p.categ_id == finished_categ)
        self.assertFalse(
            finished.filtered(lambda p: not p.available_in_pos).mapped("name"),
            "every finished good must be available in the POS this pack configures",
        )

        # sale_ok defaults True and list_price defaults 1.0
        # (addons/product/models/product_template.py:116,94-99): an ingredient or
        # a wrapper left at the default is quotable at 1.00 by any salesperson.
        not_for_sale = products.filtered(lambda p: p.categ_id in (raw | packaging))
        self.assertEqual(len(not_for_sale), 13)
        self.assertFalse(
            not_for_sale.filtered("sale_ok").mapped("name"),
            "raw materials and packaging are purchased and consumed, never sold",
        )

    def test_raw_materials_use_expiration(self):
        raws = self._pack_records("product.template").filtered(
            lambda p: p.categ_id == self.env.ref(f"{MODULE}.categ_raw")
        )
        self.assertEqual(len(raws), 10, "the catalogue's ten raw materials")
        self.assertFalse(
            raws.filtered(lambda p: not p.is_storable).mapped("name"),
            "a raw material whose inventory is not tracked cannot be consumed by a BoM",
        )
        self.assertFalse(
            raws.filtered(lambda p: p.tracking != "lot").mapped("name"),
            "lot tracking is what makes a recall possible; every raw material carries it",
        )
        self.assertFalse(
            raws.filtered(lambda p: not p.use_expiration_date).mapped("name"),
            "a bakery's reason for an ERP is shelf life; raw materials must carry it",
        )
        # The flag alone expires nothing: expiration_time is the day count Odoo
        # adds to the receipt date (addons/product_expiry/models/product_product.py,
        # class ProductTemplate), and it defaults to 0.
        self.assertFalse(
            raws.filtered(lambda p: p.expiration_time <= 0).mapped("name"),
            "use_expiration_date with a zero expiration_time expires nothing",
        )
