from odoo.tests import BaseCase, HttpCase, tagged

from odoo.addons.afenda_api_docs.aliasing import alias_prose

# The guide-sync half of the plan's Task 9 is not repeated here:
# afenda/tools/tests/test_build_docs_sync.py already holds views/guides.xml
# to its Markdown without a database.

# Case-sensitive on purpose (checked with `assertNotIn`, never folded to
# lowercase first): a case-insensitive match would also flag sanctioned
# wire values that merely share letters with these tells but are not
# identity - `ODOO.BALANCE`-shaped spreadsheet formula names (all-caps,
# aliasing.py's own docstring), and field names such as `odoobot_state`
# (all-lowercase; a live document's schema property name, never prose -
# see PROSE_KEYS below). Every prose insertion point already runs through
# `alias_prose`, whose own rules (aliasing.py) are case-insensitive on the
# word itself, so a real identity leak in prose is caught regardless of
# case; this tuple only has to catch what `alias_prose` might have missed
# in Title Case or exact-phrase form, not answer for wire values at all.
ODOO_TELLS = ("Odoo", "odoo.com", "OdooBot", "Odoo S.A.")

# Keys whose values are prose in an OpenAPI document built by openapi.py.
# Everything else - property names, enum keys, operationId, summary (the
# method name), tags, paths, x-relation - is a wire value.
PROSE_KEYS = ("title", "description", "x-enum-labels")


def walk_prose(doc, keys=PROSE_KEYS):
    """Every string value found under one of `keys`, anywhere in `doc`.

    `x-enum-labels` is a *list* of strings, not a single one, so a value
    found under one of `keys` is flattened into `prose` rather than kept as
    a list - `prose.extend(...)`, never `prose.append(...)`, is what makes
    a caller's `for text in prose: assertNoTells(text, ...)` see each label
    individually. A dict value found under `keys` (a *field* named `title`
    or `description`, e.g. res.partner has a `title` field, holds a schema
    dict, not text) is walked like any other node but never added to
    `prose` itself - only `isinstance(text, str)` values from `prose` are
    meaningful to check, which the caller decides, not this function.
    Shared with `TestDocsCrawl.test_document_prose_carries_no_odoo_identity`
    below and with `tests/test_assets.py`'s committed-asset check, so the
    two never drift into checking a different key set by accident for the
    keys they do share.
    """
    prose = []

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in keys:
                    prose.extend(value if isinstance(value, list) else [value])
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(doc)
    return prose


class TestAliasingParity(BaseCase):
    def test_runtime_aliaser_agrees_with_the_file_rules_on_shared_cases(self):
        # The runtime aliaser is deliberately broader (case-insensitive), but
        # it must never disagree with the build-time rules where both apply:
        # capitalised identity in text any file type would carry.
        #
        # afenda.tools is repo tooling, importable only because odoo-bin puts
        # its own directory - the repo root - first on sys.path. Imported
        # here, not at module level: a failed module-level import would make
        # odoo/tests/loader.py fail on the whole tests package and silently
        # take every test in this addon with it. CI still runs this test:
        # .github/workflows/afenda-image.yml runs /opt/afenda/odoo-bin with
        # the checked-out afenda/tools mounted at /opt/afenda/afenda/tools.
        try:
            from afenda.tools import rules as file_rules  # noqa: PLC0415
        except ImportError as exc:
            self.skipTest(f"afenda.tools is not importable (repo root not on sys.path): {exc}")
        global_rules = [
            rule for rule in file_rules.RULES
            if rule.suffixes is None and not rule.path_contains and not rule.path_excludes
        ]
        self.assertTrue(global_rules)
        for sample in (
            "Powered by Odoo",
            "Copyright Odoo S.A.",
            "Ask OdooBot",
            "see odoo.com for more",
            "read https://www.odoo.com/documentation/19.0/x.html",
            "read https://odoo.com/documentation/",
        ):
            expected = sample
            for rule in global_rules:
                expected = rule.pattern.sub(rule.replacement, expected)
            self.assertEqual(alias_prose(sample), expected, sample)


@tagged("post_install", "-at_install")
class TestDocsCrawl(HttpCase):
    def assertNoTells(self, text, where):
        for tell in ODOO_TELLS:
            self.assertNotIn(tell, text, f"{tell!r} on {where}")

    def test_public_pages_carry_no_odoo_identity(self):
        for url in (
            "/docs",
            "/docs/applications/general/users.html",
            "/docs/19.0/applications/general/users.html",
            # No guide: follows the redirect and crawls where it lands.
            "/docs/19.0/applications/finance/nothing_here.html",
        ):
            res = self.url_open(url)
            self.assertEqual(res.status_code, 200, url)
            self.assertNoTells(res.text, url)

    def test_signed_in_pages_carry_no_odoo_identity(self):
        self.authenticate("admin", "admin")
        for url in ("/docs/api", "/docs/api?app=mail"):
            res = self.url_open(url)
            self.assertEqual(res.status_code, 200, url)
            self.assertNoTells(res.text, url)

    def test_document_prose_carries_no_odoo_identity(self):
        self.authenticate("admin", "admin")
        for app in ("", "mail", "base"):
            doc = self.url_open(f"/docs/openapi.json?app={app}").json()
            prose = walk_prose(doc)
            self.assertTrue(prose, app)
            for text in prose:
                if isinstance(text, str):
                    self.assertNoTells(text, f"openapi.json?app={app}")

    def test_wire_values_survive_in_the_document(self):
        self.authenticate("admin", "admin")
        doc = self.url_open("/docs/openapi.json").json()
        schemas = doc["components"]["schemas"]
        self.assertIn("res.partner", schemas)
        self.assertTrue(any(p.startswith("/json/2/res.partner/") for p in doc["paths"]))
        # Field names that carry the name and must be sent back verbatim.
        users = schemas["res.users"]["properties"]
        for field in ("odoobot_state", "odoobot_failed"):
            self.assertIn(field, users)
        self.assertEqual(
            users["odoobot_state"]["enum"],
            [key for key, _label in self.env["res.users"]._fields["odoobot_state"]
             ._description_selection(self.env)],
        )
