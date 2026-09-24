import json
import re
from datetime import datetime, timedelta

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.afenda_brand.brand import BRAND

CT_JSON = {"Content-Type": "application/json"}


@tagged("post_install", "-at_install")
class TestExternalApi(HttpCase):
    """The external API, end to end over HTTP, as a customer's integration uses it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env.ref("base.user_admin")
        # What Preferences > Account Security > New API Key does.
        cls.api_key = cls.env["res.users.apikeys"].with_user(admin)._generate(
            scope="rpc", name="integration", expiration_date=datetime.now() + timedelta(days=1),
        )

    def json2(self, model, method, payload=None, key=None):
        headers = dict(CT_JSON)
        if key is not False:
            headers["Authorization"] = f"Bearer {key or self.api_key}"
        return self.url_open(f"/json/2/{model}/{method}", data=json.dumps(payload or {}), headers=headers)

    def test_json2_crud(self):
        res = self.json2("res.partner", "create", {"vals_list": [{"name": "API Partner", "email": "api@example.com"}]})
        self.assertEqual(res.status_code, 200, res.text)
        [partner_id] = res.json()

        res = self.json2("res.partner", "search_read", {
            "domain": [["id", "=", partner_id]], "fields": ["name", "email"],
        })
        self.assertEqual(res.json(), [{"id": partner_id, "name": "API Partner", "email": "api@example.com"}])

        res = self.json2("res.partner", "write", {"ids": [partner_id], "vals": {"name": "API Partner 2"}})
        self.assertIs(res.json(), True)
        res = self.json2("res.partner", "read", {"ids": [partner_id], "fields": ["name"]})
        self.assertEqual(res.json()[0]["name"], "API Partner 2")

        res = self.json2("res.partner", "unlink", {"ids": [partner_id]})
        self.assertIs(res.json(), True)
        res = self.json2("res.partner", "search_count", {"domain": [["id", "=", partner_id]]})
        self.assertEqual(res.json(), 0)

    @mute_logger("odoo.http")
    def test_json2_authentication(self):
        for key in (False, "not-a-real-key"):
            with self.subTest(key=key):
                res = self.json2("res.partner", "search", {"domain": []}, key=key)
                self.assertEqual(res.status_code, 401)
                self.assertIn("bearer", res.headers.get("WWW-Authenticate", "").lower())

    @mute_logger("odoo.http", "odoo.sql_db")
    def test_json2_errors_hide_server_internals(self):
        cases = [
            # (model, method, payload, status)
            ("no.such.model", "search", {"domain": []}, 404),
            ("res.users", "create", {"vals_list": [{"name": "Twin", "login": "admin"}]}, 422),
            ("res.partner", "read", {"ids": [1], "fields": ["no_such_field"]}, 500),
        ]
        for model, method, payload, status in cases:
            with self.subTest(model=model, method=method):
                res = self.json2(model, method, payload)
                self.assertEqual(res.status_code, status, res.text)
                body = res.json()
                self.assertEqual(body["debug"], "", "server traceback leaked to the API client")
                self.assertNotIn("Traceback", res.text)
                self.assertTrue(body["name"])
                if status == 500:
                    self.assertEqual(body["message"], "Internal server error")
                    self.assertNotIn("no_such_field", res.text)

    def test_xmlrpc_with_api_key(self):
        db = self.env.cr.dbname
        self.assertEqual(self.xmlrpc_common.version()["server_version_info"][0], 19)
        uid = self.xmlrpc_common.authenticate(db, "admin", self.api_key, {})
        self.assertEqual(uid, self.env.ref("base.user_admin").id)
        count = self.xmlrpc_object.execute_kw(db, uid, self.api_key, "res.partner", "search_count", [[]])
        self.assertGreater(count, 0)

    def test_json_version(self):
        res = self.url_open("/json/version")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["version_info"][0], 19)

    def test_doc_explorer_is_branded(self):
        self.authenticate("admin", "admin")
        res = self.url_open("/doc")
        self.assertEqual(res.status_code, 200)
        self.assertIn(f"<title>{BRAND['product']} API</title>", res.text.replace("\n", ""))
        self.assertNotIn("Odoo Runtime Doc", res.text)

        css_links = re.findall(r'href="(/web/assets/[^"]+/api_doc\.assets\.min\.css)"', res.text)
        self.assertTrue(css_links, "api_doc.assets stylesheet not linked from /doc")
        css = self.url_open(css_links[0]).text.lower()
        self.assertGreater(css.rfind("#1e3a8a"), css.find("rgb(107, 62, 102)"), "Ledger Blue must override the purple")

        js_links = re.findall(r'src="(/web/assets/[^"]+/api_doc\.assets\.min\.js)"', res.text)
        self.assertTrue(js_links, "api_doc.assets script not linked from /doc")
        self.assertIn(f"{BRAND['product']} API", self.url_open(js_links[0]).text)

        res = self.url_open("/doc/index.json", timeout=60)
        self.assertEqual(res.status_code, 200)
        self.assertIn('"res.partner"', res.text)

    @mute_logger("odoo.http")
    def test_doc_access(self):
        new_test_user(self.env, login="clerk", groups="base.group_user")
        self.authenticate("clerk", "clerk")
        self.assertEqual(self.url_open("/doc/index.json").status_code, 403)

        self.authenticate(None, None)
        res = self.url_open("/doc-bearer/index.json", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=60)
        self.assertEqual(res.status_code, 200)
