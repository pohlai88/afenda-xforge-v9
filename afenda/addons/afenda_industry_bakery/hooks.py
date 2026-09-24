# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Company-scoped seeding for the bakery pack.

Everything here exists because it cannot honestly be written as XML: the
records either carry a required `company_id` or need a variant resolved in
Python. See afenda_industry_base/seed.py for why that matters at uninstall.
"""
from odoo.addons.afenda_industry_base.seed import load_company_records

MODULE = "afenda_industry_bakery"

# (bom xmlid suffix, [(raw product xmlid suffix, quantity in GRAMS)])
#
# GRAMS, and the lines are written in grams too -- they are NOT divided by 1000
# into the raw's own kilograms. That division is the obvious reading of this
# table and it is wrong, for a reason the ORM makes non-negotiable:
# mrp.bom.line.product_qty carries digits='Product Unit'
# (addons/mrp/models/mrp_bom.py:688-690) and that precision ships at 2 decimals,
# so 2 g of yeast divided into kilograms is stored as 0.00 and the croissant has
# no yeast in it at all. Six of this pack's lines land on exactly that, and 5 g
# of salt survives only as 0.01 kg, a fivefold error.
#
# mrp.bom.line.product_uom_id is a separate field from the product's own UoM for
# exactly this case, and grams relate to kilograms through uom.product_uom_kgm's
# relative_uom_id (addons/uom/data/uom_data.xml:95-99), so Odoo converts at
# consumption. Eggs are stocked in Units and are counted, not weighed.
#
# The hazard this removes is a thousandfold one in both directions: read the
# table as kilograms and a sourdough loaf eats 600 kg of flour; divide it and
# the small components vanish. test_bom_component_quantities_are_converted
# bounds both ends and is the only guard on either.
RECIPES = [
    ("bom_sourdough", [("product_flour_t55", 600), ("product_salt", 12),
                       ("product_yeast", 8), ("product_milk", 30)]),
    ("bom_baguette", [("product_flour_t55", 250), ("product_salt", 5),
                      ("product_yeast", 4)]),
    ("bom_wholemeal", [("product_flour_t55", 420), ("product_salt", 9),
                       ("product_yeast", 6)]),
    ("bom_croissant", [("product_flour_t55", 55), ("product_butter", 30),
                       ("product_sugar", 6), ("product_yeast", 2),
                       ("product_milk", 20)]),
    ("bom_pain_choc", [("product_flour_t55", 55), ("product_butter", 30),
                       ("product_chocolate", 15), ("product_sugar", 6),
                       ("product_yeast", 2)]),
    ("bom_almond_croissant", [("product_flour_t55", 55), ("product_butter", 30),
                              ("product_almond_powder", 25), ("product_sugar", 10),
                              ("product_yeast", 2)]),
    ("bom_brioche", [("product_flour_t55", 400), ("product_butter", 160),
                     ("product_sugar", 50), ("product_eggs", 4),
                     ("product_yeast", 10), ("product_milk", 80)]),
    ("bom_cinnamon_roll", [("product_flour_t55", 70), ("product_butter", 25),
                           ("product_sugar", 30), ("product_yeast", 3),
                           ("product_milk", 25)]),
    ("bom_eclair", [("product_flour_t55", 40), ("product_butter", 30),
                    ("product_eggs", 1), ("product_chocolate", 25),
                    ("product_milk", 60)]),
    ("bom_fruit_tart", [("product_flour_t55", 45), ("product_butter", 25),
                        ("product_sugar", 20), ("product_eggs", 1),
                        ("product_vanilla", 2)]),
    ("bom_birthday_cake", [("product_flour_t55", 500), ("product_butter", 300),
                           ("product_sugar", 400), ("product_eggs", 8),
                           ("product_chocolate", 200), ("product_vanilla", 10)]),
    ("bom_focaccia", [("product_flour_t55", 700), ("product_salt", 15),
                      ("product_yeast", 10)]),
]

# (raw product xmlid suffix, min qty, max qty) in the product's own UoM
REORDER_RULES = [
    ("product_flour_t55", 50.0, 200.0),
    ("product_butter", 20.0, 80.0),
    ("product_sugar", 15.0, 60.0),
    ("product_yeast", 3.0, 12.0),
    ("product_salt", 5.0, 20.0),
    ("product_eggs", 120.0, 600.0),
    ("product_milk", 20.0, 80.0),
    ("product_chocolate", 10.0, 40.0),
    ("product_almond_powder", 5.0, 20.0),
    ("product_vanilla", 1.0, 4.0),
]


def _variant(env, suffix):
    """The product.product behind a seeded product.template."""
    return env.ref(f"{MODULE}.{suffix}").product_variant_id


def _seed_bom_lines(env):
    """Fill the BoM headers from data/mrp_bom.xml.

    Each line is written in the unit the recipe is actually measured in -- grams
    for the nine weighed raws, Units for eggs -- and never converted into the
    product's own kilograms. See the note on RECIPES: at the shipped 'Product
    Unit' precision of 2 decimals a converted 2 g component rounds to zero.

    The lines are the one record in this pack with no XMLID of their own:
    `bom_line_ids` writes create mrp.bom.line rows that ir.model.data never
    sees. Spec ruling 5 holds for them transitively -- mrp.bom.line.bom_id is
    ondelete='cascade' (addons/mrp/models/mrp_bom.py:701-703), so uninstalling
    the module deletes the module-owned header and the lines go with it. That
    is why test_post_init_records_are_module_owned enumerates only pos.config
    and stock.warehouse.orderpoint.
    """
    for bom_suffix, components in RECIPES:
        bom = env.ref(f"{MODULE}.{bom_suffix}")
        if bom.bom_line_ids:
            continue  # already seeded; the hook is safe to re-run
        gram = env.ref("uom.product_uom_gram")
        lines = []
        for product_suffix, quantity in components:
            product = _variant(env, product_suffix)
            # Eggs are counted in their own UoM; everything else is weighed, and
            # the figure in RECIPES is already the gram count.
            uom = product.uom_id if product_suffix == "product_eggs" else gram
            lines.append((0, 0, {
                "product_id": product.id,
                "product_qty": float(quantity),
                "product_uom_id": uom.id,
            }))
        bom.write({"bom_line_ids": lines})


def _seed_pos(env):
    """One counter, two POS categories, and the finished goods put on them.

    Task 2 sets `available_in_pos` on the twelve finished goods, which is what
    makes them sellable at all (it defaults to False --
    addons/point_of_sale/models/product_template.py:24). Their POS *category* has
    to be assigned here instead, because the categories do not exist until this
    hook creates them.

    Creating the pos.config needs the company to already have a chart of
    accounts: `payment_method_ids` defaults through
    `_create_journal_and_payment_methods`, which raises "Ensure that there is an
    existing bank journal" when it finds none
    (addons/point_of_sale/models/pos_config.py:1060-1063). That is upstream's
    rule -- point_of_sale itself only ever creates a config from demo data, for
    the same reason -- and it has one sharp edge worth knowing: `account` defers
    loading the chart to `_register_hook`
    (addons/account/models/ir_module.py:102-104), which runs after the whole
    module graph, while a post_init_hook runs during it
    (odoo/modules/loading.py:243). So this pack installs cleanly onto a database
    where accounting is already set up, and fails loudly in the one case where
    `account` is being installed in the same run -- a green-field
    `-i afenda_industry_bakery` on an empty database. Install the dependencies
    first, then the pack.

    Only `pos_categ_ids` is written on those templates. product_expiry's
    ProductTemplate.write() clears `use_expiration_date` whenever `tracking` is
    written as 'none' (addons/product_expiry/models/product_product.py:56-59),
    so nothing here may fold a `tracking` value into these writes.
    """
    bread, pastry = load_company_records(env, MODULE, "pos.category", [
        ("pos_categ_bread", {"name": "Bread"}),
        ("pos_categ_pastry", {"name": "Pastry"}),
    ])
    load_company_records(env, MODULE, "pos.config", [
        ("pos_config_counter", {"name": "Bakery Counter"}),
    ])
    loaves = ("product_sourdough", "product_baguette", "product_wholemeal",
              "product_focaccia", "product_brioche")
    for suffix in loaves:
        env.ref(f"{MODULE}.{suffix}").pos_categ_ids = [(6, 0, bread.ids)]
    pastries = ("product_croissant", "product_pain_choc", "product_almond_croissant",
                "product_cinnamon_roll", "product_eclair", "product_fruit_tart",
                "product_birthday_cake")
    for suffix in pastries:
        env.ref(f"{MODULE}.{suffix}").pos_categ_ids = [(6, 0, pastry.ids)]


def _seed_orderpoints(env):
    """Replenishment for the raw materials, in the company's own warehouse."""
    warehouse = env["stock.warehouse"].search(
        [("company_id", "=", env.company.id)], limit=1
    )
    if not warehouse:
        return
    records = []
    for suffix, min_qty, max_qty in REORDER_RULES:
        product = _variant(env, suffix)
        records.append((f"orderpoint_{suffix.removeprefix('product_')}", {
            "product_id": product.id,
            "warehouse_id": warehouse.id,
            "location_id": warehouse.lot_stock_id.id,
            "product_min_qty": min_qty,
            "product_max_qty": max_qty,
        }))
    load_company_records(env, MODULE, "stock.warehouse.orderpoint", records)


def post_init_hook(env):
    _seed_bom_lines(env)
    _seed_pos(env)
    _seed_orderpoints(env)
