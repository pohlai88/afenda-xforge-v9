from odoo import fields, models

from odoo.addons.afenda_brand.brand import BRAND, read_static
from odoo.addons.afenda_brand.hooks import block_odoo_services, email_colors


class ResCompany(models.Model):
    _inherit = "res.company"

    # base declares `default=_get_logo` bound to its own module-level function,
    # so overriding the method alone is not enough: re-declare the default.
    logo = fields.Binary(default=lambda self: read_static("img/logo.png"))
    # Companies created after install get the AFENDA colors too; the install
    # hook applies the same values to the companies that already exist.
    primary_color = fields.Char(default=BRAND["primary"])
    secondary_color = fields.Char(default=BRAND["ink"])
    email_primary_color = fields.Char(default=email_colors()["email_primary_color"])
    email_secondary_color = fields.Char(default=email_colors()["email_secondary_color"])

    def _get_logo(self):
        """Default company logo: the AFENDA lockup instead of the Odoo one.

        base compares against this to compute `uses_default_logo`, so the
        lockup counts as a placeholder: like Odoo's own, it stays out of a
        customer's emails and portal until they upload their real logo.
        """
        return read_static("img/logo.png")

    def _get_default_favicon(self, original=False):
        """web_favicon gives new companies Odoo's icon with a colored bar."""
        return read_static("img/favicon.ico")

    def _register_hook(self):
        super()._register_hook()
        block_odoo_services(self.env)
