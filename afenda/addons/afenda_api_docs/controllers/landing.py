from odoo import http
from odoo.http import request


class AfendaDocsController(http.Controller):
    # The catch-all is not decoration. The placeholder this replaces answered
    # `/docs/<path:subpath>` as well as `/docs`, and 117 Settings help icons
    # point at `/docs/19.0/applications/...`. Without it those 404 from this
    # task until Task 8 lands. Task 8 adds more specific `/docs/applications`
    # rules, which werkzeug prefers over this one.
    @http.route(
        ["/docs", "/docs/<path:subpath>"],
        type="http", auth="public", website=False, sitemap=False,
    )
    def docs_landing(self, subpath=None, **kwargs):
        return request.render("afenda_api_docs.landing", {})
