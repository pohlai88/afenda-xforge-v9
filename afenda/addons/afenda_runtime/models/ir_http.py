# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
import json
import logging
import uuid
from http import HTTPStatus

from odoo import models
from odoo.exceptions import MissingError
from odoo.http import request
from odoo.tools import config

from ..problems import problem_code

_logger = logging.getLogger(__name__)

_DETAIL_NOT_FOUND = "Record does not exist or has been deleted."
_DETAIL_INTERNAL = "Internal server error"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _handle_error(cls, exception):
        """JSON-2 errors as RFC 9457 Problem Details, without server internals.

        Upstream answers with Odoo's exception class name, its raw
        arguments, ``context`` and the full server traceback
        (``odoo/http.py``'s ``serialize_exception``); the server log already
        keeps all of that (``odoo/http.py:2881``). Clients instead get the
        status, a stable ``code`` and a plain ``detail`` (``message`` repeats
        it), plus on 5xx an opaque ``instance`` id they can hand to support
        without ever seeing the exception text.
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
        code = problem_code(exception, status)
        if status >= 500:
            detail = _DETAIL_INTERNAL
        elif isinstance(exception, MissingError):
            detail = _DETAIL_NOT_FOUND
        else:
            detail = body.get("message") or str(status)

        try:
            title = HTTPStatus(status).phrase
        except ValueError:
            title = str(status)

        problem = {
            "type": f"/docs/api/errors#{code}",
            "title": title,
            "status": status,
            "code": code,
            "detail": detail,
            "message": detail,
        }
        if status >= 500:
            instance = f"urn:afenda:error:{uuid.uuid4().hex}"
            problem["instance"] = instance
            _logger.error("JSON-2 internal error %s (%s)", instance, type(exception).__name__)

        response.set_data(json.dumps(problem))
        response.headers["Content-Type"] = "application/problem+json; charset=utf-8"
        return response
