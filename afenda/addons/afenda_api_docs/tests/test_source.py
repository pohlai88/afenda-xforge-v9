import importlib.util
import pathlib
import sys
import unittest
import warnings
from unittest.mock import patch

from odoo.tests import BaseCase

ADDON = pathlib.Path(__file__).resolve().parents[1]


class TestSourceCompilesCleanly(BaseCase):
    def test_every_python_file_compiles_without_warnings(self):
        # A docstring that explains a regex in a non-raw string is the trap:
        # `\w` is an invalid escape (DeprecationWarning at compile time, a
        # SyntaxWarning from Python 3.12) and `\b` is a *valid* one that
        # silently becomes a backspace character. The warning fires only when
        # the file is compiled, so a cached .pyc hides it locally while a
        # fresh CI checkout logs it with a traceback. Compiling from source
        # here catches it on every run, cache or not.
        for path in sorted(ADDON.rglob("*.py")):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            self.assertEqual(
                [str(w.message) for w in caught], [],
                "%s emits warnings when compiled" % path.relative_to(ADDON),
            )


class TestIdentityTestsSurviveWithoutRepoTools(BaseCase):
    def test_identity_tests_import_and_skip_without_afenda_tools(self):
        # test_identity.py uses afenda/tools, which is repo tooling on
        # sys.path only because odoo-bin's own directory is. If importing it
        # failed at module level, odoo/tests/loader.py would fail to import
        # the whole tests package and every test in this addon would be lost.
        # None in sys.modules makes an import raise ImportError.
        path = ADDON / "tests" / "test_identity.py"
        # Named under odoo.addons.* because BaseCase only gives test_tags to
        # classes from such modules (odoo/tests/common.py:315-317); it is never
        # put in sys.modules, so the test loader does not collect it.
        spec = importlib.util.spec_from_file_location(
            "odoo.addons.afenda_api_docs.tests._identity_probe", path
        )
        module = importlib.util.module_from_spec(spec)
        blocked = {"afenda": None, "afenda.tools": None, "afenda.tools.rules": None}
        with patch.dict(sys.modules, blocked):
            spec.loader.exec_module(module)
            case = module.TestAliasingParity(
                "test_runtime_aliaser_agrees_with_the_file_rules_on_shared_cases"
            )
            with self.assertRaises(unittest.SkipTest):
                case.test_runtime_aliaser_agrees_with_the_file_rules_on_shared_cases()
