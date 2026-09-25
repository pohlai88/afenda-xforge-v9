from odoo import http
from odoo.http import request

from ..openapi import build_document


class AfendaApiController(http.Controller):
    # auth='user': the document lists every model and field the caller can
    # read, which is an information-disclosure surface, and is generated per
    # user - meaningless if it could be fetched anonymously. werkzeug ranks
    # this static rule above landing.py's `/docs/<path:subpath>` catch-all.
    @http.route(
        "/docs/openapi.json",
        type="http", auth="user", methods=["GET"], website=False, sitemap=False,
    )
    def docs_openapi(self, app=None, **kwargs):
        return request.make_json_response(build_document(request.env, app=app or None))
