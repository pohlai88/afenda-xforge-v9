import hashlib
import pathlib
import re

from odoo.tests import HttpCase, tagged

from odoo.addons.afenda_runtime.problems import PROBLEM_CODES

REDOC = pathlib.Path(__file__).resolve().parents[1] / "static" / "lib" / "redoc"
REDOC_URL = "/afenda_api_docs/static/lib/redoc/redoc.standalone.js"


@tagged("post_install", "-at_install")
class TestApiRoutes(HttpCase):
    def assertRedirectsToLogin(self, url):
        # auth='user' on a type='http' route: an anonymous request raises
        # SessionExpiredException, which odoo/http.py answers with a 303 to
        # /web/login. Following that redirect would end on a 200 login page,
        # so the redirect itself is what is asserted.
        res = self.url_open(url, allow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertIn("/web/login", res.headers["Location"])

    def test_openapi_json_requires_a_session(self):
        self.assertRedirectsToLogin("/docs/openapi.json")

    def test_openapi_json_serves_a_document_to_a_logged_in_user(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/openapi.json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["Content-Type"].startswith("application/json"))
        # Per user and cached server-side; never by a shared cache.
        self.assertEqual(res.headers["Cache-Control"], "private, no-store")
        self.assertEqual(res.json()["openapi"], "3.1.0")

    def test_openapi_json_is_scoped_by_app(self):
        self.authenticate("admin", "admin")
        doc = self.url_open("/docs/openapi.json?app=mail").json()
        tags = {t["name"] for t in doc["tags"]}
        self.assertIn("mail.message", tags)
        self.assertNotIn("res.partner", tags)

    def test_api_reference_requires_a_session(self):
        self.assertRedirectsToLogin("/docs/api")

    def test_api_reference_renders_and_loads_redoc_from_this_origin(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/api")
        self.assertEqual(res.status_code, 200)
        self.assertIn(f'src="{REDOC_URL}"', res.text)
        self.assertRegex(res.text, r'<redoc [^>]*spec-url="/docs/openapi.json"')
        self.assertNotIn("cdn.", res.text)
        self.assertNotIn("Odoo", res.text)

    def test_api_reference_asks_redoc_to_sanitize_markdown(self):
        # Field help, model descriptions and docstrings reach Redoc as
        # Markdown; without this option the bundle injects their raw HTML.
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/api")
        self.assertRegex(res.text, r'<redoc [^>]*sanitize="true"')

    def test_api_reference_passes_the_app_through(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/api?app=mail")
        self.assertIn('spec-url="/docs/openapi.json?app=mail"', res.text)

    def test_api_reference_refuses_third_party_images(self):
        # The bundle renders a logo from cdn.redoc.ly unconditionally; the
        # policy is what stops the browser fetching it (see static/lib/redoc/README.md).
        self.authenticate("admin", "admin")
        policy = self.url_open("/docs/api").headers["Content-Security-Policy"]
        self.assertIn("img-src 'self' data:", policy)
        self.assertIn("frame-ancestors 'self'", policy)

    def test_app_picker_lists_installed_apps_to_whoever_can_read_modules(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/docs/api?app=mail")
        # QWeb renders a true t-att-selected as selected="True".
        self.assertRegex(res.text, r'<option value="mail" selected="[^"]*">')
        self.assertIn('<option value="base"', res.text)

    def test_app_picker_is_absent_for_users_who_cannot_read_modules(self):
        # ir.module.module is readable by group_system
        # (odoo/addons/base/security/ir.model.access.csv:25) and, once
        # base_install_request is installed, by group_user too (its
        # security/ir.model.access.csv:5) - never by portal. The page does
        # not sudo() around that.
        self.env["res.users"].create({
            "name": "Docs portal",
            "login": "docs_portal",
            "password": "docs_portal_pw",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        self.authenticate("docs_portal", "docs_portal_pw")
        res = self.url_open("/docs/api")
        self.assertEqual(res.status_code, 200)
        self.assertIn("<redoc", res.text)
        self.assertNotIn("<option", res.text)

    def test_errors_page_lists_every_code(self):
        # Public, no login: the "type" field of every JSON-2 error body
        # points here (#<code>), so it must be reachable by whoever gets
        # the error, signed in or not.
        res = self.url_open("/docs/api/errors")
        self.assertEqual(res.status_code, 200)
        for code, _status, _description in PROBLEM_CODES:
            self.assertIn('id="%s"' % code, res.text)

    def test_landing_links_to_the_api_reference(self):
        self.assertIn('href="/docs/api"', self.url_open("/docs").text)

    def test_vendored_redoc_is_served_and_matches_its_recorded_hash(self):
        recorded = re.search(
            r"^sha256: ([0-9a-f]{64})  redoc\.standalone\.js$",
            (REDOC / "README.md").read_text(encoding="utf-8"),
            re.MULTILINE,
        ).group(1)
        res = self.url_open(REDOC_URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(hashlib.sha256(res.content).hexdigest(), recorded)
        for name in ("LICENSE", "redoc.standalone.js.LICENSE.txt"):
            self.assertTrue((REDOC / name).is_file(), name)
