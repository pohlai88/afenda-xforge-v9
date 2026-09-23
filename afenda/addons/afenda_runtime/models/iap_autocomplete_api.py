from odoo import api, models


class IapAutocompleteApi(models.AbstractModel):
    _inherit = "iap.autocomplete.api"

    @api.model
    def _request_partner_autocomplete(self, action, params, timeout=15):
        """Null adapter: partner autocomplete is an Odoo-hosted service.

        Overridden here rather than at ``_contact_iap`` because that one first
        calls ``iap.account.get``, which creates and commits an account from a
        separate cursor (addons/iap/models/iap_account.py:171-190). ``(False,
        False)`` is "no results, no error": every caller then returns empty
        without raising a toast (addons/partner_autocomplete/models/res_partner.py:86-194).
        """
        return False, False
