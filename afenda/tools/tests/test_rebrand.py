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

    def test_prose_starting_with_from_is_not_protected_as_import(self):
        src = "from Odoo itself, and that too with great possibilities.\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertIn("from AFENDA xForge itself", out)

    def test_real_import_still_protected(self):
        src = "from odoo import models\nfrom Odoo.legacy import Thing\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("a.py"))
        self.assertEqual(out, src)


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

# Derived, never hard-coded. A literal domain here tests a string the rules stop
# producing the moment a brand value changes — which is how the placeholder
# survived in eight assertions until the real domain arrived.
DOMAIN = load_brand()["domain"]


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

    def test_versionless_documentation_link_goes_same_origin(self):
        # The web client builds the settings help URL by concatenation, so the
        # literal carries no version segment and the versioned pattern misses it.
        self.assertEqual(
            self.rw('return "https://www.odoo.com/documentation/" + serverVersion + this.props.path;\n', "w.js"),
            'return "/docs/" + serverVersion + this.props.path;\n',
        )

    def test_documentation_link_on_the_brand_domain_is_repaired(self):
        # A versionless link the generic odoo.com rule already rewrote to the
        # brand domain is still off-origin; it must come back to /docs/.
        self.assertEqual(
            self.rw('return "https://www.' + DOMAIN + '/documentation/" + serverVersion + this.props.path;\n', "w.js"),
            'return "/docs/" + serverVersion + this.props.path;\n',
        )

    def test_documentation_link_rewrite_is_idempotent(self):
        once = self.rw('href="https://www.odoo.com/documentation/19.0/applications/sales.html"\n', "v.xml")
        self.assertEqual(self.rw(once, "v.xml"), once)

    def test_brand_domain_outside_documentation_is_left_alone(self):
        for src in ('href="https://www.' + DOMAIN + '/pricing"\n', "url = 'https://accounts." + DOMAIN + "/account'\n"):
            self.assertEqual(self.rw(src, "v.xml"), src)

    def test_other_odoo_com_links_go_to_domain(self):
        self.assertEqual(self.rw("https://www.odoo.com?utm_source=db\n", "v.xml"), "https://www." + DOMAIN + "?utm_source=db\n")
        self.assertEqual(self.rw("https://accounts.odoo.com/account\n", "u.js"), "https://accounts." + DOMAIN + "/account\n")
        self.assertEqual(self.rw("info@odoo.com\n", "d.xml"), "info@" + DOMAIN + "\n")

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

    def test_cli_folder_keeps_filesystem_paths(self):
        src = "    Run it as odoo-bin upgrade_code; see /odoo/upgrade_code for details.\n"
        self.assertEqual(self.rw(src, "odoo/cli/upgrade_code.py"), src)

    def test_percent_encoded_prefix(self):
        self.assertEqual(self.rw("q = 'redirect=%2Fodoo%2Faction-887'\n", "t.py"), "q = 'redirect=%2Fapp%2Faction-887'\n")

    def test_translator_attribution_kept(self):
        src = '"Last-Translator: Ron M <ronm@odoo.com>, 2025\\n"\n'
        self.assertEqual(self.rw(src, "fr.po"), src)

    def test_odoo_com_case_insensitive(self):
        self.assertEqual(self.rw("https://accounts.ODOO.COM/account\n", "u.js"), "https://accounts." + DOMAIN + "/account\n")

    def test_allcaps_leaves_api_identifiers_alone(self):
        """ODOO in Python and JS payloads is a registered third-party identifier."""
        cases = [
            ("            'paymentSource': 'ODOO',\n", "payment_transaction.py"),
            ("        request_id = 'ODOO' + secrets.token_hex(13)\n", "connection.py"),
            ("'merchantCustomerId': ('ODOO-%s-%s' % (a, b))\n", "authorize_request.py"),
            ("     * ODOO FIX START\n", "cropper.js"),
        ]
        for src, name in cases:
            self.assertEqual(self.rw(src, name), src, name)

    def test_allcaps_odoo_word(self):
        self.assertEqual(self.rw('<separator string="FOR WEBSITES BUILT WITH ODOO"/>\n', "v.xml"), '<separator string="FOR WEBSITES BUILT WITH AFENDA XFORGE"/>\n')

    def test_lowercase_quoted_attribute_value(self):
        self.assertEqual(self.rw('title="odoo"\n', "v.xml"), 'title="AFENDA"\n')
        self.assertEqual(self.rw('placeholder="odoo"\n', "v.xml"), 'placeholder="AFENDA"\n')
        self.assertEqual(self.rw('x = "https://odoo.com"\n', "a.py"), 'x = "https://' + DOMAIN + '"\n')

    def test_iap_endpoint_protected_in_python_only(self):
        self.assertEqual(self.rw("DEFAULT_ENDPOINT = 'https://iap.odoo.com'\n", "a.py"), "DEFAULT_ENDPOINT = 'https://iap.odoo.com'\n")

    def test_iap_endpoint_rewritten_in_template(self):
        self.assertIn(DOMAIN, self.rw('<a href="https://iap-services.odoo.com/iap/sms/pricing">Pricing</a>\n', "v.xml"))

    def test_odoo_package_internal_paths_excluded(self):
        self.assertEqual(self.rw("frame.filename.endswith('/odoo/http.py')\n", "odoo/netsvc.py"), "frame.filename.endswith('/odoo/http.py')\n")
        self.assertEqual(self.rw('if "/odoo/addons/" in filename:\n', "odoo/tests/common.py"), 'if "/odoo/addons/" in filename:\n')

    def test_company_name_in_python_manifest(self):
        self.assertEqual(self.rw("    'author': 'Odoo S.A.',\n", "addons/web/__manifest__.py"), "    'author': 'AFENDA',\n")

    def test_superseded_domain_bare_host(self):
        self.assertEqual(self.rw("https://afenda.app/pricing\n", "v.xml"), "https://" + DOMAIN + "/pricing\n")

    def test_superseded_domain_subdomain(self):
        self.assertEqual(self.rw("https://accounts.afenda.app/account\n", "u.js"), "https://accounts." + DOMAIN + "/account\n")

    def test_superseded_domain_email(self):
        self.assertEqual(self.rw("jane@afenda.app\n", "d.xml"), "jane@" + DOMAIN + "\n")

    def test_superseded_domain_www_url(self):
        self.assertEqual(self.rw("https://www.afenda.app/x\n", "v.xml"), "https://www." + DOMAIN + "/x\n")

    def test_superseded_domain_documentation_link_still_repaired(self):
        # superseded_domain must run before docs_link, or this would land on
        # the new domain as a bare link instead of coming home to /docs/.
        self.assertEqual(
            self.rw('href="https://www.afenda.app/documentation/19.0/applications/sales.html"\n', "v.xml"),
            'href="/docs/applications/sales.html"\n',
        )

    def test_current_domain_is_not_rewritten_by_superseded_rule(self):
        # Anti-loop: the domain rules land on must itself be left alone, or a
        # second rebrand pass would keep rewriting the tree forever.
        src = "https://" + DOMAIN + "/pricing\n"
        self.assertEqual(self.rw(src, "v.xml"), src)

    def test_current_domain_never_listed_as_superseded(self):
        from afenda.tools.rules import _SUPERSEDED_DOMAINS
        self.assertNotIn(DOMAIN, _SUPERSEDED_DOMAINS)

    def test_current_domain_as_superseded_raises(self):
        # Fires the construction-time guard directly: if BRAND['domain'] were
        # ever also listed in _SUPERSEDED_DOMAINS, build_rules must refuse to
        # build the rule set rather than silently loop on a second rebrand
        # pass. assertRaisesRegex (not bare assertRaises) pins this to the
        # guard actually meant, not any unrelated ValueError.
        from afenda.tools.rules import build_rules, _SUPERSEDED_DOMAINS
        bad_brand = dict(load_brand())
        bad_brand["domain"] = _SUPERSEDED_DOMAINS[0]
        with self.assertRaisesRegex(ValueError, "_SUPERSEDED_DOMAINS"):
            build_rules(bad_brand)

    def test_domain_containing_a_superseded_value_also_raises(self):
        # Proves the guard tests the match condition, not mere membership:
        # "app.nexuscanon.com" is not *in* ("nexuscanon.com",), but the
        # \b-bounded pattern for "nexuscanon.com" still matches inside it
        # (preceded by ".", a non-word character). A membership-only guard
        # would miss this and every `rebrand --apply` would grow the domain
        # another "app." label.
        from unittest import mock
        from afenda.tools.rules import build_rules
        bad_brand = dict(load_brand())
        bad_brand["domain"] = "app.nexuscanon.com"
        with mock.patch("afenda.tools.rules._SUPERSEDED_DOMAINS", ("nexuscanon.com",)):
            with self.assertRaisesRegex(ValueError, "_SUPERSEDED_DOMAINS"):
                build_rules(bad_brand)

    def test_superseded_domain_word_prefix_not_matched(self):
        # \b excludes word-char-prefixed hosts: "notafenda.app" must not
        # become "not" + the current domain.
        src = "https://notafenda.app/x\n"
        self.assertEqual(self.rw(src, "v.xml"), src)

    def test_superseded_domain_hyphen_prefix_is_matched(self):
        # \b does NOT exclude non-word-char prefixes like "-", so
        # "foo-afenda.app" DOES match -- identical to the existing odoo_com
        # rule's own behaviour, not a gap introduced by this rule.
        self.assertEqual(self.rw("https://foo-afenda.app/x\n", "v.xml"), "https://foo-" + DOMAIN + "/x\n")

    def test_noto_cdn_local_rewrites_all_source_forms(self):
        # fonts.scss carries exactly these 4 families x 3 formats = 12 source
        # forms (see afenda/tools/tests/corpus/corpus.txt:33038-33049); each
        # must resolve locally instead of fetching from fonts.odoocdn.com.
        families = ("NotoSans", "NotoSansArabic", "NotoSansHebrew", "NotoSansTelugu")
        formats = (("woff2", "woff2"), ("woff", "woff"), ("ttf", "truetype"))
        for family in families:
            for ext, fmt in formats:
                src = f"url('https://fonts.odoocdn.com/fonts/noto/{family}-#{{$type}}.{ext}') format('{fmt}')\n"
                expected = f"local('{family}-Regular')\n"
                self.assertEqual(self.rw(src, "fonts.scss"), expected, src)

    def test_noto_cdn_local_idempotent(self):
        src = "url('https://fonts.odoocdn.com/fonts/noto/NotoSansHebrew-#{$type}.woff2') format('woff2')\n"
        once = self.rw(src, "fonts.scss")
        self.assertEqual(self.rw(once, "fonts.scss"), once)
        self.assertNotIn("fonts.odoocdn.com", once)

    def test_noto_cdn_local_scoped_to_scss(self):
        # Same text in a non-.scss file must survive untouched -- the rule is
        # specific to fonts.scss's own @font-face syntax.
        src = "url('https://fonts.odoocdn.com/fonts/noto/NotoSans-#{$type}.woff2') format('woff2')\n"
        self.assertEqual(self.rw(src, "fonts.js"), src)


if __name__ == "__main__":
    unittest.main()


class RstUnderlineTests(unittest.TestCase):
    """Odoo renders module descriptions and READMEs as reStructuredText.

    A title's underline must be at least as long as the title, or docutils
    warns and the heading renders wrong in the Apps list. Substituting "Odoo"
    with a longer product name lengthens the title and leaves the underline
    where it was, which broke 43 headings across the tree - every one of them
    caused by the transform, none of them wrong upstream.
    """

    def test_a_lengthened_title_gets_its_rule_repadded(self):
        src = "Odoo CRM\n--------\n\nbody\n"
        out, counts = rewrite_text(src, [PRODUCT], Path("addons/crm/README.md"))
        title, rule = out.split("\n")[:2]
        self.assertEqual(title, "AFENDA xForge CRM")
        self.assertEqual(rule, "-" * len(title), "the underline was not repadded to the new title")
        self.assertEqual(counts.get("rst_underline"), 1)

    def test_the_underline_character_is_preserved(self):
        for ch in "=-~^`#*+_":
            src = f"Odoo Accounting\n{ch * 15}\n"
            out, _ = rewrite_text(src, [PRODUCT], Path("addons/account/README.md"))
            rule = out.split("\n")[1]
            self.assertEqual(set(rule), {ch}, f"{ch} was not preserved")
            self.assertEqual(len(rule), len("AFENDA xForge Accounting"))

    def test_a_rule_that_is_already_long_enough_is_untouched(self):
        src = "Odoo\n" + "=" * 60 + "\n"
        out, counts = rewrite_text(src, [PRODUCT], Path("addons/x/README.md"))
        self.assertEqual(out.split("\n")[1], "=" * 60, "a long enough rule must not be shortened")
        self.assertNotIn("rst_underline", counts)

    def test_a_title_the_transform_did_not_touch_is_left_alone(self):
        """The repair exists to undo this transform's own collateral damage. A
        short underline upstream shipped is upstream's business - and there are
        none, so anything it touched beyond that would be a new defect."""
        src = "Some Other Heading\n---\n"
        out, counts = rewrite_text(src, [PRODUCT], Path("addons/x/README.md"))
        self.assertEqual(out, src)
        self.assertNotIn("rst_underline", counts)

    def test_only_where_odoo_renders_rst(self):
        """.md, .rst and __manifest__.py descriptions are rendered as RST. An
        ordinary .py file is code: a comment rule under a comment line is not a
        heading, and padding it would churn source for nothing."""
        src = "# Odoo notes\n# ----\n"
        out, counts = rewrite_text(src, [PRODUCT], Path("addons/crm/models/thing.py"))
        self.assertNotIn("rst_underline", counts)
        self.assertEqual(out.split("\n")[1], "# ----")

        man = 'Odoo CRM\n--------\n'
        out2, counts2 = rewrite_text(man, [PRODUCT], Path("addons/crm/__manifest__.py"))
        self.assertEqual(counts2.get("rst_underline"), 1)

    def test_an_overline_is_not_mistaken_for_an_underline(self):
        """A rule ABOVE a title is an overline; it is not made short by
        lengthening the title below it, and padding it alone would leave an
        RST section with mismatched over and under rules, which is a hard
        docutils error rather than a warning."""
        src = "=" * 8 + "\nOdoo CRM\n" + "=" * 8 + "\n"
        out, _ = rewrite_text(src, [PRODUCT], Path("addons/crm/README.md"))
        lines = out.split("\n")
        self.assertEqual(len(lines[0]), len(lines[2]),
                         "the overline and underline no longer match")

    def test_it_repairs_a_tree_that_is_already_converged(self):
        """The damage is already in the tree: those titles carry the new name, so
        a later run has nothing left to substitute and `changed` is empty. If the
        repair only looked at lines it had just rewritten it would never fire on
        the very files it was written to fix."""
        src = "AFENDA xForge CRM\n--------\n"
        out, counts = rewrite_text(src, [PRODUCT], Path("addons/crm/README.md"))
        self.assertEqual(counts.get("rst_underline"), 1)
        self.assertEqual(out.split("\n")[1], "-" * len("AFENDA xForge CRM"))

    def test_it_is_idempotent(self):
        """Running twice must not keep growing the rule."""
        src = "AFENDA xForge CRM\n--------\n"
        once, _ = rewrite_text(src, [PRODUCT], Path("addons/crm/README.md"))
        twice, counts = rewrite_text(once, [PRODUCT], Path("addons/crm/README.md"))
        self.assertEqual(once, twice)
        self.assertNotIn("rst_underline", counts)


class AccentTealTests(unittest.TestCase):
    """Odoo's second brand colour, and the four places it is not brand at all.

    The corpus golden test does not cover this rule: the corpus is a
    deduplicated sample and it happens not to carry any of these lines, so
    `corpus diff` reported no change when the rule was added. That makes these
    assertions the only thing standing between the rule and silent drift.
    """

    def setUp(self):
        self.rule = next(r for r in RULES if r.name == "odoo_accent_teal")

    def test_it_rewrites_both_odoo_teals(self):
        for hexcode in ("#017e84", "#017E84", "#00a09d", "#00A09D"):
            out, counts = rewrite_text(
                f"color: {hexcode};", [self.rule], Path("addons/web/static/src/x.scss"))
            self.assertEqual(counts.get("odoo_accent_teal"), 1, f"{hexcode} was not rewritten")
            self.assertEqual(out, f"color: {load_brand()['primary']};")

    def test_it_does_not_eat_a_longer_hex(self):
        """#017e8400 is an 8-digit RGBA, not the teal followed by two zeroes."""
        out, counts = rewrite_text(
            "color: #017e8400;", [self.rule], Path("addons/web/static/src/x.scss"))
        self.assertEqual(counts.get("odoo_accent_teal", 0), 0, "the rule swallowed an RGBA hex")
        self.assertIn("#017e8400", out)

    def test_the_colour_picker_test_is_left_alone(self):
        """It asserts the picker offers rgb(1, 126, 132).

        Rewriting the value under an assertion about that value turns a passing
        upstream test into a failing one, and the failure would read as our
        bug rather than as our edit.
        """
        rel = Path("addons/html_editor/static/tests/color_selector.test.js")
        self.assertFalse(self.rule.applies_to(rel), "the html_editor colour test is being rewritten")

    def test_the_sample_and_demo_content_is_left_alone(self):
        for rel in (
            Path("addons/project_todo/data/todo_template.xml"),
            Path("addons/spreadsheet_dashboard_website_sale/data/files/ecommerce_dashboard.json"),
        ):
            self.assertFalse(self.rule.applies_to(rel), f"{rel} is demo content, not brand")

    def test_the_spreadsheet_component_keeps_its_own_palette(self):
        """o_spreadsheet ships its palette upstream; it is not Odoo's identity."""
        rel = Path("addons/spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js")
        self.assertFalse(self.rule.applies_to(rel), "o_spreadsheet's own palette is being rewritten")

    def test_the_real_brand_surfaces_are_still_in_scope(self):
        """The exclusions must not be so broad that they take the target with them."""
        for rel in (
            Path("addons/web/static/src/scss/primary_variables.scss"),
            Path("addons/digest/models/digest.py"),
            Path("addons/iot_drivers/static/src/app/css/homepage.css"),
            Path("addons/web_hierarchy/static/src/hierarchy.variables.scss"),
        ):
            self.assertTrue(self.rule.applies_to(rel), f"{rel} is brand and should be rewritten")

    def test_translations_are_out_of_scope_like_every_other_colour_rule(self):
        """.po carries 171 of these, all translations of the demo template."""
        rel = Path("addons/project_todo/i18n/fr.po")
        self.assertFalse(self.rule.applies_to(rel), "a colour rule reached a translation file")
