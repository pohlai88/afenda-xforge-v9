# AFENDA Industry Preset Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `afenda_industry_base` (the pack contract) and `afenda_industry_bakery` (the pilot vertical), so AFENDA has industry presets that install on Community only.

**Architecture:** A preset *is* an Odoo addon. Company-less content (categories, products, BoMs) ships as `data/` XML; company-scoped content (POS config, reordering rules) is created in `post_init_hook(env)` against `env.company` through a shared `seed.load_company_records` helper that assigns an XMLID to every record, so uninstall is clean. No new models, no new engine.

**Tech Stack:** Odoo 19.0 Community, Python 3, `.venv/Scripts/python` only, PostgreSQL `127.0.0.1:5444` database `afenda`, test HTTP port 8179.

**Spec:** `docs/superpowers/specs/2026-09-24-afenda-industry-packs-design.md` (commit `6c3e32c2b`) — read it before Task 1; the rulings there are binding and this plan argues from them.

## Global Constraints

- Root `odoo/` and `addons/` are **pristine — no hand edits, ever**. All work goes under `afenda/addons/<module>/`.
- Python is `.venv/Scripts/python` only. Never the global interpreter.
- Manifest keys on both modules: `"version": "19.0.1.0.0"`, `"license": "LGPL-3"`, `"author": "AFENDA"`, `"website": "https://www.nexuscanon.com"`, and the file opens with the comment `# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.`
- **Odoo 19 field shapes, verified in this tree — do not write these from memory:**
  - `product.template.type` is `consu` / `service` / `combo` only (`addons/product/models/product_template.py:54-65`). `type='product'` does not exist in 19.0.
  - Storability is `is_storable` (Boolean) on `product.template` (`addons/stock/models/product.py:839`); `tracking` is on the same class (`:856`), values `serial` / `lot` / `none`.
  - `use_expiration_date` is on **`product.template`** (`addons/product_expiry/models/product_product.py`, class `ProductTemplate`).
  - `product.product_category_all` **does not exist** in this tree. Pack categories are top-level; `product.category.parent_id` is optional (`addons/product/models/product_category.py:21`).
  - UoM XMLIDs that do exist: `uom.product_uom_unit`, `uom.product_uom_gram`, `uom.product_uom_kgm` (`addons/uom/data/uom_data.xml:12,91,95`). Do not invent others.
  - `post_init_hook(env)` takes a single `env` argument (`afenda/addons/afenda_brand/hooks.py:98`).
- **No `company_id`, no `property_account_*`, no `taxes_id`/`supplier_taxes_id`, no `journal_id`, no `ref="l10n_*"` anywhere under `data/`.** Tasks 5 enforces this with static tests; violating it fails the suite.
- Test classes with `test_` methods must reach an Odoo case class **by a base named in the same file**. Use `class X(IndustryPackMixin, TransactionCase)`. See `afenda/addons/afenda_brand/tests/test_branding.py:1553-1567 (verified at 9be03d305; another session is editing that file, so re-check before trusting the numbers)`.
- **Every industry pack test class carries `@tagged("post_install", "-at_install")`** (import `tagged` from `odoo.tests`), with a comment saying why. Found by Task 1's implementer: `odoo/modules/loading.py:148,282` runs a module's `at_install` suite immediately after that module loads, so a thin-dependency module runs at graph depth 1 — before `account` loads — and `res.partner` then lacks `autopost_bills`, whose column is NOT NULL (`addons/account/models/partner.py:610`). The suite then passes under `-i` and errors under `-u`, which is the documented command in `.claude/odoo-agent-rules.md:186-190`. A pack that only passes when freshly installed is a trap for every later session and splits CI from local runs.
- **`-i <module>` collects nothing on a database where that module is already installed.** `odoo/service/server.py:1598-1599` builds the post-install module list from `registry.updated_modules`, and `-i` on an installed module updates nothing, so the suite selects nothing and prints `0 tests` — which in this quiet config is indistinguishable from success at a glance. Found by Task 1's implementer. Consequences: on a developer machine it is `-u` that runs a suite; and any task whose assertions depend on **install-time** behaviour (anything seeded by `post_init_hook`) must be verified on a **fresh throwaway database**, not on the shared `afenda` one. Create it on `127.0.0.1:5444`, install there, drop it and its filestore afterwards, and never uninstall or otherwise mutate the shared `afenda` database — other sessions are using it.
- **The authoritative test count is the result line** (`<module>: N tests`), not the per-class stats line. `setUpClass`/`tearDownClass` get their own stat ids (`odoo/tests/result.py:117-120`, aggregated `:253-262`), so the stats line reads higher — 5 where the result line says 3. Quote the result line; a CI floor set from the stats line is wrong.
- `tests/__init__.py` must import each `test_*.py`, or the file never loads.
- Verification reads the **printed count**, never the exit code. A green run that collected nothing prints nothing and exits 0.
- Commits: `git add -- <paths> && git commit --only -F <msgfile> -- <paths>` in one shell invocation. Never `git add -A`. Never a full-tree `git status`. Subjects use `[ADD]` / `[FIX]` / `[IMP]`.

---

## File Structure

```
afenda/addons/afenda_industry_base/
  __init__.py              imports seed
  __manifest__.py          depends ['base']; no models, so no security/
  seed.py                  load_company_records() — the one piece of machinery
  tests/__init__.py        imports test_seed (NOT common)
  tests/common.py          IndustryPackMixin — assertions, no test_ methods
  tests/test_seed.py       4 tests

afenda/addons/afenda_industry_bakery/
  __init__.py              imports hooks
  __manifest__.py          post_init_hook, data/, demo/
  hooks.py                 post_init_hook(env) -> POS config, POS categories, orderpoints
  data/product_category.xml
  data/product_template.xml
  data/mrp_bom.xml
  demo/bakery_demo.xml
  tests/__init__.py
  tests/test_pack.py       9 tests
```

`tests/common.py` is deliberately **not** imported by `afenda_industry_base/tests/__init__.py` — it holds no tests of its own, and the bakery pack imports it by path.

---

### Task 1: `afenda_industry_base` — the pack contract

**Files:**
- Create: `afenda/addons/afenda_industry_base/__init__.py`
- Create: `afenda/addons/afenda_industry_base/__manifest__.py`
- Create: `afenda/addons/afenda_industry_base/seed.py`
- Create: `afenda/addons/afenda_industry_base/tests/__init__.py`
- Create: `afenda/addons/afenda_industry_base/tests/common.py`
- Test: `afenda/addons/afenda_industry_base/tests/test_seed.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_company_records(env, module, model_name, records, noupdate=True) -> recordset`, where `records` is a list of `(suffix: str, values: dict)` and the XMLID becomes `f"{module}.{suffix}"`. Also `IndustryPackMixin`, importable as `from odoo.addons.afenda_industry_base.tests.common import IndustryPackMixin`.

- [ ] **Step 1: Write the failing tests**

`afenda/addons/afenda_industry_base/tests/test_seed.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_industry_base.seed import load_company_records

MODULE = "afenda_industry_base"


# post_install is load-bearing here, not habit. odoo/modules/loading.py:148,282
# runs a module's at_install suite immediately after that module loads, and this
# module depends only on `base`, so at_install puts it at graph depth 1 -- before
# `account` loads. res.partner then has no autopost_bills column, which account
# declares NOT NULL (addons/account/models/partner.py:610), and every test that
# creates a partner errors. The suite passed under -i and errored under -u, the
# documented command in .claude/odoo-agent-rules.md:186-190. Do not remove.
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
```

`afenda/addons/afenda_industry_base/tests/__init__.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from . import test_seed
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -i afenda_industry_base --test-enable \
  --test-tags "/afenda_industry_base" --stop-after-init --http-port 8179
```

Expected: the module fails to load with `ModuleNotFoundError` / `ImportError` on `seed`, because `seed.py` does not exist yet. That is the failure you want — not a green run.

- [ ] **Step 3: Write the module skeleton and `seed.py`**

`afenda/addons/afenda_industry_base/__manifest__.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA Industry Packs",
    "summary": "The contract every AFENDA industry preset pack follows",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    # No security/ directory on purpose: this module declares no models, and a
    # module that adds no models adds no ir.model.access.csv lines. The absence
    # is deliberate, not forgotten.
    "depends": ["base"],
}
```

`afenda/addons/afenda_industry_base/__init__.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from . import seed
```

`afenda/addons/afenda_industry_base/seed.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Company-scoped seeding for AFENDA industry packs.

A pack's company-less content (categories, products, bills of material) belongs
in `data/` XML. Its company-scoped content does not: `pos.config.company_id` is
`required=True, default=lambda self: self.env.company`
(addons/point_of_sale/models/pos_config.py:143) and `picking_type_id` is required
with a domain on `warehouse_id.company_id` (:76-82), so an XML record silently
resolves against whichever company happens to load the file. Correct for a
single-company demo, wrong for a multi-tenant product.

Those records are therefore created here, at install, against `env.company` --
and always through `_load_records` (odoo/orm/models.py:5121), which assigns an
XMLID. That is not decoration: uninstall deletes the records *referenced by
ir.model.data entries* (odoo/addons/base/models/ir_model.py:2464-2471), so a
hook that calls `create()` directly leaves orphan POS configs and reordering
rules in the tenant's database forever.

`_load_records` also makes this idempotent by construction: an XMLID that
already exists is routed to the update set rather than created again
(models.py:5121-5165), so no separate "already seeded" guard is needed.
"""


def load_company_records(env, module, model_name, records, noupdate=True):
    """Create or update company-scoped records, each owned by ``module``.

    :param env: environment; records are created against ``env.company``
    :param str module: the pack's technical name, e.g. ``afenda_industry_bakery``
    :param str model_name: the model to seed, e.g. ``pos.config``
    :param records: list of ``(suffix, values)``; the XMLID is ``module.suffix``
    :param bool noupdate: flag stored on the XMLID; ``True`` means a module
        upgrade will not overwrite what the tenant has since edited
    :return: the records, in the order given
    """
    model = env[model_name].sudo()
    # Not every seeded model is company-scoped (`pos.category` is not), so only
    # pin the company where the field actually exists.
    pin_company = "company_id" in model._fields
    data_list = [
        {
            "xml_id": f"{module}.{suffix}",
            "noupdate": noupdate,
            "values": dict(values, company_id=env.company.id) if pin_company else dict(values),
        }
        for suffix, values in records
    ]
    return model._load_records(data_list)
```

`afenda/addons/afenda_industry_base/tests/common.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Shared assertions for industry pack tests.

Deliberately a mixin that does NOT subclass TransactionCase and declares no
`test_` methods. afenda_brand's `test_every_test_class_would_actually_be_collected`
resolves a test class's bases only within the same file
(afenda/addons/afenda_brand/tests/test_branding.py:1553-1561), so a pack test
written as `class TestBakeryPack(IndustryPackCase)` would resolve to
{IndustryPackCase}, miss Odoo's case classes, and fail that guard. Packs
therefore declare `class TestBakeryPack(IndustryPackMixin, TransactionCase)`,
and this mixin is skipped by the guard because it has no `test_` methods (:1563-1567).
"""
import pathlib
# stdlib ElementTree, deliberately. The only input is the pack's own XML,
# shipped in this repo and read from disk -- not user input, no external
# entities. defusedxml is not in the venv and adding a dependency to parse our
# own files is not warranted; upstream Odoo's tests parse with stdlib too
# (addons/account/tests/common.py). Revisit only if this ever reads XML the
# tenant supplies.
import xml.etree.ElementTree as ElementTree

from odoo.modules.module import get_module_path


class IndustryPackMixin:

    def pack_data_files(self, module):
        """Every XML file under the pack's `data/` directory."""
        path = pathlib.Path(get_module_path(module)) / "data"
        return sorted(path.glob("*.xml"))

    def assert_no_field_in_data(self, module, forbidden, why):
        """Assert no `<field name=...>` in data/ uses a forbidden name."""
        offenders = []
        for source in self.pack_data_files(module):
            tree = ElementTree.parse(source)
            for field in tree.iter("field"):
                name = field.get("name")
                if name in forbidden:
                    offenders.append(f"{source.name}: field name={name!r}")
        self.assertFalse(offenders, f"{why}\n  " + "\n  ".join(offenders))

    def assert_no_models_in_data(self, module, forbidden, why):
        """Assert no `<record model=...>` in data/ creates a forbidden model."""
        offenders = []
        for source in self.pack_data_files(module):
            tree = ElementTree.parse(source)
            for record in tree.iter("record"):
                model = record.get("model")
                if model in forbidden:
                    offenders.append(f"{source.name}: record model={model!r}")
        self.assertFalse(offenders, f"{why}\n  " + "\n  ".join(offenders))

    def assert_records_are_module_owned(self, module, model_name, expected_count):
        """Assert the pack owns `expected_count` records of `model_name`.

        This is the invariant that makes uninstall clean
        (odoo/addons/base/models/ir_model.py:2464-2471). It replaces a literal
        uninstall test, which cannot run inside a TransactionCase: uninstalling
        mutates the registry.
        """
        owned = self.env["ir.model.data"].search_count(
            [("module", "=", module), ("model", "=", model_name)]
        )
        self.assertEqual(
            owned,
            expected_count,
            f"{module} should own {expected_count} {model_name} record(s) via "
            f"ir.model.data, found {owned}; records created without an XMLID "
            f"survive uninstall as orphans",
        )
```

- [ ] **Step 4: Run the tests and verify they pass**

Run the Step 2 command again.
Expected, printed on stdout: `afenda_industry_base: 4 tests` with `0 failed, 0 error(s)`. If no count prints at all, nothing was collected — check that `tests/__init__.py` imports `test_seed`.

- [ ] **Step 5: Commit**

```bash
printf '%s\n' "[ADD] industry: the pack contract every AFENDA preset follows" "" \
  "seed.load_company_records creates company-scoped records against env.company" \
  "and gives each an XMLID via _load_records (odoo/orm/models.py:5121). Without" \
  "the XMLID, uninstall cannot reach them: it deletes records referenced by" \
  "ir.model.data entries (ir_model.py:2464-2471), so a hook that calls create()" \
  "leaves orphan POS configs behind forever." "" \
  "The shared assertions ship as a mixin with no test_ methods, because" \
  "afenda_brand's collection guard resolves test bases only within one file" \
  "(test_branding.py:1553-1561)." "" \
  "afenda_industry_base: 4 tests, 0 failed." "" \
  "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" > /tmp/msg1.txt
git add -- afenda/addons/afenda_industry_base && \
git commit --only -F /tmp/msg1.txt -- afenda/addons/afenda_industry_base
```

---

### Task 2: Bakery pack skeleton, categories and products

**Files:**
- Create: `afenda/addons/afenda_industry_bakery/__init__.py`
- Create: `afenda/addons/afenda_industry_bakery/__manifest__.py`
- Create: `afenda/addons/afenda_industry_bakery/data/product_category.xml`
- Create: `afenda/addons/afenda_industry_bakery/data/product_template.xml`
- Create: `afenda/addons/afenda_industry_bakery/tests/__init__.py`
- Test: `afenda/addons/afenda_industry_bakery/tests/test_pack.py`

**Interfaces:**
- Consumes: `IndustryPackMixin` from Task 1.
- Produces: XMLIDs `afenda_industry_bakery.categ_finished`, `.categ_raw`, `.categ_packaging`; product template XMLIDs of the form `.product_<slug>` listed in the catalogue table below. Task 3 and Task 4 reference them by those exact names.

**Catalogue — this is the content, transcribe it exactly.** All products are `type="consu"` with `is_storable` `True`. Raw materials are `tracking="lot"` with `use_expiration_date` `True`; everything else is `tracking="none"`.

| XMLID suffix | name | category | uom | tracking | price field | value |
|---|---|---|---|---|---|---|
| `product_flour_t55` | Flour T55 | raw | kgm | lot | standard_price | 0.85 |
| `product_butter` | Butter | raw | kgm | lot | standard_price | 7.20 |
| `product_sugar` | Caster Sugar | raw | kgm | lot | standard_price | 1.10 |
| `product_yeast` | Fresh Yeast | raw | kgm | lot | standard_price | 3.40 |
| `product_salt` | Fine Salt | raw | kgm | lot | standard_price | 0.60 |
| `product_eggs` | Eggs | raw | unit | lot | standard_price | 0.22 |
| `product_milk` | Whole Milk | raw | kgm | lot | standard_price | 1.05 |
| `product_chocolate` | Dark Chocolate | raw | kgm | lot | standard_price | 9.50 |
| `product_almond_powder` | Almond Powder | raw | kgm | lot | standard_price | 12.00 |
| `product_vanilla` | Vanilla Extract | raw | kgm | lot | standard_price | 45.00 |
| `product_sourdough` | Sourdough Loaf 800g | finished | unit | none | list_price | 5.50 |
| `product_baguette` | Baguette Tradition | finished | unit | none | list_price | 1.40 |
| `product_wholemeal` | Wholemeal Loaf 500g | finished | unit | none | list_price | 3.80 |
| `product_croissant` | Croissant | finished | unit | none | list_price | 1.30 |
| `product_pain_choc` | Pain au Chocolat | finished | unit | none | list_price | 1.50 |
| `product_almond_croissant` | Almond Croissant | finished | unit | none | list_price | 2.20 |
| `product_brioche` | Brioche Loaf | finished | unit | none | list_price | 4.60 |
| `product_cinnamon_roll` | Cinnamon Roll | finished | unit | none | list_price | 2.40 |
| `product_eclair` | Chocolate Eclair | finished | unit | none | list_price | 3.20 |
| `product_fruit_tart` | Fruit Tart Slice | finished | unit | none | list_price | 3.90 |
| `product_birthday_cake` | Birthday Cake | finished | unit | none | list_price | 28.00 |
| `product_focaccia` | Focaccia Tray | finished | unit | none | list_price | 6.50 |
| `product_paper_bag` | Paper Bag Small | packaging | unit | none | standard_price | 0.03 |
| `product_cake_box` | Cake Box | packaging | unit | none | standard_price | 0.45 |
| `product_ribbon` | Ribbon Roll | packaging | unit | none | standard_price | 0.02 |

25 products: 10 raw, 12 finished, 3 packaging.

- [ ] **Step 1: Write the failing tests**

`afenda/addons/afenda_industry_bakery/tests/test_pack.py`:

```python
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
```

`afenda/addons/afenda_industry_bakery/tests/__init__.py`:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from . import test_pack
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -i afenda_industry_bakery --test-enable \
  --test-tags "/afenda_industry_bakery" --stop-after-init --http-port 8179
```

Expected: the module does not exist yet, so the install fails outright. Once Step 3 creates it, a re-run must fail on the assertions, not on import.

- [ ] **Step 3: Write the manifest and the data files**

`afenda/addons/afenda_industry_bakery/__manifest__.py`:

```python
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
```

`afenda/addons/afenda_industry_bakery/__init__.py` — empty but for the licence line.
`hooks.py` does not exist until Task 4, and `__init__.py` is imported at module
load, so importing from it here raises at install:

```python
# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
```

`afenda/addons/afenda_industry_bakery/data/product_category.xml` — complete file:

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Part of AFENDA xForge. See LICENSE file for full copyright and licensing details. -->
<odoo>
    <data noupdate="1">
        <!-- Top-level on purpose: `product.product_category_all` does not exist
             in this tree, and product.category.parent_id is optional
             (addons/product/models/product_category.py:21). No account
             properties are set here: property_account_* XMLIDs only exist once
             a specific l10n_* chart is installed, so setting them would make
             this pack install in one country and fail in every other. -->
        <record id="categ_finished" model="product.category">
            <field name="name">Bakery / Finished Goods</field>
        </record>
        <record id="categ_raw" model="product.category">
            <field name="name">Bakery / Raw Materials</field>
        </record>
        <record id="categ_packaging" model="product.category">
            <field name="name">Bakery / Packaging</field>
        </record>
    </data>
</odoo>
```

`afenda/addons/afenda_industry_bakery/data/product_template.xml` — wrap all 25 records in `<odoo><data noupdate="1"> … </data></odoo>`. Use exactly this shape; the first two records are given in full, and every other row in the catalogue table above follows the same shape with its own values:

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Part of AFENDA xForge. See LICENSE file for full copyright and licensing details. -->
<odoo>
    <data noupdate="1">
        <!-- No company_id, no taxes_id, no property_account_*: see
             docs/superpowers/specs/2026-09-24-afenda-industry-packs-design.md
             rulings 1 and 2. Tests 10 and 11 fail the suite if any reappears. -->
        <record id="product_flour_t55" model="product.template">
            <field name="name">Flour T55</field>
            <field name="type">consu</field>
            <field name="is_storable" eval="True"/>
            <field name="categ_id" ref="categ_raw"/>
            <field name="uom_id" ref="uom.product_uom_kgm"/>
            <field name="tracking">lot</field>
            <field name="use_expiration_date" eval="True"/>
            <field name="expiration_time">270</field>
            <field name="standard_price">0.85</field>
        </record>
        <record id="product_sourdough" model="product.template">
            <field name="name">Sourdough Loaf 800g</field>
            <field name="type">consu</field>
            <field name="is_storable" eval="True"/>
            <field name="categ_id" ref="categ_finished"/>
            <field name="uom_id" ref="uom.product_uom_unit"/>
            <field name="tracking">none</field>
            <field name="list_price">5.50</field>
        </record>
    </data>
</odoo>
```

Raw materials take `expiration_time` in days: flour 270, butter 60, sugar 720, yeast 21, salt 1080, eggs 28, milk 10, chocolate 365, almond powder 180, vanilla 1080.

- [ ] **Step 4: Run the tests and verify they pass**

Re-run the Step 2 command.
Expected: `afenda_industry_bakery: 2 tests`, `0 failed, 0 error(s)`. Two, not nine — the remaining seven arrive in Tasks 3–5.

- [ ] **Step 5: Commit**

```bash
printf '%s\n' "[ADD] industry: the bakery catalogue and its shelf life" "" \
  "25 products across three categories, raw materials lot-tracked with" \
  "expiration dates -- use_expiration_date is a product.template field" \
  "(addons/product_expiry/models/product_product.py, class ProductTemplate)." "" \
  "Written for 19.0 field shapes, not from memory: type is consu/service/combo" \
  "(product_template.py:54-65) and storability is the separate is_storable" \
  "boolean (stock/models/product.py:839). Categories are top-level because" \
  "product.product_category_all does not exist in this tree." "" \
  "afenda_industry_bakery: 2 tests, 0 failed." "" \
  "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" > /tmp/msg2.txt
git add -- afenda/addons/afenda_industry_bakery && \
git commit --only -F /tmp/msg2.txt -- afenda/addons/afenda_industry_bakery
```

---

### Task 3: Bills of material

**Files:**
- Create: `afenda/addons/afenda_industry_bakery/data/mrp_bom.xml`
- Modify: `afenda/addons/afenda_industry_bakery/__manifest__.py` — append `"data/mrp_bom.xml"` to the `data` list, after `data/product_template.xml` (bills of material reference products, so the file must load after them)
- Modify: `afenda/addons/afenda_industry_bakery/tests/test_pack.py` (add one test)

**Interfaces:**
- Consumes: product XMLIDs from Task 2.
- Produces: 12 `mrp.bom` records, XMLIDs `bom_<slug>` matching each finished good's slug (e.g. `bom_sourdough`).

**Recipes — one BoM per finished good, `product_qty` 1, components in the product's own UoM.** `mrp.bom.bom_line_ids.product_id` points at `product.product` (`addons/mrp/models/mrp_bom.py:684`), so each line references the template's variant with `ref="product_<slug>_product_template"`… **no** — reference the template XMLID and let the line resolve the variant is *not* available in XML. Use `product_id` with the product variant XMLID that Odoo creates automatically: for a template XMLID `afenda_industry_bakery.product_flour_t55`, the variant is reachable in XML only via a separate record. To avoid that entirely, **BoM lines are created in the post-init hook alongside the other resolved records** — see Task 4, which has `env.ref(...).product_variant_id` available in Python.

Therefore this task creates only the BoM headers in XML (which take `product_tmpl_id`, a template reference), and Task 4 fills the lines.

| BoM XMLID | finished good | components (grams, or units for eggs) |
|---|---|---|
| `bom_sourdough` | product_sourdough | flour 600, salt 12, yeast 8, milk 30 |
| `bom_baguette` | product_baguette | flour 250, salt 5, yeast 4 |
| `bom_wholemeal` | product_wholemeal | flour 420, salt 9, yeast 6 |
| `bom_croissant` | product_croissant | flour 55, butter 30, sugar 6, yeast 2, milk 20 |
| `bom_pain_choc` | product_pain_choc | flour 55, butter 30, chocolate 15, sugar 6, yeast 2 |
| `bom_almond_croissant` | product_almond_croissant | flour 55, butter 30, almond_powder 25, sugar 10, yeast 2 |
| `bom_brioche` | product_brioche | flour 400, butter 160, sugar 50, eggs 4, yeast 10, milk 80 |
| `bom_cinnamon_roll` | product_cinnamon_roll | flour 70, butter 25, sugar 30, yeast 3, milk 25 |
| `bom_eclair` | product_eclair | flour 40, butter 30, eggs 1, chocolate 25, milk 60 |
| `bom_fruit_tart` | product_fruit_tart | flour 45, butter 25, sugar 20, eggs 1, vanilla 2 |
| `bom_birthday_cake` | product_birthday_cake | flour 500, butter 300, sugar 400, eggs 8, chocolate 200, vanilla 10 |
| `bom_focaccia` | product_focaccia | flour 700, salt 15, yeast 10 |

- [ ] **Step 1: Write the failing test**

Append to `TestBakeryPack` in `tests/test_pack.py`:

```python
    def test_boms_resolve_components(self):
        boms = self.env["mrp.bom"].search(
            [("product_tmpl_id.categ_id", "=", self.env.ref(f"{MODULE}.categ_finished").id)]
        )
        self.assertEqual(len(boms), 12, "one bill of material per finished good")
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
                # Upper bound, and it is the point of this assertion rather than
                # decoration. The recipe table is written in grams and divided by
                # 1000 when seeded, so the largest component in the pack is 700 g
                # of flour = 0.7, and the largest unit component is 8 eggs. Read
                # the table as "the raw's own unit" instead and a loaf consumes
                # 600 kg of flour. Nothing else in the plan would notice: no other
                # assertion looks at component magnitude at all.
                self.assertLess(
                    line.product_qty, 10.0,
                    f"{bom.display_name} consumes {line.product_qty} "
                    f"{line.product_uom_id.name} of {line.product_id.display_name} -- "
                    f"grams were probably seeded without the kilogram conversion",
                )
```

- [ ] **Step 2: Run it and verify it fails**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -u afenda_industry_bakery --test-enable \
  --test-tags "/afenda_industry_bakery:TestBakeryPack.test_boms_resolve_components" \
  --stop-after-init --http-port 8179
```

Expected: FAIL, `0 != 12`.

- [ ] **Step 3: Write `data/mrp_bom.xml` (headers only)**

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Part of AFENDA xForge. See LICENSE file for full copyright and licensing details. -->
<odoo>
    <data noupdate="1">
        <!-- Headers only. Lines live in hooks.py: mrp.bom.line.product_id is a
             product.product (addons/mrp/models/mrp_bom.py:684) and the variant
             of a template seeded here has no XMLID of its own, so the line is
             resolved in Python via product_variant_id. -->
        <record id="bom_sourdough" model="mrp.bom">
            <field name="product_tmpl_id" ref="product_sourdough"/>
            <field name="product_qty">1</field>
            <field name="product_uom_id" ref="uom.product_uom_unit"/>
            <field name="type">normal</field>
        </record>
        <!-- … the remaining 11, same shape, per the recipe table … -->
    </data>
</odoo>
```

- [ ] **Step 4: Confirm it still fails, for the right reason**

Re-run Step 2's command. Expected: still FAIL, now on `has no components` rather than `0 != 12`. Task 4 closes it. Do not commit a red test as green.

- [ ] **Step 5: Commit the headers**

```bash
printf '%s\n' "[ADD] industry: bakery bills of material, headers" "" \
  "Twelve BoM headers, one per finished good. Lines are seeded in Python" \
  "rather than XML: mrp.bom.line.product_id is a product.product" \
  "(addons/mrp/models/mrp_bom.py:684) and an auto-created variant of a seeded" \
  "template carries no XMLID to reference." "" \
  "test_boms_resolve_components still fails on missing components by design;" \
  "the next commit seeds the lines." "" \
  "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" > /tmp/msg3.txt
git add -- afenda/addons/afenda_industry_bakery && \
git commit --only -F /tmp/msg3.txt -- afenda/addons/afenda_industry_bakery
```

---

### Task 4: The post-init hook — BoM lines, POS counter, replenishment

**Files:**
- Create: `afenda/addons/afenda_industry_bakery/hooks.py`
- Modify: `afenda/addons/afenda_industry_bakery/__init__.py` — add `from .hooks import post_init_hook`
- Modify: `afenda/addons/afenda_industry_bakery/__manifest__.py` — add `"post_init_hook": "post_init_hook",`
- Modify: `afenda/addons/afenda_industry_bakery/tests/test_pack.py` (add three tests)

Both manifest and `__init__.py` changes belong in **this** task's commit, not an
earlier one: the hook has nothing to seed until now, and naming it earlier would
break install.

**Interfaces:**
- Consumes: `load_company_records` (Task 1), product and BoM XMLIDs (Tasks 2–3).
- Produces: `post_init_hook(env)`; XMLIDs `pos_config_counter`, `pos_categ_bread`, `pos_categ_pastry`, `orderpoint_<raw slug>` (10 of them).

- [ ] **Step 1: Write the failing tests**

Append to `TestBakeryPack`:

```python
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
        self.assert_records_are_module_owned(MODULE, "pos.config", 1)
        self.assert_records_are_module_owned(MODULE, "stock.warehouse.orderpoint", 10)

    def test_reordering_rules_cover_raw_materials(self):
        raw = self.env.ref(f"{MODULE}.categ_raw")
        rules = self.env["stock.warehouse.orderpoint"].search(
            [("product_id.categ_id", "=", raw.id)]
        )
        self.assertEqual(len(rules), 10)
        for rule in rules:
            self.assertEqual(rule.company_id, self.env.company)
            self.assertGreater(rule.product_max_qty, rule.product_min_qty)
```

- [ ] **Step 2: Run them and verify they fail**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -u afenda_industry_bakery --test-enable \
  --test-tags "/afenda_industry_bakery" --stop-after-init --http-port 8179
```

Expected: FAIL — `ValueError: External ID not found: afenda_industry_bakery.pos_config_counter`.

- [ ] **Step 3: Write `hooks.py`**

```python
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
# GRAMS, not the raw's own unit. Every raw but eggs is stocked in kilograms, so
# these numbers are divided by 1000 in _seed_bom_lines below; eggs are stocked in
# Units and pass through unchanged. Read this table as "the raw's own UoM" and a
# sourdough loaf consumes 600 KILOGRAMS of flour -- a thousandfold error that no
# test in this plan would catch, because nothing asserts component magnitudes.
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

    Gram quantities are expressed against each raw material's own UoM, which is
    kilograms for everything but eggs, so they are divided here rather than
    carried as a second unit on the line.
    """
    for bom_suffix, components in RECIPES:
        bom = env.ref(f"{MODULE}.{bom_suffix}")
        if bom.bom_line_ids:
            continue  # already seeded; the hook is safe to re-run
        lines = []
        for product_suffix, grams in components:
            product = _variant(env, product_suffix)
            qty = float(grams) if product_suffix == "product_eggs" else float(grams) / 1000.0
            lines.append((0, 0, {
                "product_id": product.id,
                "product_qty": qty,
                "product_uom_id": product.uom_id.id,
            }))
        bom.write({"bom_line_ids": lines})


def _seed_pos(env):
    """One counter, two POS categories, and the finished goods put on them.

    Task 2 sets `available_in_pos` on the twelve finished goods, which is what
    makes them sellable at all (it defaults to False --
    addons/point_of_sale/models/product_template.py:24). Their POS *category* has
    to be assigned here instead, because the categories do not exist until this
    hook creates them.
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
```

- [ ] **Step 4: Verify on a fresh database — this task cannot be verified on the shared one**

`post_init_hook` runs at install only, and `-i` against the shared `afenda` database (where the pack is already installed from Task 2) updates nothing and therefore collects nothing — `0 tests`, which reads like success. Three of this task's assertions are about records the hook creates, so they must be exercised on a database where the install genuinely happens. Do **not** uninstall the pack from the shared database; other sessions are using it.

```bash
DB=afenda_t4_scratch
createdb -h 127.0.0.1 -p 5444 -U odoo "$DB"
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d "$DB" -i afenda_industry_bakery --test-enable \
  --test-tags "/afenda_industry_bakery" --stop-after-init --http-port 8179 \
  --without-demo=all
```

Expected: `afenda_industry_bakery: 6 tests`, `0 failed, 0 error(s)`. A `0 tests` line means the module was already installed there — use a database name that does not exist yet.

Afterwards drop the scratch database **and its filestore** (`filestore/<db>` under Odoo's data directory, path from `odoo.tools.config`); a leftover filestore makes later attachment-backed failures read as code regressions.

If `test_post_init_records_are_module_owned` fails, a record was created with `create()` instead of `load_company_records` — fix the hook, not the test.

- [ ] **Step 5: Commit**

```bash
printf '%s\n' "[ADD] industry: bakery counter, recipes and replenishment" "" \
  "The POS config, its categories and ten reordering rules are created at" \
  "install against env.company, never in XML: pos.config.picking_type_id is" \
  "required with a domain on warehouse_id.company_id" \
  "(addons/point_of_sale/models/pos_config.py:76-82), so an XML record resolves" \
  "it against whichever company loads the file." "" \
  "Every one of them is created through load_company_records, so uninstall can" \
  "reach them (ir_model.py:2464-2471). test_post_init_records_are_module_owned" \
  "asserts exactly that." "" \
  "afenda_industry_bakery: 6 tests, 0 failed." "" \
  "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" > /tmp/msg4.txt
git add -- afenda/addons/afenda_industry_bakery && \
git commit --only -F /tmp/msg4.txt -- afenda/addons/afenda_industry_bakery
```

---

### Task 5: The static guards

**Files:**
- Modify: `afenda/addons/afenda_industry_bakery/tests/test_pack.py` (add three tests)

**Interfaces:**
- Consumes: `assert_no_field_in_data`, `assert_no_models_in_data` from `IndustryPackMixin` (Task 1).
- Produces: nothing further.

These three are static scans of the pack's own XML rather than runtime checks, because a static check holds even when the relevant localization is not installed in the test database — and it catches the future edit that reintroduces the mistake.

- [ ] **Step 1: Write the tests**

```python
    def test_data_xml_sets_no_company_id(self):
        self.assert_no_field_in_data(
            MODULE,
            {"company_id"},
            "data/ must not pin a company: XML resolves it against whichever "
            "company loads the file. Company-scoped records belong in hooks.py.",
        )

    def test_data_xml_hardcodes_no_accounts_or_taxes(self):
        self.assert_no_field_in_data(
            MODULE,
            {
                "property_account_income_categ_id",
                "property_account_expense_categ_id",
                "property_account_creditor_price_difference_categ",
                "property_stock_account_input_categ_id",
                "property_stock_account_output_categ_id",
                "property_stock_valuation_account_id",
                "taxes_id",
                "supplier_taxes_id",
                "journal_id",
            },
            "accounts, taxes and journals only exist once a specific l10n_* "
            "chart is installed; hard-coding them breaks every other country.",
        )
        for source in self.pack_data_files(MODULE):
            body = source.read_text(encoding="utf-8")
            self.assertNotIn(
                'ref="l10n_', body, f"{source.name} references a localization XMLID"
            )

    def test_data_xml_has_no_transactional_records(self):
        self.assert_no_models_in_data(
            MODULE,
            {"purchase.order", "sale.order", "pos.order", "mrp.production", "stock.picking"},
            "data/ is configuration; business history belongs in demo/, which "
            "production never loads (--without-demo=all).",
        )
```

- [ ] **Step 2: Run them and verify they pass immediately**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -u afenda_industry_bakery --test-enable \
  --test-tags "/afenda_industry_bakery" --stop-after-init --http-port 8179
```

Expected: `afenda_industry_bakery: 9 tests`, `0 failed`. These three are guards, not red-green tests: they pass on correct data from the moment they are written. To prove a guard actually bites, temporarily add `<field name="company_id" eval="1"/>` to one product record, re-run, see `test_data_xml_sets_no_company_id` fail, then remove it. Do that once; do not commit it.

- [ ] **Step 3: Commit**

```bash
printf '%s\n' "[ADD] industry: static guards on the bakery pack data" "" \
  "Three scans of the pack's own XML: no company_id, no account/tax/journal" \
  "properties or l10n_ refs, no transactional records outside demo/." "" \
  "Static rather than runtime on purpose -- a static check holds even when the" \
  "localization is not installed in the test database, and it catches the" \
  "future edit that puts the mistake back." "" \
  "afenda_industry_bakery: 9 tests, 0 failed." "" \
  "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" > /tmp/msg5.txt
git add -- afenda/addons/afenda_industry_bakery && \
git commit --only -F /tmp/msg5.txt -- afenda/addons/afenda_industry_bakery
```

---

### Task 6: Demo data

**Files:**
- Create: `afenda/addons/afenda_industry_bakery/demo/bakery_demo.xml`
- Modify: `afenda/addons/afenda_industry_bakery/__manifest__.py` — add the `demo` key: `"demo": ["demo/bakery_demo.xml"],`

**Interfaces:**
- Consumes: product XMLIDs from Task 2.
- Produces: demo-only records; nothing later depends on them.

Contents: two suppliers (`res.partner` — "Moulin Dupont" for flour and "Laiterie Verte" for butter, milk and eggs), one `purchase.order` per supplier with lines for the products they supply, three `hr.employee` records (Head Baker, Pastry Chef, Counter Staff), and one `mrp.production` for 40 croissants. All wrapped in `<odoo><data noupdate="1"> … </data></odoo>`.

This is the only file allowed to create transactional records — Task 5's guard scans `data/`, not `demo/`, and that asymmetry is the point.

- [ ] **Step 1: Write the file, then verify production installs are unaffected**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -u afenda_industry_bakery --test-enable \
  --test-tags "/afenda_industry_bakery" --stop-after-init --http-port 8179
```

Expected: `afenda_industry_bakery: 9 tests`, `0 failed`. The `afenda` database was created `--without-demo=all`, so the demo file is parsed but not loaded; a failure here means something in `demo/` was wrongly listed under `data` in the manifest.

- [ ] **Step 2: Commit**

```bash
printf '%s\n' "[ADD] industry: bakery demo suppliers, orders and staff" "" \
  "Business history lives in demo/ and nowhere else: production installs run" \
  "--without-demo=all, so this is the line between a pack that configures a" \
  "real tenant and one that fills it with invented transactions." "" \
  "afenda_industry_bakery: 9 tests, 0 failed." "" \
  "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" > /tmp/msg6.txt
git add -- afenda/addons/afenda_industry_bakery && \
git commit --only -F /tmp/msg6.txt -- afenda/addons/afenda_industry_bakery
```

---

### Task 7: Final gates

**Files:** none — this task runs gates and fixes what they find.

- [ ] **Step 1: Both pack suites**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -u afenda_industry_base,afenda_industry_bakery \
  --test-enable --test-tags "/afenda_industry_base,/afenda_industry_bakery" \
  --stop-after-init --http-port 8179
```

Expected: `afenda_industry_base: 4 tests` and `afenda_industry_bakery: 9 tests`, 13 in total, `0 failed`.

Then run the same two modules **once on a fresh throwaway database** with `-i` and `--without-demo=all`, because that is what CI does (the orchestrator session's job builds a new database per run) and it is the only path that exercises `post_init_hook` end to end. Both result lines must read the same 3 and 9. Drop the scratch database and its filestore afterwards. These two numbers are what CI's floor is raised by — take them from the result lines, never the per-class stats lines.

- [ ] **Step 2: The `afenda_brand` suite — it now has two new addons in scope**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" .venv/Scripts/python odoo-bin \
  -c afenda/odoo.conf -d afenda -u afenda_brand --test-enable \
  --test-tags "/afenda_brand" --stop-after-init --http-port 8179
```

Expected: all pass. `test_every_test_class_would_actually_be_collected` AST-walks `afenda/addons/*/tests/*.py`, so it is now judging the two new modules. If it reports an offender, the test class was declared without `TransactionCase` as a direct base — fix the class, never the guard.

- [ ] **Step 3: Review**

Dispatch `odoo-reviewer` over `afenda/addons/afenda_industry_base` and `afenda/addons/afenda_industry_bakery`. It is read-only. Fix what it finds, re-run only the affected suite, then re-run the full pack gate once.

- [ ] **Step 4: Report**

Quote the printed counts from Steps 1 and 2 verbatim, name anything skipped, and report any failure in full even when you believe it unrelated.

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: the pack contract and `seed.py` → Task 1; the catalogue, shelf life and category rulings → Task 2; bills of material → Tasks 3–4; rulings 1 and 5 (company scoping, module ownership) → Task 4; rulings 2 and 3 (no localization, data vs demo) → Tasks 5–6; the acceptance counts → Task 7. Ruling 4 (`noupdate`) is carried by every `data/` file's `<data noupdate="1">` wrapper, stated in Tasks 2, 3 and 6.

**Type consistency.** `load_company_records(env, module, model_name, records, noupdate=True)` is defined once in Task 1 and called with that exact signature in Task 4. `IndustryPackMixin`'s three helpers — `pack_data_files`, `assert_no_field_in_data`, `assert_no_models_in_data`, plus `assert_records_are_module_owned` — are defined in Task 1 and used in Tasks 4 and 5 under those names. XMLID suffixes in the Task 2 catalogue match the `RECIPES` and `REORDER_RULES` tables in Task 4 exactly.

**Known rough edge, called out rather than hidden.** Task 3 discovers mid-task that BoM lines cannot be expressed in XML, because `mrp.bom.line.product_id` is a `product.product` (`addons/mrp/models/mrp_bom.py:684`) and the auto-created variant of a seeded template has no XMLID to reference. The plan resolves it by splitting headers (XML, Task 3) from lines (Python, Task 4) and leaves Task 3's test deliberately red at its own commit, with the commit message saying so. An executor who finds a cleaner route — a `product.product` record with its own XMLID per raw material — may take it, but must then update Task 2's expected count of 25 `product.template` records and say so in the commit.
