from odoo import api, models
from odoo.exceptions import AccessDenied, UserError

from ..mail_templates import strip_invitation_marketing


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    # Every translation load funnels through here: language activation
    # (odoo/addons/base/models/res_lang.py:341), the language wizard and module
    # updates call _update_translations, which calls this
    # (odoo/addons/base/models/ir_module.py:893, :972-990). The importer adds a
    # language's full invitation body for a key the record does not have yet
    # (odoo/tools/translate.py:1715), marketing included, so it is removed again
    # right after.
    @api.model
    def _load_module_terms(self, modules, langs, overwrite=False):
        res = super()._load_module_terms(modules, langs, overwrite=overwrite)
        if "auth_signup" in modules:
            strip_invitation_marketing(self.env)
        return res

    # Null adapters for the Odoo apps store that base_import_module queries for
    # industry modules (addons/base_import_module/models/ir_module.py:440-563).

    @api.model
    def _get_modules_from_apps(self, fields, module_type, module_name, domain=None, limit=None, offset=None):
        return []

    # Upstream also wraps this in `@ormcache()`; a constant needs no cache.
    @api.model
    def _get_industry_categories_from_apps(self):
        return []

    def button_immediate_install_app(self):
        # Same access gate as upstream, so a non-admin still gets AccessDenied.
        if not self.env.is_admin():
            raise AccessDenied()
        raise UserError(self.env._("Industry packages are not available in this deployment."))
