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
        seven tests below still resolve to TransactionCase through a base named
        in this file.
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

    def test_boms_resolve_components(self):
        """Every finished good is manufacturable, out of this pack's own raw materials.

        The headers ship in data/mrp_bom.xml; the lines cannot. mrp.bom.line
        .product_id is a product.product (addons/mrp/models/mrp_bom.py:684) and
        the variant Odoo auto-creates for a template seeded by XML carries no
        XMLID of its own, so no `ref=` can name it. The lines are therefore
        seeded in Python, where env.ref(...).product_variant_id resolves.
        """
        boms = self.env["mrp.bom"].search(
            [("product_tmpl_id.categ_id", "=", self.env.ref(f"{MODULE}.categ_finished").id)]
        )
        self.assertEqual(len(boms), 12, "one bill of material per finished good")
        # The row count alone does not say "one *per* product". An edit adding a
        # second BoM on sourdough while dropping bom_focaccia leaves twelve rows
        # and a focaccia nobody can manufacture; the distinct template count is
        # what closes that.
        self.assertEqual(
            len(boms.product_tmpl_id),
            12,
            "twelve BoMs spread over fewer than twelve products means some "
            "finished good has none",
        )
        raw = self.env.ref(f"{MODULE}.categ_raw")
        for bom in boms:
            self.assertTrue(bom.bom_line_ids, f"{bom.display_name} has no components")
            for line in bom.bom_line_ids:
                self.assertEqual(
                    line.product_id.categ_id,
                    raw,
                    f"{bom.display_name} consumes {line.product_id.display_name}, "
                    f"which is not a raw material",
                )
                self.assertGreater(line.product_qty, 0.0)

    def test_pos_config_belongs_to_env_company(self):
        config = self.env.ref(f"{MODULE}.pos_config_counter")
        self.assertEqual(config.company_id, self.env.company)
        self.assertEqual(
            config.picking_type_id.warehouse_id.company_id,
            self.env.company,
            "picking_type_id is required with a domain on warehouse_id.company_id "
            "(addons/point_of_sale/models/pos_config.py:76-82)",
        )

    def test_post_init_records_are_module_owned(self):
        """Uninstall can reach everything the hook created.

        mrp.bom.line is deliberately absent from this list. The lines carry no
        XMLID of their own -- `bom_line_ids` writes create them without any
        ir.model.data entry -- and they do not need one: mrp.bom.line.bom_id is
        ondelete='cascade' (addons/mrp/models/mrp_bom.py:701-703), so they go
        when the module-owned header goes. Adding them here would assert an
        ownership that by design does not exist.
        """
        self.assert_records_are_module_owned(MODULE, "pos.config", 1)
        self.assert_records_are_module_owned(MODULE, "stock.warehouse.orderpoint", 10)

    def test_bom_component_quantities_are_converted(self):
        """The recipe unit on every component line, bounded per UoM.

        `RECIPES` is written in grams and `_seed_bom_lines` writes the lines in
        grams, because the obvious alternative does not survive the ORM:
        mrp.bom.line.product_qty carries digits='Product Unit'
        (addons/mrp/models/mrp_bom.py:688-690), that precision ships at 2
        decimals, and 2 g of yeast divided into the product's own kilograms is
        stored as 0.00 -- a croissant with no yeast in it. Six lines in this
        pack land on exactly that, and 5 g of salt survives only as 0.01 kg.

        So the regression this guards is a thousandfold error in either
        direction, and the bound has to be per-UoM because the invariant is.

        Grams: every legitimate value is between 1 (yeast, vanilla) and 700
        (focaccia's flour). A line that was divided by 1000 and left in grams is
        below 1; a kilogram figure mistakenly labelled grams would have to be
        under a gram to pass, which no recipe here is.

        Kilograms: a hard failure, not a bound. A kg line means somebody
        reintroduced the division, and the small components are already zero by
        the time this test could measure them.
        """
        gram = self.env.ref("uom.product_uom_gram")
        units = self.env.ref("uom.product_uom_unit")
        lines = self.env["mrp.bom"].search(
            [("product_tmpl_id.categ_id", "=", self.env.ref(f"{MODULE}.categ_finished").id)]
        ).bom_line_ids
        self.assertTrue(lines, "no components to check")
        for line in lines:
            if line.product_uom_id == gram:
                self.assertGreaterEqual(
                    line.product_qty, 1.0,
                    f"{line.bom_id.display_name} consumes {line.product_qty} g of "
                    f"{line.product_id.display_name}; the smallest real component "
                    f"is 1 g, so this is a gram figure that got divided by 1000",
                )
                self.assertLessEqual(
                    line.product_qty, 700.0,
                    f"{line.bom_id.display_name} consumes {line.product_qty} g of "
                    f"{line.product_id.display_name}; the largest real component "
                    f"is 700 g",
                )
            elif line.product_uom_id == units:
                self.assertLessEqual(
                    line.product_qty, 12.0,
                    f"{line.bom_id.display_name} consumes {line.product_qty} "
                    f"{line.product_id.display_name}; the largest real count is 8",
                )
                self.assertEqual(
                    line.product_qty, int(line.product_qty),
                    f"{line.product_id.display_name} is counted in whole units",
                )
            else:
                self.fail(
                    f"{line.bom_id.display_name} consumes "
                    f"{line.product_id.display_name} in {line.product_uom_id.name}. "
                    f"This pack weighs in grams and counts in Units; a kilogram "
                    f"line in particular means the grams were divided by 1000, "
                    f"which rounds the small components to zero at the shipped "
                    f"2-decimal 'Product Unit' precision"
                )

    def test_reordering_rules_cover_raw_materials(self):
        raw = self.env.ref(f"{MODULE}.categ_raw")
        rules = self.env["stock.warehouse.orderpoint"].search(
            [("product_id.categ_id", "=", raw.id)]
        )
        self.assertEqual(len(rules), 10)
        for rule in rules:
            self.assertEqual(rule.company_id, self.env.company)
            self.assertGreater(rule.product_max_qty, rule.product_min_qty)
