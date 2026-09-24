from odoo import fields, models

from odoo.addons.afenda_brand.brand import read_static
from odoo.addons.afenda_brand.hooks import block_odoo_services


def _afenda_logo(record):
    return read_static("img/logo.png")


class ResCompany(models.Model):
    _inherit = "res.company"

    # base declares `default=_get_logo` bound to its own module-level function,
    # so overriding the method alone is not enough: re-declare the default.
    logo = fields.Binary(default=_afenda_logo)

    def _get_logo(self):
        """Default company logo: the AFENDA lockup instead of the Odoo one.

        base compares against this to compute `uses_default_logo`, so the
        lockup counts as a placeholder: like Odoo's own, it stays out of a
        customer's emails and portal until they upload their real logo.
        """
        return _afenda_logo(self)

    def _register_hook(self):
        super()._register_hook()
        block_odoo_services(self.env)
