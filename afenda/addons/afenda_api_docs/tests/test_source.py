import pathlib
import warnings

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
