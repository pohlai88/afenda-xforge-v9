from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def autocomplete_by_vat(self, vat, query_country_id, timeout=15):
        """Null adapter: no lookup by VAT number.

        Upstream falls back to the EU VIES service when the autocomplete call
        returns nothing (addons/partner_autocomplete/models/res_partner.py:115-118),
        so the null autocomplete adapter alone would still reach out here.
        """
        return []
