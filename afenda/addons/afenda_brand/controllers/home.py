from odoo import http

from odoo.addons.web.controllers import home

from ..brand import BRAND


class Home(home.Home):
    """The login card carries the AFENDA tagline under the company logo."""

    @http.route()
    def web_login(self, *args, **kw):
        response = super().web_login(*args, **kw)
        # Every odoo.http.Response carries a qcontext (set_default, http.py:1573),
        # redirects included; the guard is only for a third-party override of
        # web_login returning a plain werkzeug response.
        if hasattr(response, "qcontext"):
            response.qcontext["afenda_tagline"] = BRAND["tagline"]
        return response
