# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import AccessDenied, LockError, MissingError, UserError
from odoo.tests import HttpCase, mute_logger, new_test_user, tagged
from odoo.tools import config

from ..problems import PROBLEM_CODES, problem_code

_CONTRACT_KEYS = {"type", "title", "status", "code", "detail", "message"}
_DOCUMENTED_STATUS_BY_CODE = {code: status for code, status, _description in PROBLEM_CODES}


def _generate_key(env, user, days=0.5):
    return env["res.users.apikeys"].with_user(user)._generate(
        None, "t", datetime.now() + timedelta(days=days),
    )


@tagged("post_install", "-at_install")
class TestProblemDetails(HttpCase):
    """JSON-2 errors as RFC 9457 Problem Details, without server internals.

    An HttpCase, so an Odoo BaseCase: a plain unittest class would be
    discovered and then silently dropped (odoo/tests/tag_selector.py:88-90).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # base.user_admin: broad rights, used wherever a test needs to reach
        # past a plain internal user's ACLs (writing partners, patching a
        # model method) without that itself becoming the thing under test.
        cls.admin = cls.env.ref("base.user_admin")
        cls.admin_key = _generate_key(cls.env, cls.admin)
        # A plain internal user (base.group_user only): no access to
        # ir.cron, which is exactly what the 403 test needs.
        cls.employee = new_test_user(cls.env, login="afenda_json2_employee")
        cls.employee_key = _generate_key(cls.env, cls.employee)

    def setUp(self):
        super().setUp()
        # Every test runs as if dev mode were off: the rewrite is skipped
        # under dev mode (Global Constraints > Error contract), and a
        # developer's shell should not silently change these results.
        original = list(config["dev_mode"])
        config["dev_mode"] = []
        self.addCleanup(config.__setitem__, "dev_mode", original)

    def _bearer(self, key):
        return {"Authorization": f"Bearer {key}"}

    def _assert_contract_keys(self, body, *, fivexx):
        expected = set(_CONTRACT_KEYS)
        if fivexx:
            expected.add("instance")
        self.assertEqual(set(body), expected, body)

    def test_problem_code_follows_the_table(self):
        # Subclass order wins over the generic UserError mapping.
        self.assertEqual(problem_code(AccessDenied("x"), 403), "access_denied")
        self.assertEqual(problem_code(LockError("x"), 409), "conflict")
        # The exception class wins over a mismatched status too: these are
        # what pins "checked in this order" rather than "status decides".
        self.assertEqual(problem_code(AccessDenied("x"), 422), "access_denied")
        self.assertEqual(problem_code(MissingError("x"), 422), "not_found")
        # Any other 4xx not in the table falls back to invalid_request.
        self.assertEqual(problem_code(Exception("x"), 418), "invalid_request")
        # 5xx is always internal_error, whatever the exception.
        self.assertEqual(problem_code(Exception("x"), 503), "internal_error")

    def test_problem_codes_documents_every_4xx_the_runtime_can_return(self):
        # PROBLEM_CODES drives the /docs/api/errors page (controllers/api.py)
        # and the shared Problem response description
        # (afenda_api_docs/openapi.py's _PROBLEM_STATUSES): every status this
        # function can actually return for an unmapped exception must be
        # documented, either as its own integer or, for the catch-all
        # "invalid_request", as the literal string "4xx" (fix round 2,
        # finding 1 - PR #5 review). A plain Exception is never one of
        # _CODES_BY_EXCEPTION's classes, so this walks status alone.
        for status in range(400, 500):
            with self.subTest(status=status):
                code = problem_code(Exception("x"), status)
                documented = _DOCUMENTED_STATUS_BY_CODE[code]
                self.assertTrue(
                    documented == status or documented == "4xx",
                    f"status {status} -> code {code!r} documented as "
                    f"{documented!r}, which is neither {status} nor '4xx'",
                )

    def test_missing_bad_or_revoked_key_is_problem_401(self):
        revoked_user = new_test_user(self.env, login="afenda_json2_revoked")
        revoked_key = _generate_key(self.env, revoked_user)
        self.env["res.users.apikeys"].sudo().search(
            [("user_id", "=", revoked_user.id)],
        )._remove()

        cases = {
            "missing": {},
            "bad": self._bearer("not-a-real-api-key"),
            "revoked": self._bearer(revoked_key),
        }
        for label, headers in cases.items():
            with self.subTest(case=label):
                r = self.url_open(
                    "/json/2/res.partner/search", json={"domain": []}, headers=headers,
                )
                self.assertEqual(r.status_code, 401)
                self.assertEqual(
                    r.headers.get("Content-Type"), "application/problem+json; charset=utf-8",
                )
                self.assertIn("WWW-Authenticate", r.headers)
                body = r.json()
                self.assertEqual(body["code"], "unauthenticated")
                self.assertEqual(body["type"], "/docs/api/errors#unauthenticated")
                self._assert_contract_keys(body, fivexx=False)

    def test_access_error_is_problem_403(self):
        with mute_logger("odoo.http"):
            r = self.url_open(
                "/json/2/ir.cron/search",
                json={"domain": []},
                headers=self._bearer(self.employee_key),
            )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(
            r.headers.get("Content-Type"), "application/problem+json; charset=utf-8",
        )
        body = r.json()
        self.assertEqual(body["code"], "access_denied")
        self.assertEqual(body["type"], "/docs/api/errors#access_denied")
        self._assert_contract_keys(body, fivexx=False)

    def test_missing_record_is_problem_404_without_internals(self):
        missing_id = self.env["res.partner"].search([], order="id desc", limit=1).id + 1000
        with mute_logger("odoo.http"):
            r = self.url_open(
                "/json/2/res.partner/write",
                json={"ids": [missing_id], "vals": {"name": "x"}},
                headers=self._bearer(self.admin_key),
            )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(
            r.headers.get("Content-Type"), "application/problem+json; charset=utf-8",
        )
        body = r.json()
        self.assertEqual(body["code"], "not_found")
        self.assertEqual(body["type"], "/docs/api/errors#not_found")
        self.assertEqual(body["detail"], "Record does not exist or has been deleted.")
        self._assert_contract_keys(body, fivexx=False)
        raw = r.text
        # The raw MissingError message is "...(Record: res.partner(<id>,),
        # User: <uid>)": assert the actual leak shapes, not a bare digit that
        # could coincidentally appear in the id or a status code.
        self.assertNotIn("res.partner(", raw)
        self.assertNotIn("User:", raw)
        self.assertNotIn(f"User: {self.admin.id}", raw)

    def test_bad_arguments_are_problem_422(self):
        r = self.url_open(
            "/json/2/res.partner/search",
            json={"domain": [], "this_kwarg_does_not_exist": 1},
            headers=self._bearer(self.employee_key),
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(
            r.headers.get("Content-Type"), "application/problem+json; charset=utf-8",
        )
        body = r.json()
        self.assertEqual(body["code"], "invalid_request")
        self.assertEqual(body["type"], "/docs/api/errors#invalid_request")
        self._assert_contract_keys(body, fivexx=False)

    def test_malformed_json_body_is_problem_400(self):
        # Json2Dispatcher.dispatch (odoo/http.py) raises werkzeug's
        # BadRequest, an HTTPException with .code == 400, before any model or
        # method is even resolved - a status this table's invalid_request
        # row covers via the "4xx" fallback, not its own integer entry
        # (fix round 2, finding 1 - PR #5 review).
        with mute_logger("odoo.http"):
            r = self.url_open(
                "/json/2/res.partner/search",
                data=b"{not-valid-json",
                headers={
                    **self._bearer(self.admin_key),
                    "Content-Type": "application/json",
                },
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.headers.get("Content-Type"), "application/problem+json; charset=utf-8",
        )
        body = r.json()
        self.assertEqual(body["code"], "invalid_request")
        self.assertEqual(body["type"], "/docs/api/errors#invalid_request")
        self._assert_contract_keys(body, fivexx=False)

    def test_unexpected_error_is_opaque_500(self):
        with (
            mute_logger("odoo.http"),
            self.assertLogs("odoo.addons.afenda_runtime", "ERROR") as cm,
            patch.object(
                type(self.env["res.partner"]),
                "name_search",
                autospec=True,
                side_effect=RuntimeError("secret-internal-detail"),
            ),
        ):
            r = self.url_open(
                "/json/2/res.partner/name_search",
                json={"name": "x"},
                headers=self._bearer(self.admin_key),
            )
        self.assertEqual(r.status_code, 500)
        self.assertEqual(
            r.headers.get("Content-Type"), "application/problem+json; charset=utf-8",
        )
        body = r.json()
        self.assertEqual(body["code"], "internal_error")
        self.assertEqual(body["type"], "/docs/api/errors#internal_error")
        self.assertEqual(body["detail"], "Internal server error")
        self._assert_contract_keys(body, fivexx=True)

        raw = r.text
        for banned in ("secret-internal-detail", "Traceback", "odoo.", "debug", "arguments", "context"):
            self.assertNotIn(banned, raw)
        self.assertRegex(body["instance"], r"^urn:afenda:error:[0-9a-f]{32}$")
        self.assertTrue(
            any(body["instance"] in line for line in cm.output),
            cm.output,
        )

    def test_every_problem_has_exactly_the_contract_keys(self):
        missing_id = self.env["res.partner"].search([], order="id desc", limit=1).id + 1000
        cases = [
            (
                401,
                self.url_open(
                    "/json/2/res.partner/search", json={"domain": []}, headers={},
                ),
            ),
        ]
        with mute_logger("odoo.http"):
            cases.append((
                404,
                self.url_open(
                    "/json/2/res.partner/write",
                    json={"ids": [missing_id], "vals": {"name": "x"}},
                    headers=self._bearer(self.admin_key),
                ),
            ))
        with (
            mute_logger("odoo.http"),
            self.assertLogs("odoo.addons.afenda_runtime", "ERROR"),
            patch.object(
                type(self.env["res.partner"]),
                "name_search",
                autospec=True,
                side_effect=RuntimeError("boom"),
            ),
        ):
            cases.append(
                (
                    500,
                    self.url_open(
                        "/json/2/res.partner/name_search",
                        json={"name": "x"},
                        headers=self._bearer(self.admin_key),
                    ),
                ),
            )
        for expected_status, response in cases:
            with self.subTest(status=expected_status):
                self.assertEqual(response.status_code, expected_status)
                self._assert_contract_keys(response.json(), fivexx=expected_status >= 500)

    def test_json_rpc_errors_keep_upstream_shape(self):
        self.authenticate("admin", "admin")
        with (
            mute_logger("odoo.http"),
            patch.object(
                type(self.env["res.partner"]),
                "name_search",
                autospec=True,
                side_effect=UserError("x"),
            ),
        ):
            r = self.url_open(
                "/web/dataset/call_kw/res.partner/name_search",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "model": "res.partner",
                        "method": "name_search",
                        # `call_kw` reads `_api_model` off the bound method to
                        # decide whether `args[0]` is an id list; the mock
                        # below (autospec'd from `name_search`, an
                        # `@api.model` method) does not carry that custom
                        # attribute, so it is treated as an instance method
                        # and args[0] must be one (empty is fine).
                        "args": [[]],
                        "kwargs": {},
                    },
                },
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["error"]["data"]["name"], "odoo.exceptions.UserError")
