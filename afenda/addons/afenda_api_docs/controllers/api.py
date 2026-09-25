from werkzeug.urls import url_encode

from odoo import http
from odoo.http import request

from ..aliasing import alias_prose
from ..openapi import build_document

# The Redoc bundle unconditionally renders an "API docs by Redocly" link with
# a logo fetched from cdn.redoc.ly (static/lib/redoc/README.md). Hiding the
# link with CSS would not stop an <img> from loading, and patching the
# vendored file would break its recorded hash, so the browser is told to
# refuse third-party images on this one page instead. Same per-response
# mechanism upstream uses on the login page (addons/web/controllers/home.py:153),
# including its `frame-ancestors 'self'` against framing by another origin.
_API_PAGE_CSP = "img-src 'self' data:; frame-ancestors 'self'"


class AfendaApiController(http.Controller):
    # auth='user' on both routes: the document lists every model and field the
    # caller can read, which is an information-disclosure surface, and is
    # generated per user - meaningless if it could be fetched anonymously.
    # werkzeug ranks these static rules above landing.py's
    # `/docs/<path:subpath>` catch-all.
    @http.route(
        "/docs/openapi.json",
        type="http", auth="user", methods=["GET"], website=False, sitemap=False,
    )
    def docs_openapi(self, app=None, **kwargs):
        return request.make_json_response(build_document(request.env, app=app or None))

    @http.route(
        "/docs/api",
        type="http", auth="user", methods=["GET"], website=False, sitemap=False,
    )
    def docs_api(self, app=None, **kwargs):
        spec_url = "/docs/openapi.json"
        if app:
            spec_url += "?" + url_encode({"app": app})
        response = request.render("afenda_api_docs.api_reference", {
            "spec_url": spec_url,
            "app": app or "",
            "apps": self._app_choices(),
        })
        response.headers["Content-Security-Policy"] = _API_PAGE_CSP
        return response

    def _app_choices(self):
        """(name, label) of each installed module that defines a concrete model.

        Offered only to users who may read ir.module.module (group_system,
        odoo/addons/base/security/ir.model.access.csv) - no sudo(): anyone
        else gets the default document and can still pass ?app= by hand.
        The name is a wire value (it goes back in the query string); the
        label is prose.
        """
        Module = request.env["ir.module.module"]
        if not Module.has_access("read"):
            return []
        env = request.env
        defining = {
            env[name]._original_module
            for name in env.registry
            if not env[name]._abstract
        }
        modules = Module.search(
            [("state", "=", "installed"), ("name", "in", sorted(defining))],
            order="shortdesc, name",
        )
        return [(module.name, alias_prose(module.shortdesc or module.name)) for module in modules]
