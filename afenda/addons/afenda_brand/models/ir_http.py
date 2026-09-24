import json

from odoo import models
from odoo.http import request
from odoo.tools import config


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _handle_error(cls, exception):
        """Keep server internals out of JSON-2 API errors.

        Upstream puts the full server traceback in every error body and, for
        unexpected errors, the raw exception message (SQL, file paths). The
        server log already records both. Status codes and `name` stay as they
        are: they are the wire contract Odoo client libraries rely on.
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
        body["debug"] = ""
        if response.status_code >= 500:
            body.update(message="Internal server error", arguments=[])
        response.set_data(json.dumps(body))
        return response
