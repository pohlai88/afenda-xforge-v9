import base64

from odoo import fields, models
from odoo.tools import file_open


def _afenda_logo(record):
    with file_open("afenda_brand/static/img/logo.png", "rb") as f:
        return base64.b64encode(f.read())


class ResCompany(models.Model):
    _inherit = "res.company"

    # base declares `default=_get_logo` bound to its own module-level function,
    # so overriding the method alone is not enough: re-declare the default.
    logo = fields.Binary(default=_afenda_logo)

    def _get_logo(self):
        """Default company logo: the AFENDA lockup instead of the Odoo one."""
        return _afenda_logo(self)
