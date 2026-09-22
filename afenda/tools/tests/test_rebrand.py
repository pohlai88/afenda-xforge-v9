import re
import tempfile
import unittest
from pathlib import Path

from afenda.tools.rebrand import Rule, iter_files, rewrite_text, run

PRODUCT = Rule("product", re.compile(r"(?<![\w@/.])Odoo(?!\w)"), "AFENDA xForge")


class RewriteTextTests(unittest.TestCase):
    def test_replaces_standalone_word(self):
        out, counts = rewrite_text('title = _("Welcome to Odoo")\n', [PRODUCT], Path("a.py"))
        self.assertEqual(out, 'title = _("Welcome to AFENDA xForge")\n')
        self.assertEqual(counts, {"product": 1})

    def test_leaves_identifiers_alone(self):
        src = "class OdooEditor:\n    pass\nX_ODOO = 'X-Odoo-Database'\n"
        out, counts = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertEqual(out, src)
        self.assertEqual(counts, {})

    def test_skips_license_header_in_code(self):
        src = "# Part of Odoo. See LICENSE file.\n# Copyright Odoo S.A.\nname = 'Odoo'\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertTrue(out.startswith("# Part of Odoo. See LICENSE file.\n# Copyright Odoo S.A.\n"))
        self.assertIn("name = 'AFENDA xForge'", out)

    def test_skips_import_lines(self):
        src = "from odoo import Odoo\nimport Odoo.things\nlabel = 'Odoo'\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertIn("from odoo import Odoo\n", out)
        self.assertIn("import Odoo.things\n", out)
        self.assertIn("label = 'AFENDA xForge'", out)

    def test_copyright_is_not_protected_in_markup(self):
        src = "<small>Copyright 2004 Odoo</small>\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("t.xml"))
        self.assertEqual(out, "<small>Copyright 2004 AFENDA xForge</small>\n")

    def test_noqa_marker_protects_line(self):
        src = "x = 'Odoo'  # noqa: rebrand\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertEqual(out, src)

    def test_machine_endpoints_protected(self):
        src = "URL = 'https://iap.odoo.com/Odoo'\nURL2 = 'https://iap-services.odoo.com'\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertEqual(out, src)

    def test_po_only_touches_msgid_and_msgstr(self):
        src = (
            '#. module: base\n'
            '#: model:ir.module.module,shortdesc:base.module_Odoo\n'
            'msgid "Odoo"\n'
            'msgstr "Odoo"\n'
            'msgid ""\n'
            '"Welcome to Odoo, "\n'
            '"the suite"\n'
            'msgstr ""\n'
        )
        out, counts = rewrite_text(src, [PRODUCT], Path("fr.po"))
        self.assertIn('#: model:ir.module.module,shortdesc:base.module_Odoo\n', out)
        self.assertIn('msgid "AFENDA xForge"\n', out)
        self.assertIn('msgstr "AFENDA xForge"\n', out)
        self.assertIn('"Welcome to AFENDA xForge, "\n', out)
        self.assertEqual(counts, {"product": 3})

    def test_rule_suffix_and_path_filters(self):
        only_xml = Rule("x", re.compile("Odoo"), "A", suffixes=frozenset({".xml"}))
        self.assertTrue(only_xml.applies_to(Path("v.xml")))
        self.assertFalse(only_xml.applies_to(Path("v.py")))
        router = Rule("r", re.compile("Odoo"), "A", path_contains=("core/browser/router.js",))
        self.assertTrue(router.applies_to(Path("addons/web/static/src/core/browser/router.js")))
        self.assertFalse(router.applies_to(Path("addons/web/static/src/other.js")))
        no_iot = Rule("n", re.compile("Odoo"), "A", path_excludes=("iot_box_image",))
        self.assertFalse(no_iot.applies_to(Path("addons/iot_box_image/x.py")))

    def test_idempotent(self):
        src = "a = 'Odoo Odoo'\n"
        once, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        twice, counts = rewrite_text(once, [PRODUCT], Path("a.py"))
        self.assertEqual(once, twice)
        self.assertEqual(counts, {})

    def test_license_header_protected_in_any_file_type(self):
        src = "# Part of Odoo. See LICENSE file for full copyright and licensing details.\nname = 'Odoo'\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("model.py.template"))
        self.assertTrue(out.startswith("# Part of Odoo. See LICENSE"))
        self.assertIn("name = 'AFENDA xForge'", out)
        out2, _ = rewrite_text("<!-- Part of Odoo. -->\n<t>Odoo</t>\n", [PRODUCT], Path("v.xml"))
        self.assertEqual(out2, "<!-- Part of Odoo. -->\n<t>AFENDA xForge</t>\n")


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "addons" / "m").mkdir(parents=True)
        (self.root / "odoo").mkdir()
        (self.root / "afenda").mkdir()
        (self.root / ".git").mkdir()
        (self.root / "addons" / "m" / "v.xml").write_text("<t>Odoo</t>\n", encoding="utf-8")
        (self.root / "addons" / "m" / "logo.png").write_bytes(b"\x89PNG Odoo")
        (self.root / "odoo" / "x.py").write_text("s = 'Odoo'\n", encoding="utf-8")
        (self.root / "afenda" / "y.py").write_text("s = 'Odoo'\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_iter_files_scans_only_text_in_addons_and_odoo(self):
        rel = sorted(p.relative_to(self.root).as_posix() for p in iter_files(self.root))
        self.assertEqual(rel, ["addons/m/v.xml", "odoo/x.py"])

    def test_dry_run_changes_nothing_and_counts(self):
        counts = run(self.root, [PRODUCT], apply=False)
        self.assertEqual(counts, {"product": 2})
        self.assertEqual((self.root / "odoo" / "x.py").read_text(encoding="utf-8"), "s = 'Odoo'\n")

    def test_apply_writes_files(self):
        run(self.root, [PRODUCT], apply=True)
        self.assertEqual((self.root / "odoo" / "x.py").read_text(encoding="utf-8"), "s = 'AFENDA xForge'\n")
        self.assertEqual((self.root / "addons" / "m" / "v.xml").read_text(encoding="utf-8"), "<t>AFENDA xForge</t>\n")
        self.assertEqual((self.root / "afenda" / "y.py").read_text(encoding="utf-8"), "s = 'Odoo'\n")
        self.assertEqual(run(self.root, [PRODUCT], apply=False), {})


from afenda.tools.rules import RULES, load_brand


class RulesTests(unittest.TestCase):
    def rw(self, text, name):
        out, _ = rewrite_text(text, RULES, Path(name))
        return out

    def test_brand_values_loaded(self):
        b = load_brand()
        self.assertEqual(b["product"], "AFENDA xForge")
        self.assertEqual(b["url_prefix"], "app")

    def test_company_name_in_markup_becomes_short_name(self):
        self.assertEqual(self.rw("<a>Odoo S.A.</a>\n", "t.xml"), "<a>AFENDA</a>\n")
        self.assertEqual(self.rw('msgid "Odoo S.A."\n', "fr.po"), 'msgid "AFENDA"\n')

    def test_company_name_in_code_header_untouched(self):
        src = "# Copyright 2004 Odoo S.A.\n"
        self.assertEqual(self.rw(src, "a.py"), src)

    def test_bot(self):
        self.assertEqual(self.rw('name = _("OdooBot")\n', "a.py"), 'name = _("AFENDA Bot")\n')
        self.assertEqual(self.rw("state = user.odoobot_state\n", "a.py"), "state = user.odoobot_state\n")

    def test_documentation_links_go_same_origin(self):
        self.assertEqual(
            self.rw('href="https://www.odoo.com/documentation/19.0/applications/sales.html"\n', "v.xml"),
            'href="/docs/applications/sales.html"\n',
        )
        self.assertEqual(
            self.rw("url = 'https://www.odoo.com/documentation/latest/'\n", "a.py"),
            "url = '/docs/'\n",
        )

    def test_other_odoo_com_links_go_to_domain(self):
        self.assertEqual(self.rw("https://www.odoo.com?utm_source=db\n", "v.xml"), "https://www.afenda.app?utm_source=db\n")
        self.assertEqual(self.rw("https://accounts.odoo.com/account\n", "u.js"), "https://accounts.afenda.app/account\n")
        self.assertEqual(self.rw("info@odoo.com\n", "d.xml"), "info@afenda.app\n")

    def test_iap_endpoints_survive(self):
        src = "DEFAULT_ENDPOINT = 'https://iap.odoo.com'\n"
        self.assertEqual(self.rw(src, "a.py"), src)

    def test_url_prefix(self):
        self.assertEqual(self.rw("return request.redirect_query('/odoo', query=q)\n", "h.py"), "return request.redirect_query('/app', query=q)\n")
        self.assertEqual(self.rw("@http.route(['/web', '/odoo', '/odoo/<path:subpath>'])\n", "h.py"), "@http.route(['/web', '/app', '/app/<path:subpath>'])\n")
        self.assertEqual(self.rw('browser.location.pathname.startsWith("/odoo")\n', "r.js"), 'browser.location.pathname.startsWith("/app")\n')
        self.assertEqual(self.rw("goto('/odoo/action-108?debug=1')\n", "t.js"), "goto('/app/action-108?debug=1')\n")
        self.assertEqual(self.rw("path = '/home/odoo/bin'\n", "a.py"), "path = '/home/odoo/bin'\n")
        self.assertEqual(self.rw("ExecStart=/odoo/odoo-bin\n", "addons/iot_box_image/odoo.service"), "ExecStart=/odoo/odoo-bin\n")

    def test_router_prefix_constants(self):
        router = "addons/web/static/src/core/browser/router.js"
        self.assertEqual(self.rw('return isScopedApp() ? "scoped_app" : "odoo";\n', router), 'return isScopedApp() ? "scoped_app" : "app";\n')
        self.assertEqual(self.rw('if (["odoo", "scoped_app"].includes(prefix)) {\n', router), 'if (["app", "scoped_app"].includes(prefix)) {\n')
        self.assertEqual(self.rw('x = "odoo";\n', "addons/web/static/src/other.js"), 'x = "odoo";\n')

    def test_product_word_last(self):
        self.assertEqual(self.rw("<h1>Odoo Enterprise</h1>\n", "v.xml"), "<h1>AFENDA xForge Enterprise</h1>\n")
        self.assertEqual(self.rw("Sent by Odoo\n", "v.xml"), "Sent by AFENDA xForge\n")

    def test_hyphenated_words_are_rebranded(self):
        self.assertEqual(self.rw('msgstr "Verbindung zum Odoo-Server"\n', "de.po"), 'msgstr "Verbindung zum AFENDA xForge-Server"\n')
        self.assertEqual(self.rw("Non-Odoo systems\n", "v.xml"), "Non-AFENDA xForge systems\n")

    def test_http_header_prefix_survives(self):
        src = "header_dbname = self.httprequest.headers.get('X-Odoo-Database')\n"
        self.assertEqual(self.rw(src, "http.py"), src)
        src2 = "headers = {'Odoo-Link-Preview': '1'}\n"
        self.assertEqual(self.rw(src2, "link_preview.py"), src2)

    def test_social_handles(self):
        self.assertEqual(self.rw('href="https://twitter.com/Odoo"\n', "v.xml"), 'href="https://twitter.com/afenda"\n')
        self.assertEqual(self.rw('"https://www.facebook.com/Odoo"\n', "fr.po"), '"https://www.facebook.com/afenda"\n')
        self.assertEqual(self.rw('href="https://example.com/Odoo"\n', "v.xml"), 'href="https://example.com/Odoo"\n')
        self.assertEqual(self.rw('href="https://fedex.com/Odoo"\n', "v.xml"), 'href="https://fedex.com/Odoo"\n')
        self.assertEqual(self.rw('href="https://www.twitter.com/Odoo"\n', "v.xml"), 'href="https://www.twitter.com/afenda"\n')

    def test_rules_are_idempotent_on_own_output(self):
        samples = [
            ("<a>Odoo S.A.</a> Odoo OdooBot https://www.odoo.com/documentation/19.0/x https://odoo.com /odoo/x Odoo-Server https://twitter.com/Odoo\n", "v.xml"),
            ('msgid "Odoo"\nmsgstr "Odoo S.A."\n', "fr.po"),
        ]
        for text, name in samples:
            once = self.rw(text, name)
            self.assertEqual(self.rw(once, name), once)
            self.assertNotIn("Odoo", once)
            self.assertNotIn("odoo.com", once)


if __name__ == "__main__":
    unittest.main()
