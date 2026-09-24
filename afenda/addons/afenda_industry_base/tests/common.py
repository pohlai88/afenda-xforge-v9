# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Shared assertions for industry pack tests.

Deliberately a mixin that does NOT subclass TransactionCase and declares no
`test_` methods. afenda_brand's `test_every_test_class_would_actually_be_collected`
resolves a test class's bases only within the same file
(afenda/addons/afenda_brand/tests/test_branding.py:1537-1545), so a pack test
written as `class TestBakeryPack(IndustryPackCase)` would resolve to
{IndustryPackCase}, miss Odoo's case classes, and fail that guard. Packs
therefore declare `class TestBakeryPack(IndustryPackMixin, TransactionCase)`,
and this mixin is skipped by the guard because it has no `test_` methods (:1548-1551).
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
