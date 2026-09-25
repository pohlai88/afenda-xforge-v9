import json
from http import HTTPStatus

from odoo import models
from odoo.exceptions import (
    AccessDenied,
    AccessError,
    ConcurrencyError,
    MissingError,
    UserError,
    ValidationError,
)
from odoo.http import request
from odoo.tools import config

# Stable error codes of the AFENDA API (SPEC.md, decision D7). Checked in
# order: subclasses before their parents.
_CODES = (
    (AccessDenied, "unauthenticated"),
    (AccessError, "access_denied"),
    (MissingError, "not_found"),
    (ConcurrencyError, "conflict"),
    (ValidationError, "validation_error"),
    (UserError, "user_error"),
)
_CODES_BY_STATUS = {401: "unauthenticated", 403: "access_denied", 404: "not_found", 409: "conflict"}


def _problem_code(exception, status):
    if status >= 500:
        return "internal_error"
    for exc_class, code in _CODES:
        if isinstance(exception, exc_class):
            return code
    return _CODES_BY_STATUS.get(status, "invalid_request")


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _handle_error(cls, exception):
        """JSON-2 errors as RFC 9457 Problem Details, without server internals.

        Upstream answers with Odoo's exception class, arguments, context and
        the full server traceback; the server log already keeps all of that.
        Clients get the status, a stable `code` and a readable `detail`
        (`message` repeats it for the /doc explorer). A 500 never echoes the
        raw exception text.
        """
        response = super()._handle_error(exception)
        if request.dispatcher.routing_type != "json2" or config["dev_mode"]:
            return response
        try:
            body = json.loads(response.get_data())
        except ValueError:
            return response
        if not isinstance(body, dict) or "debug" not in body:
            return response
        status = response.status_code
        detail = "Internal server error" if status >= 500 else body.get("message") or str(status)
        problem = {
            "type": "about:blank",
            "title": HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else str(status),
            "status": status,
            "code": _problem_code(exception, status),
            "detail": detail,
            "message": detail,
        }
        response.set_data(json.dumps(problem))
        response.headers["Content-Type"] = "application/problem+json; charset=utf-8"
        return response
