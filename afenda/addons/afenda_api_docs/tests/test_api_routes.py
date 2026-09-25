from odoo.tests import HttpCase, tagged


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
        self.assertEqual(res.json()["openapi"], "3.1.0")

    def test_openapi_json_is_scoped_by_app(self):
        self.authenticate("admin", "admin")
        doc = self.url_open("/docs/openapi.json?app=mail").json()
        tags = {t["name"] for t in doc["tags"]}
        self.assertIn("mail.message", tags)
        self.assertNotIn("res.partner", tags)
