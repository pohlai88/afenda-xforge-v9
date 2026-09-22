import base64

from odoo import fields, models
from odoo.tools import file_open

from ..brand import BRAND


def _afenda_logo(record):
    with file_open("afenda_brand/static/img/logo.png", "rb") as f:
        return base64.b64encode(f.read())


class ResCompany(models.Model):
    _inherit = "res.company"

    # base declares `default=_get_logo` bound to its own module-level function,
    # so overriding the method alone is not enough: re-declare the default.
    logo = fields.Binary(default=_afenda_logo)

    # mail's names are read from the email: "primary" is the CTA button text,
    # "secondary" is the button fill. The install hook writes these on the
    # existing companies; these defaults carry them to companies created later.
    email_primary_color = fields.Char(default=BRAND["on_primary"])
    email_secondary_color = fields.Char(default=BRAND["primary"])

    def _get_logo(self):
        """Default company logo: the AFENDA lockup instead of the Odoo one."""
        return _afenda_logo(self)
