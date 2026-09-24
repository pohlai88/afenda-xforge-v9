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
    # Ordered: a file that references an XML id comes after the file defining it.
    # Only the two files that exist as of this task are listed. Odoo resolves
    # every `data` path at install and raises on a missing one, so a manifest
    # naming data/mrp_bom.xml (Task 3) or demo/bakery_demo.xml (Task 6) would
    # fail this task's own verification run before reaching an assertion. Each
    # later task adds its line in the commit that creates the file.
    "data": [
        "data/product_category.xml",
        "data/product_template.xml",
    ],
}
