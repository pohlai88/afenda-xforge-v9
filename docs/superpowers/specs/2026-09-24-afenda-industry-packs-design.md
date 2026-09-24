# AFENDA industry preset packs — foundation and bakery pilot

Date: 2026-09-24. Status: **design approved in conversation; implementation plan to follow.**
Scope: `afenda_industry_base` (the pack contract) and `afenda_industry_bakery` (the pilot).

## Why we build these rather than adopt `odoo/industry`

`https://github.com/odoo/industry` branch `19.0` carries 113 modules with a manifest.
Measured on 2026-09-24 by resolving each manifest's dependency closure against the 707
modules present in this tree (`addons/`, `odoo/addons/`, `afenda/addons/`, the two OCA
submodules):

| measurement | result |
|---|---|
| modules with a manifest | 113 |
| distinct licences declared | `{'OEEL-1': 113}` |
| installable here as-is | **0** |
| blocked by `knowledge` | 107 |
| blocked by `web_studio` | 53 |
| blocked only by authoring sugar (`knowledge`, `web_studio`, `social`) | 14 |

The tree also cannot be checked out on Windows: `git restore` fails with `Filename too
long` on demo attachments such as
`bakery/static/src/binary/ir_attachment/1269-Croissants!@formatdmd#food#...jpeg`.

So adoption is not on the table, and none of their content is copied. What the
measurement buys is the *shape* question answered with evidence: the 14 modules blocked
only by authoring sugar are the vertical shapes reachable on Community dependencies, and
they cluster in retail/POS, distribution and light manufacturing. The pilot is chosen
from that set.

## Approach

Three were considered:

- **A — a preset *is* an addon.** Module install loads the records; uninstall removes
  them; `module upgrade --outdated` (already how the deploy init ships changes) carries
  new versions.
- **B — a preset is data applied by an AFENDA service**, with an AFENDA-owned provenance
  ledger.
- **C — hybrid**: packs ship as modules but route content through an AFENDA seed layer.

**A is chosen.** Three reasons, in order of weight:

1. `docs/superpowers/specs/2026-09-23-afenda-platform-architecture.md` rules *break
   infrastructure coupling first, keep transactional business coupling intact*. A preset
   pack is business **content**, not a platform boundary — it is not what that doctrine
   protects.
2. B's ledger re-implements `ir.model.data`, which already records exactly which records
   a module created and already drives clean uninstall
   (`odoo/addons/base/models/ir_model.py:2464-2471`). Duplicated truth, not owned truth.
3. C is an abstraction with exactly one consumer, and every line of it is permanent fork
   surface.

"Apply a pack to a live tenant without installing a module" remains possible later as a
G4 control-plane feature built *on* A. It is not a reason to build B now.

## Module: `afenda/addons/afenda_industry_base`

The pack contract. Small on purpose.

- **No models.** Therefore no `security/ir.model.access.csv`; a module that adds no
  models adds no access lines, and the manifest says so in a comment so the absence
  reads as deliberate rather than forgotten.
- **`seed.py`** — the one piece of real machinery. Company-scoped records are created
  through `_load_records` (`odoo/orm/models.py:5121`, docstring: *"Create or update
  records of this model, and assign XMLIDs"*, taking `xml_id`, `noupdate`, `values`)
  with an explicit `xml_id`, never through a bare `create()`.

  This is the single most important rule in the design. Uninstall deletes records
  *referenced by `ir.model.data` entries* (`ir_model.py:2464-2471`); a `post_init_hook`
  that calls `create()` directly therefore leaves orphan POS configs and reordering
  rules in the tenant's database forever. `seed.py` exists so that mistake cannot be
  written.

  No separate "already seeded" guard: `_load_records` partitions existing xml_ids into
  the *update* set rather than re-creating them (`models.py:5121-5165`), so it is
  idempotent by construction.
- **`tests/common.py`** — `IndustryPackMixin`, carrying the shared assertions. It
  declares **no `test_` methods** and does **not** subclass `TransactionCase`.

  Both constraints come from `afenda_brand`'s
  `test_every_test_class_would_actually_be_collected`
  (`afenda/addons/afenda_brand/tests/test_branding.py:1501-1562`): it AST-walks every
  `afenda/addons/*/tests/*.py`, resolves base classes **only within the same file**
  (`:1553-1561`), and flags any class with `test_` methods whose reachable bases miss
  Odoo's case classes. A pack test written as `class TestBakeryPack(IndustryPackCase)`
  would resolve to `{IndustryPackCase}`, miss `odoo_cases`, and **fail the afenda_brand
  suite**. Packs therefore declare:

  ```python
  class TestBakeryPack(IndustryPackMixin, TransactionCase):
  ```

  and the mixin is skipped by the guard because it has no `test_` methods (`:1563-1567`).

Manifest: `version 19.0.1.0.0`, `license LGPL-3`, `author AFENDA`,
`category Hidden/Tools`, `application False`.

## Module: `afenda/addons/afenda_industry_bakery`

`depends`: `afenda_industry_base`, `mrp`, `mrp_account`, `pos_sale`, `purchase_stock`,
`stock_account`, `product_expiry`. All verified present in `addons/`.
`category Industries`, `application True`.

| layer | where | content |
|---|---|---|
| Product categories | `data` | Finished Goods, Raw Materials, Packaging — no account properties |
| Products | `data` | Exactly 25: 12 finished, 10 raw, 3 packaging. The counts are fixed here because test 4 asserts them; changing the catalogue means changing the test in the same commit |
| Shelf life | `data` | Raw materials `tracking='lot'` with `use_expiration_date` — a field on **`product.template`** (`addons/product_expiry/models/product_product.py`, class `ProductTemplate`), not on `product.product` |
| Bills of material | `data` | One per finished good; components consumed in grams from kg-stocked raws |
| POS config + POS categories | `post_init_hook` | One "Bakery Counter", against `env.company` |
| Reordering rules | `post_init_hook` | On raw materials, bound to the company's warehouse |
| Suppliers, POs, MOs, a POS session, 3 employees | `demo` | Never loaded in production |

`post_init_hook(env)` takes the single-`env` form used by
`afenda/addons/afenda_brand/hooks.py:98` and `afenda_runtime/__init__.py:6`.

## Rulings

**1. No company pinning in XML.** Company-scoped records are created in the hook against
`env.company`, never as XML records.

Evidence: `pos.config.company_id` is `required=True, default=lambda self: self.env.company`
(`addons/point_of_sale/models/pos_config.py:143`) and `pos.config.picking_type_id` is
`required=True` with domain
`[('code','=','outgoing'), ('warehouse_id.company_id','=',self.env.company.id)]`
(`:76-82`). `stock.warehouse` is company-scoped (`addons/stock/models/stock_warehouse.py:37`)
and `stock.warehouse.orderpoint` carries `check_company=True` on product, location and
warehouse (`addons/stock/models/stock_orderpoint.py:40,44,51`). An XML record resolves
those defaults against whichever company happens to load the file — correct for a
single-company demo, wrong for a multi-tenant product.

**Known limitation, stated rather than papered over.** The hook does not make the pack
company-*selectable*. At install the environment is `api.Environment(cr, api.SUPERUSER_ID, {})`
(`odoo/modules/loading.py:404`) — empty context, so `env.company` resolves to the
superuser's default company, not the company the admin was viewing when they clicked
install. In a multi-company database, installing from company B seeds company A. Found in
review of Task 1, before the hook had a caller.

What the hook still buys over XML, which is the part that survives: it can *search* for
the installing company's warehouse and bind the orderpoints and POS config to it
(`stock.warehouse.orderpoint` carries `check_company=True` on product, location and
warehouse, so a mismatch is a hard error, not a silent wrong row). XML cannot express
that lookup at all. The company *target* is the same either way; the company
*consistency* is only achievable in Python.

Making the target selectable means either a setting read at install or a post-install
wizard. Both are the G4 control-plane work this spec already defers under "out of scope",
so the limitation is documented and deliberately not engineered around. The cost of being
wrong is bounded: a multi-company tenant that installs from the wrong company gets the
pack in the main company, and since every record is module-owned (ruling 5), uninstalling
and reinstalling moves it cleanly. No data is lost.

**The same exposure exists in the `data/` XML, and this ruling previously read as though
it did not.** `product.template.standard_price` is a non-stored compute whose inverse
`_set_standard_price` writes `product.product.standard_price`
(`addons/product/models/product_template.py:100-106,312-318`), and that field is
`company_dependent=True` (`addons/product/models/product_product.py:62`). So the thirteen
costs in the catalogue land in the per-company store for whichever company `env.company`
resolves to at load — the same limitation as above, reached through XML rather than the
hook. In a two-company tenant, company B sees a flour cost of 0.00, and every MO
valuation, replenishment cost and margin figure downstream reads zero **with no error
anywhere**.

Ruling 5's static guard cannot catch it either: `test_data_xml_sets_no_company_id` scans
for the *field name* `company_id`, and `standard_price` does not contain it. Found in
review of Task 2. Accepted on the same terms as the hook limitation — bounded, now
documented, and properly answered by the G4 control plane rather than by a per-company
XML scheme Odoo's data loader has no way to express.

**2. No accounts, taxes or journals anywhere in the pack.** Not on product categories,
not on products. Those xml_ids exist only once a specific `l10n_*` chart is installed, so
hard-coding them makes the pack install in one country and fail in the rest. Everything
falls back to company defaults.

**3. `data` is configuration; `demo` is business history.** Production installs run
`--without-demo=all`, so this split is the difference between a pack that configures a
real tenant and one that pollutes it with fake transactions. Odoo's own industry packs
blur it; ours does not.

**4. Pack content is `noupdate="1"`.** Once a tenant owns their product list, an upgrade
must not overwrite their prices. Corrections ship as a version bump plus an explicit
migration, the pattern `afenda_brand`'s manifest already documents. The development cost
is understood: re-running `-u` will not refresh seeded data, so iterating on pack content
means reinstalling the module.

**5. Every record the pack creates is module-owned**, XML or hook alike — the
precondition for ruling 4's uninstall story, enforced by a test rather than by care.

Two exceptions, both found in review of Task 4 and both documented rather than engineered
around:

**BoM lines are owned transitively, not directly.** `bom.write({"bom_line_ids": …})`
creates `mrp.bom.line` rows with no `ir.model.data` entry. Uninstall still removes them,
because they cascade from a module-owned header (`mrp.bom.line.bom_id` is
`ondelete='cascade'`, `addons/mrp/models/mrp_bom.py:697-699`). The ownership test
therefore enumerates `pos.config` and `stock.warehouse.orderpoint` only; adding
`mrp.bom.line` to it would fail for a record that is nonetheless cleaned up correctly.

**Creating a `pos.config` makes Odoo create records the pack cannot own.**
`_create_journal_and_payment_methods` (`addons/point_of_sale/models/pos_config.py:1032-1073`)
creates a Cash `account.journal` and Cash and Card `pos.payment.method` records. The
`_update_xmlids` branch at `:1049-1054` only fires when a `cash_ref` is supplied, which
`load_company_records` does not pass, so none of them get an `ir.model.data` row. A tenant
who uninstalls the pack loses the counter but keeps two payment methods and a journal in
their chart. This is unavoidable for any pack that ships a POS counter — Odoo creates
those records as a side effect of the config — so it is stated here rather than implied by
ruling 5's "every record".

**Install order: the pack requires Invoicing to be installed first.** A `pos.config` needs
a bank journal, therefore a chart of accounts
(`addons/point_of_sale/models/pos_config.py:1060-1063`). `account` defers chart loading to
`_register_hook` (`addons/account/models/ir_module.py:97-104`), which runs *after* the
whole module graph, while `post_init_hook` runs *during* it
(`odoo/modules/loading.py:239-243`). So the pack cannot be installed in the same run that
first installs `account` — which is both the single-run CI shape and the Apps-menu click
on a stock database. The pack pre-flights the bank journal and raises an error naming
itself and the remedy, rather than either failing with POS's generic message or silently
shipping without its till.

**Known limitation: components finer than the stock unit's precision round to zero on very
small manufacturing orders.** `uom.uom.rounding` is not per-unit —
`_compute_rounding` returns `10 ** -precision_get('Product Unit')`
(`addons/uom/models/uom_uom.py:62-66`), which ships at 2 decimals — so a raw move's
quantity is rounded in the product's stock unit. Croissant yeast at 2 g means an MO for one
or two croissants moves `0.00` kg of yeast and does not deplete stock; by three croissants
it rounds to `0.01` and by a realistic batch it is exact (500 croissants demand a full
kilogram). The exposure is therefore single-digit manufacturing orders on the three finest
raws, not manufacturing generally — a review flagged it with a 500-unit scenario, which
does not hold because demand scales with the order. Recorded rather than fixed: stocking
yeast, salt and vanilla in grams would remove it, at the cost of a catalogue and
replenishment change whose value has not been demonstrated.

## Tests and acceptance

`afenda_industry_base` — 4 tests in `tests/test_seed.py`:

1. `test_load_company_records_assigns_xmlid`
2. `test_load_company_records_is_idempotent`
3. `test_load_company_records_uses_env_company`

`afenda_industry_bakery` — 11 tests in `tests/test_pack.py`:

4. `test_products_and_categories_installed`
5. `test_boms_resolve_components`
6. `test_pos_config_belongs_to_env_company`
7. `test_post_init_records_are_module_owned`
8. `test_reordering_rules_cover_raw_materials`
9. `test_raw_materials_use_expiration`
10. `test_data_xml_sets_no_company_id`
11. `test_data_xml_hardcodes_no_accounts_or_taxes`
12. `test_data_xml_has_no_transactional_records`

Tests 10–12 are **static scans of the pack's own XML**, deliberately: a static check
holds even when the relevant localization is not installed in the test database, and it
catches a future edit that reintroduces the mistake. Test 7 replaces the
"uninstall is clean" test that cannot honestly be written — a real uninstall mutates the
registry and cannot run inside a `TransactionCase`, so the design asserts the
`ir.model.data` ownership that *causes* clean uninstall instead.

Acceptance, per module, reading the printed count and never the exit code:

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -i afenda_industry_bakery --test-enable \
  --test-tags "/afenda_industry_bakery" --stop-after-init --http-port 8179
```

Expected: `afenda_industry_base: 4 tests`, `afenda_industry_bakery: 11 tests`. A run that
prints no count collected nothing. The `afenda_brand` suite runs once at the end too,
because its collection guard now has two new addons in scope.

## Out of scope

- Work orders and routings — `mrp_workorder` is Enterprise. Manufacturing stays at MO level.
- Click-and-collect and any website surface.
- The other nine Community-reachable verticals. They follow the contract this pilot
  proves, as separate units of work.
- Applying a pack to a running tenant without a module install — a G4 control-plane
  feature, not this.

## Risks

| Risk | Mitigation |
|---|---|
| Seeded content is opinionated and a tenant wants none of it | Packs are opt-in modules and uninstall cleanly (ruling 5) |
| `noupdate` means we cannot fix shipped content | Accepted deliberately; fixes ship as a migration |
| The foundation is shaped by one vertical | Why the pilot is end-to-end rather than ten thin packs: pack #2 tests the contract before nine more depend on it |
