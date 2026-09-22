from odoo import http

from odoo.addons.web.controllers import home

from ..brand import BRAND


class Home(home.Home):
    """The login card carries the AFENDA tagline under the company logo."""

    @http.route()
    def web_login(self, *args, **kw):
        response = super().web_login(*args, **kw)
        # A successful POST returns a redirect, which has no template context.
        if hasattr(response, "qcontext"):
            response.qcontext["afenda_tagline"] = BRAND["tagline"]
        return response
