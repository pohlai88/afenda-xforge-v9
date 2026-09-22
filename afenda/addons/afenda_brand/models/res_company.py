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

    # Printed documents. These four are base fields
    # (odoo/addons/base/models/res_company.py:88-91); re-declaring them adds the
    # AFENDA face to the Selection and moves the defaults, nothing else.
    # The Selection key doubles as a CSS family name: web.styles_company_report
    # emits it raw as `font-family: Source_Sans_3`, which fonts_report.scss
    # declares (addons/web/views/report_templates.xml:925-926).
    font = fields.Selection(
        selection_add=[("Source_Sans_3", "Source Sans 3")],
        default="Source_Sans_3",
        ondelete={"Source_Sans_3": "set default"},
    )
    external_report_layout_id = fields.Many2one(
        default=lambda self: self.env.ref("web.external_layout_standard", raise_if_not_found=False),
    )
    # A document has no action to take, so no Ledger Blue on it: the title and
    # totals are ink, the labels graphite.
    primary_color = fields.Char(default=BRAND["ink"])
    secondary_color = fields.Char(default=BRAND["graphite"])

    def _get_logo(self):
        """Default company logo: the AFENDA lockup instead of the Odoo one."""
        return _afenda_logo(self)
