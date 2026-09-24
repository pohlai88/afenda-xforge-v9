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

## Tests and acceptance

`afenda_industry_base` — 4 tests in `tests/test_seed.py`:

1. `test_load_company_records_assigns_xmlid`
2. `test_load_company_records_is_idempotent`
3. `test_load_company_records_uses_env_company`

`afenda_industry_bakery` — 9 tests in `tests/test_pack.py`:

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

Expected: `afenda_industry_base: 4 tests`, `afenda_industry_bakery: 9 tests`. A run that
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
