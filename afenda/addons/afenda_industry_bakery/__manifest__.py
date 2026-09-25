# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "Bakery",
    "summary": "AFENDA preset for a bakery: catalogue, recipes, counter and replenishment",
    "version": "19.0.1.0.0",
    "category": "Industries",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": True,
    "auto_install": False,
    # mrp_account and stock_account are named explicitly rather than left to be
    # pulled in transitively: the pack's value is costed production, and a
    # reader should not have to derive that from mrp's own dependencies.
    "depends": [
        "afenda_industry_base",
        "mrp",
        "mrp_account",
        "pos_sale",
        "purchase_stock",
        "stock_account",
        "product_expiry",
    ],
    # No security/ directory on purpose: this pack declares no models, and a
    # module that adds no models adds no ir.model.access.csv lines. It ships
    # data records of models that already carry their own ACLs. The absence is
    # deliberate, not forgotten -- same contract as
    # afenda_industry_base/__manifest__.py:12-14.
    # Ordered: a file that references an XML id comes after the file defining it,
    # which is why data/mrp_bom.xml follows data/product_template.xml -- every
    # BoM header names a product template by ref.
    "data": [
        "data/res_groups.xml",
        "data/product_category.xml",
        "data/product_template.xml",
        "data/mrp_bom.xml",
    ],
    # Business history only: suppliers, draft purchase orders and a draft
    # manufacturing order. Never under `data`, which production loads; see
    # demo/bakery_demo.xml for what shapes each record.
    "demo": [
        "demo/bakery_demo.xml",
    ],
    # Runs once, at install, and never on -u: odoo/modules/loading.py:239-243
    # fires it only when update_operation == 'install'. Everything it seeds is
    # either company-scoped (the POS counter, its categories, the ten
    # reordering rules) or needs a product.product resolved from a template
    # XMLID (every BoM line), so none of it can be written as data/ XML. See
    # hooks.py and afenda_industry_base/seed.py. It requires the installing
    # company to already have a chart of accounts; see _seed_pos for why, and
    # for the one install order that cannot satisfy that.
    "post_init_hook": "post_init_hook",
}
