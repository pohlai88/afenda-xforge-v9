from odoo import http
from odoo.http import request


class AfendaDocsController(http.Controller):
    @http.route(['/docs', '/docs/<path:subpath>'], type='http', auth='public', website=False, sitemap=False)
    def docs_placeholder(self, subpath=None, **kwargs):
        return request.render('afenda_brand.docs_placeholder', {})
