from unittest.mock import patch
from urllib.parse import urlsplit

import requests

import odoo.modules.module
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.iap.tools import iap_tools

LOOPBACK = {"127.0.0.1", "localhost"}
NULL_ENDPOINT = "http://127.0.0.1:9"
ENDPOINT_PARAMS = (
    "iap.endpoint",
    "sms.endpoint",
    "snailmail.endpoint",
    "html_editor.olg_api_endpoint",
    "html_editor.media_library_endpoint",
    "iap.partner_autocomplete.endpoint",
    "enrich.endpoint",
    "reveal.endpoint",
)
INDUSTRIES = [("module_type", "=", "industries")]


@tagged("post_install", "-at_install")
class TestNoOdooHost(TransactionCase):
    """Every Odoo-hosted entry point this module neutralizes stays on loopback.

    The test runs the real code paths rather than trusting the overrides:

    - ``current_test`` is forced off, because both IAP layers return early
      while it is set (addons/iap/tools/iap_tools.py:113-114,
      addons/partner_autocomplete/models/iap_autocomplete_api.py:20-21), which
      would make an un-neutralized path look silent here.
    - ``requests.Session.send`` is replaced by a recorder, which also replaces
      BaseCase's own external-request block (odoo/tests/common.py:337-379), so
      nothing can leave the machine and every attempt is seen. It raises
      ``ConnectionError`` the way a closed port would.
    - The registry cannot be put in test mode alongside that patch: a
      TestCursor asserts ``current_test`` is set (odoo/tests/test_cursor.py:42-43).
      So the only partner_autocomplete account ``iap.account.get`` can see is
      one with a token, created in this transaction. If the null adapter is
      ever lost, ``get`` then returns it without opening the committing cursor
      it otherwise uses (addons/iap/models/iap_account.py:153-190), and the
      test fails on the returned value instead of writing to the database.
    """

    def setUp(self):
        super().setUp()
        self.requested_urls = []

        def record(session, request, **kwargs):
            self.requested_urls.append(request.url)
            raise requests.exceptions.ConnectionError(f"afenda_runtime test: {request.url}")

        IapAccount = self.env["iap.account"].sudo()
        IapAccount.search([("service_name", "=", "partner_autocomplete")]).unlink()
        IapAccount.create({
            "service_id": self.env.ref("partner_autocomplete.iap_service_partner_autocomplete").id,
        })
        self.env.flush_all()

        self.startPatcher(patch.object(odoo.modules.module, "current_test", False))
        self.startPatcher(patch.object(requests.sessions.Session, "send", record))
        # `_get_industry_categories_from_apps` and `_call_apps` are ormcached
        # upstream (addons/base_import_module/models/ir_module.py:497-511): a
        # value cached before this test would hide the request being made.
        self.env.registry.clear_cache()

    def assertOnlyLoopback(self):
        hosts = {urlsplit(url).hostname for url in self.requested_urls}
        self.assertLessEqual(
            hosts, LOOPBACK,
            f"requests left the machine: {self.requested_urls}",
        )

    def test_endpoint_parameters(self):
        ICP = self.env["ir.config_parameter"].sudo()
        for key in ENDPOINT_PARAMS:
            with self.subTest(key=key):
                self.assertEqual(ICP.get_param(key), NULL_ENDPOINT)
        # base_vat raises on any value but its two own hosts
        # (addons/base_vat/models/res_partner.py:263-268).
        self.assertFalse(ICP.get_param("iap_vies.endpoint"))

    def test_recorder_sees_a_real_request(self):
        """The recorder is live and iap.endpoint routes to loopback, so an
        empty ``requested_urls`` in the other tests means no request, not a
        blind spot."""
        # iap_jsonrpc's error message calls `_()` from a frame with no env,
        # which logs a stack at WARNING (odoo/tools/translate.py:561); that is
        # upstream noise, while the failure warning itself is expected.
        with (
            mute_logger("odoo.tools.translate"),
            self.assertLogs("odoo.addons.iap.tools.iap_tools", "WARNING"),
            self.assertRaises(AccessError),
        ):
            iap_tools.iap_jsonrpc(iap_tools.iap_get_endpoint(self.env) + "/iap/1/balance", params={})
        self.assertEqual(
            [(u.hostname, u.port) for u in map(urlsplit, self.requested_urls)],
            [("127.0.0.1", 9)],
        )

    def test_partner_autocomplete(self):
        api = self.env["iap.autocomplete.api"]
        self.assertEqual(
            api._request_partner_autocomplete("search_by_name", {"query": "afenda"}),
            (False, False),
        )
        belgium = self.env.ref("base.be").id
        Partner = self.env["res.partner"]
        self.assertEqual(Partner.autocomplete_by_name("afenda", belgium), [])
        # No VIES fallback (addons/partner_autocomplete/models/res_partner.py:115-118).
        self.assertEqual(Partner.autocomplete_by_vat("BE0477472701", belgium), [])
        # The enrich path res.company takes on creation (res_company.py:59).
        self.assertEqual(Partner.enrich_by_domain("example.com"), {})
        self.assertOnlyLoopback()

    def test_apps_store(self):
        Module = self.env["ir.module.module"]
        self.assertEqual(Module._get_modules_from_apps(["name"], "industries", False), [])
        self.assertEqual(Module._get_industry_categories_from_apps(), [])
        # The public callers of those two, as the Apps screen reaches them.
        self.assertEqual(
            Module.web_search_read(INDUSTRIES, {"name": {}}),
            {"length": 0, "records": []},
        )
        self.assertEqual(
            Module.search_panel_select_range("category_id", category_domain=INDUSTRIES)["values"],
            [],
        )
        with self.assertRaises(UserError):
            Module.with_context(module_name="afenda_industry").button_immediate_install_app()
        self.assertOnlyLoopback()
